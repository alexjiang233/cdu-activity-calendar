"""校园活动与指南的领域模型。

设计要点：
- 活动（Activity）是稳定系列；通知（Notice）是某一年的某一份公告；来源（Source）按 URL 唯一。
- 事实（Fact）与正文画像（Profile）逐条保存，原文引句与编辑值分开。
- 学院拆分卡（ActivityGroup）只做展示分组，不复制通知，避免同一公告出现在两条记录里。
- 修订（Revision）、变更（ChangeLog）、导入批次（ImportBatch）保留历史，隐藏不等于删除。
"""
from django.db import models
from django.utils import timezone

VISIBILITY = [('public', '公开'), ('hidden', '隐藏')]


class TimeStamped(models.Model):
    created_at = models.DateTimeField('创建时间', auto_now_add=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        abstract = True


class Taxonomy(models.Model):
    """统一词表：类别、学院、级别。"""
    KIND = [('category', '活动类别'), ('college', '学院'), ('level', '级别')]
    kind = models.CharField('词表类型', max_length=16, choices=KIND)
    code = models.CharField('代码', max_length=40)
    label = models.CharField('名称', max_length=80)
    position = models.PositiveIntegerField('排序', default=0)

    class Meta:
        verbose_name = '分类标签'
        verbose_name_plural = '分类标签'
        unique_together = [('kind', 'code')]
        ordering = ['kind', 'position', 'code']

    def __str__(self):
        return f'{self.get_kind_display()}·{self.label}'


class Activity(TimeStamped):
    """活动系列：稳定 ID 不因改标题变化。"""
    id = models.CharField('活动 ID', max_length=64, primary_key=True)
    title = models.CharField('标题', max_length=200)
    kind = models.CharField('记录类型', max_length=20, default='notice')
    category = models.ForeignKey(
        Taxonomy, verbose_name='活动类别', null=True, blank=True, on_delete=models.PROTECT,
        related_name='activities', limit_choices_to={'kind': 'category'},
    )
    summary = models.TextField('卡片摘要', blank=True)
    tags = models.JSONField('标签', default=list, blank=True)
    editorial_note = models.TextField('编辑补充说明', blank=True)
    featured = models.BooleanField('首页候选', default=False)
    spotlight = models.BooleanField('精选', default=False)
    position = models.PositiveIntegerField('排序', default=0)
    visibility = models.CharField('公开状态', max_length=10, choices=VISIBILITY, default='public')
    split_by_college = models.BooleanField('按学院拆成卡片', default=False)
    material_ids = models.JSONField('关联资料 ID', default=list, blank=True)
    extras = models.JSONField('扩展字段（原样保留）', default=dict, blank=True)
    layout = models.JSONField('原字段顺序', default=list, blank=True)
    source_revision = models.CharField('导入修订', max_length=64, blank=True)
    # 导入/编辑时算好，供搜索与筛选下推到数据库；不参与公开展示
    search_text = models.TextField('可检索文本', blank=True, default='', editable=False)
    # 后台“保存草稿”后的待发布内容；公开接口只读正式字段，不看这里
    draft = models.JSONField('未发布草稿', null=True, blank=True, editable=False, default=None)

    class Meta:
        verbose_name = '活动'
        verbose_name_plural = '活动'
        ordering = ['position', 'id']
        indexes = [
            models.Index(fields=['visibility', 'featured', 'spotlight']),
            models.Index(fields=['visibility', 'category']),
        ]

    def __str__(self):
        return self.title

    @property
    def category_label(self):
        return self.category.label if self.category_id else (self.extras.get('category_label') or '未分类')

    @property
    def is_public(self):
        return self.visibility == 'public'


class Source(models.Model):
    id = models.CharField('来源 ID', max_length=80, primary_key=True)
    url = models.URLField('来源地址', max_length=500, unique=True)
    title = models.CharField('原文标题', max_length=300, blank=True)
    publisher = models.CharField('发布单位', max_length=120, blank=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True)

    class Meta:
        verbose_name = '来源'
        verbose_name_plural = '来源'
        ordering = ['id']

    def __str__(self):
        return self.url


class Notice(TimeStamped):
    """某份公告：同一活动同一年可以有多份（报名、补充、延期、赛程）。"""
    id = models.CharField('通知 ID', max_length=80, primary_key=True)
    activity = models.ForeignKey(Activity, verbose_name='所属活动', on_delete=models.CASCADE, related_name='notices')
    source = models.ForeignKey(Source, verbose_name='来源', null=True, blank=True, on_delete=models.PROTECT, related_name='notices')
    year = models.PositiveIntegerField('年份', null=True, blank=True)
    visibility = models.CharField('公开状态', max_length=10, choices=VISIBILITY, default='public')
    published = models.DateField('公告日期', null=True, blank=True)
    deadline = models.DateTimeField('报名/提交截止', null=True, blank=True)
    deadline_kind = models.CharField('截止类型', max_length=20, blank=True,
                                     help_text='registration 报名截止；submission 作品截止；combined 两者；notice 原文其他截止')
    stage_start = models.DateField('活动阶段开始', null=True, blank=True)
    stage_end = models.DateField('活动阶段结束', null=True, blank=True)
    audience = models.TextField('参与对象', blank=True)
    conflict = models.BooleanField('原文存在冲突', default=False)
    display_activity = models.ForeignKey(
        Activity, verbose_name='展示归属', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='displayed_notices',
        help_text='公开页面把这条通知显示在哪个活动下；为空表示沿用所属活动。原归属不会被改写。')
    position = models.PositiveIntegerField('同年排序', default=0)
    taxonomies = models.ManyToManyField(Taxonomy, through='NoticeTaxonomy', related_name='notices', blank=True)
    extras = models.JSONField('扩展字段（原样保留）', default=dict, blank=True)
    layout = models.JSONField('原字段顺序', default=list, blank=True)
    # 导入/编辑时算好：搜索文本与“往年这个月”的起始月集合（逗号分隔，如 ",3,5,"）
    search_text = models.TextField('可检索文本', blank=True, default='', editable=False)
    seasonal_months = models.CharField('往年月份', max_length=40, blank=True, default='', editable=False)

    class Meta:
        verbose_name = '通知版本'
        verbose_name_plural = '通知版本'
        ordering = ['-year', '-published', 'position']
        indexes = [
            models.Index(fields=['activity', 'year']),
            models.Index(fields=['year', 'published']),
            models.Index(fields=['deadline']),
        ]

    def __str__(self):
        return f'{self.activity_id} · {self.year or "年份未明"}'

    @property
    def college_labels(self):
        return [t.label for t in self.taxonomies.all() if t.kind == 'college' and t.code != 'unknown']

    @property
    def level_codes(self):
        return [t.code for t in self.taxonomies.all() if t.kind == 'level' and t.code != 'unknown']


class NoticeTaxonomy(models.Model):
    notice = models.ForeignKey(Notice, on_delete=models.CASCADE)
    taxonomy = models.ForeignKey(Taxonomy, on_delete=models.CASCADE)
    kind = models.CharField('词表类型', max_length=16)
    position = models.PositiveIntegerField('排序', default=0)

    class Meta:
        verbose_name = '通知标签'
        verbose_name_plural = '通知标签'
        unique_together = [('notice', 'taxonomy')]
        ordering = ['kind', 'position']


class Fact(models.Model):
    """通知下的一条事实。value 为展示值，quote 为原文引句，二者不互相冒充。"""
    id = models.CharField('事实 ID', max_length=120, primary_key=True)
    notice = models.ForeignKey(Notice, on_delete=models.CASCADE, related_name='facts')
    position = models.PositiveIntegerField('排序', default=0)
    kind = models.CharField('类别', max_length=24, default='other')
    label = models.CharField('栏目名', max_length=60, blank=True)
    value = models.TextField('展示值')
    quote = models.TextField('原文引句', blank=True)
    locator = models.CharField('原文定位', max_length=120, blank=True)
    source_url = models.URLField('条款出处', max_length=500, blank=True)
    basis = models.CharField('依据类型', max_length=60, blank=True)
    extras = models.JSONField('扩展字段', default=dict, blank=True)
    layout = models.JSONField('原字段顺序', default=list, blank=True)

    class Meta:
        verbose_name = '事实条款'
        verbose_name_plural = '事实条款'
        ordering = ['notice', 'position']
        indexes = [models.Index(fields=['notice', 'kind', 'position'])]

    def __str__(self):
        return f'{self.kind}: {self.value[:40]}'


class Profile(models.Model):
    """原文画像（按栏目归并的旧结构），迁移期原样保留。"""
    notice = models.OneToOneField(Notice, primary_key=True, on_delete=models.CASCADE, related_name='profile')
    payload = models.JSONField('原始画像', default=dict)

    class Meta:
        verbose_name = '正文画像'
        verbose_name_plural = '正文画像'


class ActivityGroup(models.Model):
    """学院拆分卡：只做展示分组，通知仍然属于原活动。"""
    id = models.CharField('拆分卡 ID', max_length=64, primary_key=True)
    activity = models.ForeignKey(Activity, verbose_name='所属活动', on_delete=models.CASCADE, related_name='groups')
    title = models.CharField('卡片标题', max_length=200)
    colleges = models.ManyToManyField(Taxonomy, blank=True, related_name='groups', limit_choices_to={'kind': 'college'})
    notices = models.ManyToManyField(Notice, blank=True, related_name='groups')
    position = models.PositiveIntegerField('排序', default=0)
    visibility = models.CharField('公开状态', max_length=10, choices=VISIBILITY, default='public')
    tags = models.JSONField('卡片标签', default=list, blank=True)

    class Meta:
        verbose_name = '学院拆分卡'
        verbose_name_plural = '学院拆分卡'
        ordering = ['position', 'id']

    def __str__(self):
        return self.title


class ImportBatch(models.Model):
    id = models.CharField('批次 ID', max_length=80, primary_key=True)
    input_hash = models.CharField('输入哈希', max_length=64, unique=True)
    source_revision = models.CharField('源库修订', max_length=64, blank=True)
    status = models.CharField('状态', max_length=20, default='running',
                             choices=[('running', '进行中'), ('done', '完成'), ('failed', '失败'), ('dry-run', '预演')])
    stats = models.JSONField('统计', default=dict, blank=True)
    note = models.TextField('说明', blank=True)
    created_at = models.DateTimeField('开始时间', auto_now_add=True)
    finished_at = models.DateTimeField('结束时间', null=True, blank=True)

    class Meta:
        verbose_name = '导入批次'
        verbose_name_plural = '导入批次'
        ordering = ['-created_at']


class Revision(models.Model):
    id = models.CharField('修订号', max_length=64, primary_key=True)
    parent_id = models.CharField('上一修订', max_length=64, blank=True)
    batch = models.ForeignKey(ImportBatch, null=True, blank=True, on_delete=models.SET_NULL, related_name='revisions')
    catalog_hash = models.CharField('目录哈希', max_length=64, blank=True)
    snapshot = models.BinaryField('快照（gzip）', null=True, blank=True)
    reason = models.TextField('修改原因', blank=True)
    origin = models.CharField('来源', max_length=40, blank=True)
    created_at = models.DateTimeField('创建时间', default=timezone.now)

    class Meta:
        verbose_name = '数据修订'
        verbose_name_plural = '数据修订'
        ordering = ['-created_at']


class ChangeLog(models.Model):
    revision = models.ForeignKey(Revision, on_delete=models.CASCADE, related_name='changes')
    entity_kind = models.CharField('对象类型', max_length=20)
    entity_id = models.CharField('对象 ID', max_length=80)
    action = models.CharField('动作', max_length=20)
    before_hash = models.CharField('修改前哈希', max_length=64, blank=True)
    after_hash = models.CharField('修改后哈希', max_length=64, blank=True)
    note = models.CharField('说明', max_length=200, blank=True)
    actor = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL, verbose_name='操作人')
    created_at = models.DateTimeField('时间', auto_now_add=True)

    class Meta:
        verbose_name = '修改记录'
        verbose_name_plural = '修改记录'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['entity_kind', 'entity_id'])]


