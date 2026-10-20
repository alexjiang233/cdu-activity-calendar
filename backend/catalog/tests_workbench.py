"""Workbench rendering, permission and lossless publish/restore checks on a disposable DB."""
from django.test import TestCase
from django.contrib.auth import get_user_model
from catalog import audit, drafts
from catalog.models import Activity, Notice, Source, Fact, Guide, GuideSection, GuideBlock, GuideFaq, CampusService, DraftChange, Revision


class WorkbenchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user=get_user_model().objects.create_superuser('editor',password='temporary-test-only')
        cls.activity=Activity.objects.create(id='workbench-a',title='校园演讲赛',summary='原摘要')
        cls.source=Source.objects.create(id='workbench-s',url='https://example.cdu.edu.cn/a.htm')
        cls.notice=Notice.objects.create(id='workbench-n',activity=cls.activity,source=cls.source,year=2026)
        cls.fact=Fact.objects.create(id='workbench-f',notice=cls.notice,kind='requirement',label='材料',value='原条目',quote='原证据')
        cls.guide=Guide.objects.create(id='workbench-g',title='校园网')
        cls.section=GuideSection.objects.create(guide=cls.guide,title='连接网络')
        cls.block=GuideBlock.objects.create(section=cls.section,text='打开官方入口')
        cls.faq=GuideFaq.objects.create(guide=cls.guide,question='密码忘了怎么办？',answer='使用官方找回入口。')
        cls.service=CampusService.objects.create(id='workbench-service',name='图书馆')

    def setUp(self):
        self.client.force_login(self.user)

    def test_all_pages_render_with_pending_draft(self):
        drafts.save_draft('notice',self.notice.pk,{'audience':'本科生'},author=self.user)
        for path in ('','activity/','guide/','service/','history/','activity/workbench-a/',
                     'notice/workbench-n/','guide/workbench-g/','service/workbench-service/'):
            with self.subTest(path=path):
                self.assertEqual(self.client.get('/manage/'+path).status_code,200)
        self.assertContains(self.client.get('/manage/guide/workbench-g/'),'密码忘了怎么办？')

    def test_anonymous_and_nonstaff_cannot_edit(self):
        self.client.logout()
        self.assertEqual(self.client.get('/manage/').status_code,302)
        user=get_user_model().objects.create_user('visitor',password='test')
        self.client.force_login(user)
        self.assertEqual(self.client.post('/manage/activity/workbench-a/',{}).status_code,403)

    def post_activity(self,action='save',baseline=None):
        page=self.client.get('/manage/activity/workbench-a/')
        return self.client.post('/manage/activity/workbench-a/',{
            'title':'精简标题','summary':'清楚的摘要','category':'','tags':'创作，团队',
            'editorial_note':'','featured':'on','spotlight':'on','position':0,'visibility':'public',
            'baseline':baseline or page.context['baseline'],'action':action,'kind':'notice','material_ids':'[]'})

    def test_draft_does_not_publish_and_reopens(self):
        self.assertEqual(self.post_activity().status_code,302)
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.title,'校园演讲赛')
        self.assertEqual(Revision.objects.count(),0)
        page=self.client.get('/manage/activity/workbench-a/')
        self.assertEqual(page.context['form']['title'].value(),'精简标题')
        self.assertEqual(page.context['form']['tags'].value(),'创作，团队')
        self.assertContains(self.client.get('/manage/'),'精简标题')
        self.assertEqual(self.post_activity('publish').status_code,302)
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.title,'精简标题')
        self.assertEqual(self.activity.tags,['创作','团队'])
        self.assertEqual(DraftChange.objects.filter(status='draft').count(),0)

    def test_stale_editor_and_stale_draft_are_rejected(self):
        baseline=self.client.get('/manage/activity/workbench-a/').context['baseline']
        d=drafts.save_draft('activity',self.activity.pk,{'title':'旧草稿'})
        audit.apply_updates('activity',self.activity,{'summary':'其他人改了'},reason='test',origin='test')
        self.assertEqual(self.post_activity(baseline=baseline).status_code,409)
        with self.assertRaises(ValueError):drafts.publish(d)
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.title,'校园演讲赛')

    def test_nested_fact_and_guide_publish_restore(self):
        for kind,entity,key in [('notice',self.notice,'facts'),('guide',self.guide,'sections')]:
            before=audit.snapshot(kind,entity)
            import copy
            payload=copy.deepcopy(before)
            if kind=='notice':payload['facts'][0]['value']='新条目'
            else:payload['sections'][0]['blocks'][0]['text']='新步骤'
            d=drafts.save_draft(kind,entity.pk,payload)
            self.assertEqual(audit.snapshot(kind,entity),before)
            d=drafts.publish(d)
            self.assertNotEqual(audit.snapshot(kind,entity)[key],before[key])
            self.assertEqual(self.client.get('/manage/history/'+d.revision_id+'/').status_code,200)
            audit.restore(d.revision)
            entity.refresh_from_db()
            self.assertEqual(audit.snapshot(kind,entity),before)

    def test_cross_notice_fact_cannot_be_overwritten(self):
        other=Notice.objects.create(id='other',activity=self.activity)
        payload=audit.snapshot('notice',other)
        payload['facts']=audit.snapshot('notice',self.notice)['facts']
        with self.assertRaises(ValueError):audit.apply_updates('notice',other,payload,reason='test',origin='test')
        self.fact.refresh_from_db()
        self.assertEqual(self.fact.value,'原条目')

    def test_newer_draft_cannot_be_overwritten_and_can_be_discarded(self):
        baseline=self.client.get('/manage/activity/workbench-a/').context['baseline']
        d=drafts.save_draft('activity',self.activity.pk,{'title':'另一个窗口的草稿'})
        self.assertEqual(self.post_activity(baseline=baseline).status_code,409)
        self.assertEqual(self.client.post('/manage/activity/workbench-a/discard/').status_code,302)
        d.refresh_from_db()
        self.assertEqual(d.status,'discarded')
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.title,'校园演讲赛')
        self.assertEqual(self.post_activity().status_code,302)

    def test_bulk_hide_keeps_rows_and_records_history(self):
        result=self.client.post('/manage/activity/bulk/',{'selected':[self.activity.pk],'action':'hide'})
        self.assertEqual(result.status_code,302)
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.visibility,'hidden')
        self.assertTrue(Notice.objects.filter(pk=self.notice.pk).exists())
        revision=Revision.objects.first()
        result=self.client.post('/manage/history/'+revision.pk+'/')
        self.assertEqual(result.status_code,302)
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.visibility,'public')
