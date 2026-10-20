"""P1-4：草稿不公开、发布才生效、改动留修订、可回退。"""
import json

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from catalog import audit, drafts, services
from catalog.models import (Activity, ChangeLog, DraftChange, Notice, Revision, SiteMeta,
                            Taxonomy)


class PublishFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_superuser('tester', 't@example.com', 'pw-123456789')
        cls.category = Taxonomy.objects.create(kind='category', code='career', label='生涯就业')
        cls.activity = Activity.objects.create(id='act-x', title='原标题', category=cls.category,
                                               visibility='public', summary='原摘要',
                                               featured=True, spotlight=True)
        Notice.objects.create(id='n-x', activity=cls.activity, year=2026, published='2026-09-01')
        SiteMeta.objects.create(id=1, current_revision='rev-initial')

    def setUp(self):
        self.client.force_login(self.user)

    def _post(self, **overrides):
        data = {
            'id': 'act-x', 'title': '新标题', 'kind': 'notice', 'category': self.category.pk,
            'summary': '新摘要', 'tags': json.dumps(['官方公告']), 'editorial_note': '',
            'featured': 'on', 'spotlight': 'on', 'position': '0', 'visibility': 'public',
            'material_ids': '[]', 'extras': '{}', 'layout': '[]',
            'notices-TOTAL_FORMS': '0', 'notices-INITIAL_FORMS': '0',
            'notices-MIN_NUM_FORMS': '0', 'notices-MAX_NUM_FORMS': '1000',
        }
        data['tags']='官方公告'
        data['action']='save' if '_save_draft' in overrides else 'publish'
        data['baseline']=self.client.get('/manage/activity/act-x/').context['baseline']
        data.update(overrides)
        return self.client.post(reverse('workbench:edit', args=['activity','act-x']), data)

    def test_admin_save_writes_revision_and_changelog(self):
        before_revisions = Revision.objects.count()
        response = self._post(_save='保存')
        self.assertEqual(response.status_code, 302)
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.title, '新标题')
        self.assertEqual(Revision.objects.count(), before_revisions + 1)
        change = ChangeLog.objects.filter(entity_kind='activity', entity_id='act-x').first()
        self.assertIsNotNone(change)
        self.assertEqual(change.action, 'update')

    def test_save_draft_does_not_change_public_content(self):
        response = self._post(_save_draft='保存草稿（不公开）', title='还没定稿的标题')
        self.assertEqual(response.status_code, 302)
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.title, '原标题')
        draft = DraftChange.objects.get()
        self.assertEqual(draft.status, 'draft')
        self.assertEqual(draft.payload['title'], '还没定稿的标题')
        # 公开接口仍返回旧标题
        payload = self.client.get('/api/v1/activities/act-x/').json()
        self.assertEqual(payload['entry']['title'], '原标题')

    def test_publishing_draft_updates_public_and_revision(self):
        self._post(_save_draft='保存草稿（不公开）', title='定稿标题')
        draft = DraftChange.objects.get()
        drafts.publish(draft, actor=self.user)
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.title, '定稿标题')
        draft.refresh_from_db()
        self.assertEqual(draft.status, 'published')
        self.assertIsNotNone(draft.revision_id)
        meta = SiteMeta.objects.first()
        self.assertEqual(meta.current_revision, draft.revision_id)
        payload = self.client.get('/api/v1/activities/act-x/').json()
        self.assertEqual(payload['entry']['title'], '定稿标题')

    def test_restore_creates_new_revision_and_reverts(self):
        response = self._post(_save='保存')
        self.assertEqual(response.status_code, 302)
        revision = Revision.objects.exclude(pk='rev-initial').first()
        rollback_ids = audit.restore(revision, actor=self.user)
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.title, '原标题')
        rollback = Revision.objects.get(pk=rollback_ids[0])
        self.assertIn('回退', rollback.reason)
        self.assertEqual(SiteMeta.objects.first().current_revision, rollback.id)

    def test_draft_preview_shows_draft_without_saving(self):
        self._post(_save_draft='保存草稿（不公开）', title='预览用标题')
        draft = DraftChange.objects.get()
        preview = drafts.preview(draft)
        self.assertEqual(preview['entity']['title'], '预览用标题')
        self.assertEqual(preview['entry']['title'], '预览用标题')
        self.activity.refresh_from_db()
        self.assertEqual(self.activity.title, '原标题')