class DraftChange(models.Model):
    """草稿：保存后不影响公开内容，发布时才写入正式字段并生成修订。

    payload 只放“哪些字段要改成什么”，发布时由 services.apply_draft 统一落库，
    这样后台、脚本、API 走同一条审计链路。
    """
    STATUS = [('draft', '草稿'), ('published', '已发布'), ('discarded', '已丢弃')]
    entity_kind = models.CharField('对象类型', max_length=20,
                                   choices=[('activity', '活动'), ('notice', '通知版本'),
                                            ('guide', '校园指南'), ('service', '校园服务')])
    entity_id = models.CharField('对象 ID', max_length=80)
    payload = models.JSONField('草稿内容', default=dict)
    note = models.TextField('修改说明', blank=True)
    status = models.CharField('状态', max_length=12, choices=STATUS, default='draft')
    author = models.ForeignKey('auth.User', null=True, blank=True, on_delete=models.SET_NULL,
                              verbose_name='保存人')
    created_at = models.DateTimeField('保存时间', auto_now_add=True)
    published_at = models.DateTimeField('发布时间', null=True, blank=True)
    revision = models.ForeignKey(Revision, null=True, blank=True, on_delete=models.SET_NULL,
                                 related_name='drafts', verbose_name='发布修订')

    class Meta:
        verbose_name = '内容草稿'
        verbose_name_plural = '内容草稿'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['entity_kind', 'entity_id', 'status'])]

    def __str__(self):
        return f'{self.get_entity_kind_display()} {self.entity_id} · {self.get_status_display()}'


