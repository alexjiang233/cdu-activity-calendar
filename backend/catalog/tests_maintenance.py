"""Full workbench replacement checks; mutations use Django's disposable database."""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from catalog import maintenance, audit
from catalog.models import Activity, Notice, Source, Fact, Guide, GuideSection, GuideBlock, Revision, SiteMeta, Taxonomy


class MaintenanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user=get_user_model().objects.create_superuser('owner',password='disposable-test-password')
        cls.activity=Activity.objects.create(id='a',title='校级演讲赛')
        cls.source=Source.objects.create(id='s',url='https://example.cdu.edu.cn/1.htm',title='校级通知')
        cls.notice=Notice.objects.create(id='n',activity=cls.activity,source=cls.source,year=2026)
        cls.fact=Fact.objects.create(id='f',notice=cls.notice,value='原要求')
        cls.guide=Guide.objects.create(id='g',title='指南')
        cls.section=GuideSection.objects.create(guide=cls.guide,title='第一步')
        cls.block=GuideBlock.objects.create(section=cls.section,text='打开入口')

    def setUp(self):self.client.force_login(self.user)

    def save(self,code,pk,data):
        url=f'/manage/settings/{code}/{pk}/'
        baseline=self.client.get(url).context['baseline']
        return self.client.post(url,{**data,'baseline':baseline})

    def test_every_maintenance_list_create_and_edit_renders(self):
        self.assertEqual(self.client.get('/manage/settings/').status_code,200)
        for code,(model,title,fields,_,_) in maintenance.REGISTRY.items():
            with self.subTest(code=code):
                self.assertEqual(self.client.get(f'/manage/settings/{code}/').status_code,200)
                if fields and not(code=='site' and model.objects.exists()):
                    self.assertEqual(self.client.get(f'/manage/settings/{code}/new/').status_code,200)
                obj=model.objects.first()
                if obj:self.assertEqual(self.client.get(f'/manage/settings/{code}/{obj.pk}/').status_code,200)
        for code in ('activity','guide','service','notice'):
            self.assertEqual(self.client.get('/manage/new/'+code+'/').status_code,200)

    def test_add_activity_notice_and_fact_end_to_end(self):
        result=self.client.post('/manage/new/activity/',{'title':'游泳比赛','summary':'游泳竞赛',
            'category':'','tags':'运动','editorial_note':'','position':0,'visibility':'public','kind':'notice','material_ids':'[]'})
        self.assertEqual(result.status_code,302)
        activity=Activity.objects.get(title='游泳比赛')
        self.assertEqual(activity.visibility,'hidden')
        result=self.client.post('/manage/new/notice/',{'activity':activity.pk,'source':self.source.pk,
             'year':2026,'published':'2026-10-21','audience':'本科生','deadline_kind':'','position':0,'visibility':'public'})
        self.assertEqual(result.status_code,302)
        notice=activity.notices.get()
        self.assertContains(self.client.get(f'/manage/activity/{activity.pk}/'),'通知版本 <span>1</span>',html=False)
        result=self.client.post('/manage/settings/fact/new/',{'notice':notice.pk,'kind':'requirement',
            'label':'材料','value':'学生证','quote':'携带学生证','position':0})
        self.assertEqual(result.status_code,302)
        self.assertEqual(notice.facts.get().value,'学生证')
        self.assertEqual(Revision.objects.count(),3)

    def test_new_guide_step_and_block(self):
        result=self.client.post('/manage/new/guide/',{'title':'图书馆指南','category':'学习','visibility':'public','position':0,'tags':'[]'})
        self.assertEqual(result.status_code,302)
        guide=Guide.objects.get(title='图书馆指南')
        self.assertEqual(guide.visibility,'hidden')
        result=self.client.post('/manage/settings/section/new/',{'guide':guide.pk,'title':'第一步','kind':'step','position':0})
        self.assertEqual(result.status_code,302)
        section=guide.sections.get()
        result=self.client.post('/manage/settings/block/new/',{'section':section.pk,'text':'打开检索入口','kind':'step','position':0})
        self.assertEqual(result.status_code,302)
        self.assertEqual(section.blocks.get().text,'打开检索入口')

    def test_support_edits_refresh_search_and_restore(self):
        result=self.save('fact','f',{'notice':'n','kind':'requirement','label':'材料','value':'1920×1080','quote':'原证据','position':0})
        self.assertEqual(result.status_code,302)
        self.notice.refresh_from_db()
        self.assertIn('1920',self.notice.search_text)
        revision=Revision.objects.first()
        self.assertEqual(self.client.post('/manage/history/'+revision.pk+'/').status_code,302)
        self.fact.refresh_from_db();self.assertEqual(self.fact.value,'原要求')

    def test_remove_leaf_is_recoverable_parent_cannot_cascade(self):
        page=self.client.get('/manage/settings/block/'+str(self.block.pk)+'/')
        result=self.client.post(f'/manage/settings/block/{self.block.pk}/remove/',{'baseline':page.context['baseline']})
        self.assertEqual(result.status_code,302)
        self.assertFalse(GuideBlock.objects.filter(pk=self.block.pk).exists())
        revision=Revision.objects.first()
        self.assertEqual(self.client.post('/manage/history/'+revision.pk+'/').status_code,302)
        self.assertEqual(GuideBlock.objects.get(pk=self.block.pk).text,'打开入口')
        page=self.client.get(f'/manage/settings/section/{self.section.pk}/')
        self.assertFalse(page.context['removable'])
        self.assertEqual(self.client.post(f'/manage/settings/section/{self.section.pk}/remove/',{'baseline':page.context['baseline']}).status_code,403)
        self.assertTrue(GuideBlock.objects.filter(pk=self.block.pk).exists())

    def test_editor_conflict_rejects_overwrite(self):
        url='/manage/settings/source/s/'
        baseline=self.client.get(url).context['baseline']
        Source.objects.filter(pk='s').update(title='别的窗口更新了')
        response=self.client.post(url,{'baseline':baseline,'url':self.source.url,'title':'覆盖','publisher':''})
        self.assertEqual(response.status_code,409)
        self.assertEqual(Source.objects.get(pk='s').title,'别的窗口更新了')

    def test_old_admin_routes_only_redirect_and_reject_old_posts(self):
        self.assertRedirects(self.client.get('/admin/catalog/activity/a/change/'),'/manage/activity/a/')
        self.assertEqual(self.client.post('/admin/catalog/activity/a/change/',{'title':'不得改'}).status_code,405)
        self.assertEqual(Activity.objects.get(pk='a').title,'校级演讲赛')

    def test_hidden_notice_is_not_exposed_but_staff_can_restore(self):
        Notice.objects.filter(pk='n').update(visibility='hidden')
        self.assertEqual(self.client.get('/api/v1/activities/a/notices/n/').status_code,404)
        self.assertContains(self.client.get('/manage/activity/a/'),'通知版本 <span>1</span>',html=False)

    def test_group_rejects_unrelated_notices(self):
        other=Activity.objects.create(id='other',title='别的活动')
        result=self.client.post('/manage/settings/group/new/',{'title':'错误分组','activity':other.pk,
                  'visibility':'public','position':0,'notices':['n'],'tags':''})
        self.assertEqual(result.status_code,200)
        self.assertContains(result,'请选择属于该活动的通知')

    def test_permissions_cannot_create_or_escalate_without_rights(self):
        user=get_user_model().objects.create_user('staff',is_staff=True,password='temporary-test-only')
        user.user_permissions.add(Permission.objects.get(codename='view_activity',content_type__app_label='catalog'))
        self.client.force_login(user)
        self.assertEqual(self.client.get('/manage/new/activity/').status_code,403)
        self.assertEqual(self.client.get('/manage/settings/user/').status_code,403)
        self.assertEqual(self.client.post('/manage/settings/source/new/',{}).status_code,403)
        self.assertEqual(self.client.post('/manage/settings/password/'+str(self.user.pk)+'/',{}).status_code,403)

    def test_account_passwords_never_enter_revision_snapshots(self):
        response=self.client.post('/manage/settings/user/new/',{'username':'new-editor','email':'','is_active':'on','is_staff':'on',
                  'password1':'random-user-pass-634','password2':'random-user-pass-634'})
        self.assertEqual(response.status_code,302)
        user=get_user_model().objects.get(username='new-editor')
        self.assertTrue(user.check_password('random-user-pass-634'))
        import gzip
        snapshot=gzip.decompress(bytes(Revision.objects.first().snapshot)).decode()
        self.assertNotIn('random-user-pass',snapshot)
        self.assertNotIn('pbkdf2_',snapshot)