class Guide(TimeStamped):
    id = models.CharField('指南 ID', max_length=64, primary_key=True)
    title = models.CharField('标题', max_length=160)
    subtitle = models.CharField('副标题', max_length=160, blank=True)
    category = models.CharField('分类', max_length=40, blank=True)
    summary = models.TextField('简介', blank=True)
    scope = models.TextField('适用范围', blank=True)
    caution = models.TextField('使用前提醒', blank=True)
    source_note = models.TextField('资料依据', blank=True)
    number = models.CharField('编号', max_length=8, blank=True)
    icon = models.CharField('图标', max_length=20, blank=True)
    tags = models.JSONField('标签', default=list, blank=True)
    position = models.PositiveIntegerField('排序', default=0)
    visibility = models.CharField('公开状态', max_length=10, choices=VISIBILITY, default='public')
    related_service = models.CharField('相关服务 ID', max_length=64, blank=True)
    draft = models.JSONField('未发布草稿', null=True, blank=True, editable=False, default=None)

    class Meta:
        verbose_name = '校园指南'
        verbose_name_plural = '校园指南'
        ordering = ['position', 'id']

    def __str__(self):
        return self.title


class GuideSection(models.Model):
    guide = models.ForeignKey(Guide, on_delete=models.CASCADE, related_name='sections')
    position = models.PositiveIntegerField('排序', default=0)
    title = models.CharField('步骤标题', max_length=120)
    kind = models.CharField('栏目类型', max_length=24, default='step')

    class Meta:
        verbose_name = '指南步骤'
        verbose_name_plural = '指南步骤'
        ordering = ['guide', 'position']

    def __str__(self):
        return self.title


class GuideBlock(models.Model):
    section = models.ForeignKey(GuideSection, on_delete=models.CASCADE, related_name='blocks')
    position = models.PositiveIntegerField('排序', default=0)
    text = models.TextField('内容')
    kind = models.CharField('类型', max_length=24, default='step')

    class Meta:
        verbose_name = '指南条目'
        verbose_name_plural = '指南条目'
        ordering = ['section', 'position']


class GuideFaq(models.Model):
    guide = models.ForeignKey(Guide, on_delete=models.CASCADE, related_name='faqs')
    position = models.PositiveIntegerField('排序', default=0)
    question = models.CharField('问题', max_length=200)
    answer = models.TextField('回答')

    class Meta:
        verbose_name = '指南问答'
        verbose_name_plural = '指南问答'
        ordering = ['guide', 'position']


class GuideSource(models.Model):
    guide = models.ForeignKey(Guide, on_delete=models.CASCADE, related_name='sources')
    label = models.CharField('资料名称', max_length=200)
    url = models.URLField('公开链接', max_length=500, blank=True)
    page_ref = models.CharField('页码/位置', max_length=80, blank=True)
    checked_on = models.DateField('核对日期', null=True, blank=True)
    note = models.CharField('说明', max_length=200, blank=True)

    class Meta:
        verbose_name = '指南出处'
        verbose_name_plural = '指南出处'
        ordering = ['guide', 'id']


class CampusService(TimeStamped):
    id = models.CharField('服务 ID', max_length=64, primary_key=True)
    name = models.CharField('名称', max_length=160)
    category = models.CharField('分类', max_length=40, blank=True)
    description = models.TextField('说明', blank=True)
    owner = models.CharField('负责单位', max_length=120, blank=True)
    phone = models.CharField('公开电话', max_length=60, blank=True)
    url = models.URLField('官方入口', max_length=500, blank=True)
    location = models.CharField('地点', max_length=160, blank=True)
    open_hours = models.CharField('开放时间', max_length=160, blank=True)
    source_url = models.URLField('来源链接', max_length=500, blank=True)
    source_label = models.CharField('来源名称', max_length=200, blank=True)
    source_date = models.DateField('来源日期', null=True, blank=True)
    checked_on = models.DateField('核对日期', null=True, blank=True)
    note = models.CharField('使用说明', max_length=300, blank=True)
    related_guide = models.CharField('相关指南 ID', max_length=64, blank=True)
    position = models.PositiveIntegerField('排序', default=0)
    visibility = models.CharField('公开状态', max_length=10, choices=VISIBILITY, default='public')

    class Meta:
        verbose_name = '校园服务'
        verbose_name_plural = '校园服务'
        ordering = ['position', 'id']

    def __str__(self):
        return self.name


class SiteMeta(models.Model):
    """单例行：站点信息、口径策略、展示开关。"""
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    site_name = models.CharField('站点名称', max_length=80, default='成都大学校园生活与活动')
    description = models.CharField('站点说明', max_length=200, blank=True)
    schema_version = models.CharField('数据版本', max_length=40, default='catalog-1')
    coverage = models.JSONField('覆盖范围', default=dict, blank=True)
    policies = models.JSONField('口径策略', default=dict, blank=True)
    display_options = models.JSONField('展示开关', default=dict, blank=True)
    current_revision = models.CharField('当前修订', max_length=64, blank=True)
    published_at = models.DateTimeField('最近发布', null=True, blank=True)

    class Meta:
        verbose_name = '站点设置'
        verbose_name_plural = '站点设置'

    def __str__(self):
        return self.site_name
