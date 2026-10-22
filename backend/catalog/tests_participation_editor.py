"""End-to-end acceptance tests for the per-notice curated participation editor."""
from datetime import date

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from catalog import audit, drafts, services
from catalog.models import Activity, DraftChange, Fact, Notice, Profile, Source


class ParticipationEditorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.editor = get_user_model().objects.create_superuser(
            'participation-editor-test', password='temporary-test-only'
        )
        cls.activity = Activity.objects.create(
            id='participation-a', title='版本隔离测试活动', summary='原活动摘要'
        )
        cls.other_activity = Activity.objects.create(
            id='participation-b', title='其他活动', summary='不得跨活动修改'
        )
        cls.source = Source.objects.create(
            id='participation-source-a', url='https://example.test/source-a', title='甲通知'
        )
        cls.other_source = Source.objects.create(
            id='participation-source-b', url='https://example.test/source-b', title='乙通知'
        )
        cls.notice = Notice.objects.create(
            id='participation-n26a', activity=cls.activity, source=cls.source,
            year=2026, published=date(2026, 1, 10), audience='原参与对象',
            extras={'registration_windows': [{'start': '2026-01-01', 'end': '2026-01-31'}],
                    'keep_me': {'source_key': 'preserve'}},
        )
        cls.second_notice = Notice.objects.create(
            id='participation-n26b', activity=cls.activity, source=cls.source,
            year=2026, published=date(2026, 3, 10), audience='第二份通知对象',
            extras={'curated_details': {'enabled': True, 'fields': {
                'event_time': '8月第二份时间', 'location': '第二份地点'}}},
        )
        cls.old_notice = Notice.objects.create(
            id='participation-n25', activity=cls.activity, source=cls.source,
            year=2025, published=date(2025, 4, 10), audience='往年参与对象',
            extras={'curated_details': {'enabled': True, 'fields': {
                'event_time': '4月往年时间', 'location': '往年地点'}}},
        )
        cls.foreign_notice = Notice.objects.create(
            id='participation-foreign', activity=cls.other_activity,
            source=cls.other_source, year=2026, published=date(2026, 2, 1),
        )
        cls.display_owned_notice = Notice.objects.create(
            id='participation-display-owned', activity=cls.other_activity,
            display_activity=cls.activity, source=cls.other_source, year=2024,
            published=date(2024, 2, 1),
        )
        cls.legacy_fact = Fact.objects.create(
            id='participation-fact-old', notice=cls.notice, kind='schedule',
            label='旧时间地点', value='5月旧方案在旧图书馆开展，忽略该段',
            quote='来源中的旧版长句', position=1,
        )
        Profile.objects.create(notice=cls.notice, payload={'sections': [{
            'kind': 'schedule', 'title': '旧画像',
            'items': [{'text': '5月旧画像时间，旧场地不再采用'}],
        }]})

    def setUp(self):
        self.client.force_login(self.editor)

    def participation_url(self, activity=None):
        return reverse('workbench:participation', args=[activity or self.activity.pk])

    def participation_post(self, *, notice=None, action='save', baseline=None, **overrides):
        url = self.participation_url()
        query = {'notice': notice or self.notice.pk}
        page = self.client.get(url, query)
        self.assertEqual(page.status_code, 200)
        data = {
            'baseline': baseline or page.context['baseline'], 'action': action,
            # The selected editor renders these as disabled fields. Forged values must be ignored.
            'activity': self.other_activity.pk, 'source': self.other_source.pk,
            'year': '2026', 'published': '2026-01-10',
            'deadline': '2099-05-30T23:59', 'deadline_kind': 'registration',
            'stage_start': '2027-05-05', 'stage_end': '2027-05-20',
            'audience': 'CURATED_AUDIENCE_KEY', 'position': '0', 'visibility': 'public',
            'curated_enabled': 'on',
            'curated_event_time': '2027年5月5日至20日，按通知安排参加',
            'curated_location': 'CURATED_LOCATION_KEY · 图书馆A区',
            'curated_registration': 'CURATED_REGISTRATION_KEY · 在线表单报名',
            'curated_conditions': 'CURATED_CONDITION_KEY · 本校在读学生',
            'curated_materials': '准备学生证',
            'curated_benefits': '完成活动可获得实践证明',
            'curated_fees': '', 'curated_contact': '咨询活动负责人',
            'curated_notes': '',
        }
        data.update(overrides)
        return self.client.post(url + f'?notice={query["notice"]}', data)

    def test_editor_pages_version_picker_and_cross_activity_isolation(self):
        activity_page = self.client.get(reverse('workbench:edit', args=['activity', self.activity.pk]))
        self.assertEqual(activity_page.status_code, 200)
        self.assertContains(activity_page, '时间、地点与报名')

        page = self.client.get(self.participation_url(), {'notice': self.second_notice.pk})
        self.assertEqual(page.status_code, 200)
        self.assertEqual(page.context['obj'].pk, self.second_notice.pk)
        self.assertContains(page, '正在编辑哪一届／哪份通知')
        self.assertContains(page, self.notice.pk)
        self.assertContains(page, self.old_notice.pk)
        self.assertEqual(self.client.get(self.participation_url(),
                                         {'notice': self.foreign_notice.pk}).status_code, 404)
        self.assertEqual(self.client.get(self.participation_url(),
                                         {'notice': 'does-not-exist'}).status_code, 404)

    def test_display_activity_owns_editor_heading_navigation_and_return_link(self):
        response = self.client.get(self.participation_url(), {'notice': self.display_owned_notice.pk})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '版本隔离测试活动 · 2024 年通知')
        self.assertContains(response, reverse('workbench:edit', args=['activity', self.activity.pk]))
        self.assertContains(response, reverse('workbench:participation', args=[self.activity.pk]) +
                            '?notice=participation-display-owned')
        self.assertNotContains(response, reverse('workbench:edit', args=['activity', self.other_activity.pk]))

        response = self.participation_post(notice=self.second_notice.pk)
        self.assertEqual(response.status_code, 302)
        self.notice.refresh_from_db()
        self.second_notice.refresh_from_db()
        self.old_notice.refresh_from_db()
        self.assertIsNone(self.notice.extras.get('curated_details'))
        second_draft = DraftChange.objects.get(entity_kind='notice', entity_id=self.second_notice.pk,
                                               status='draft')
        self.assertEqual(second_draft.payload['extras']['curated_details']['fields']['location'],
                         'CURATED_LOCATION_KEY · 图书馆A区')
        self.assertEqual(self.second_notice.extras['curated_details']['fields']['location'], '第二份地点')
        self.assertEqual(self.old_notice.extras['curated_details']['fields']['location'], '往年地点')
        self.second_notice.refresh_from_db()
        self.assertEqual(self.second_notice.activity_id, self.activity.pk)
        self.assertEqual(self.second_notice.source_id, self.source.pk)

    def test_authentication_permissions_and_csrf_are_enforced(self):
        client = Client()
        self.assertEqual(client.get(self.participation_url()).status_code, 302)
        visitor = get_user_model().objects.create_user('participation-visitor', password='test-only')
        client.force_login(visitor)
        self.assertEqual(client.get(self.participation_url()).status_code, 403)

        limited = get_user_model().objects.create_user('participation-limited', is_staff=True,
                                                       password='test-only')
        from django.contrib.auth.models import Permission
        limited.user_permissions.add(*Permission.objects.filter(
            content_type__app_label='catalog', codename__in=('change_activity', 'view_activity')
        ))
        client.force_login(limited)
        self.assertEqual(client.get(self.participation_url()).status_code, 403)

        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.editor)
        page = csrf_client.get(self.participation_url())
        self.assertEqual(page.status_code, 200)
        payload = {'baseline': page.context['baseline'], 'action': 'save',
                   'curated_enabled': 'on', 'curated_event_time': '5月安排'}
        self.assertEqual(csrf_client.post(self.participation_url() +
                                          f'?notice={self.notice.pk}', payload).status_code, 403)
        self.notice.refresh_from_db()
        self.assertFalse(DraftChange.objects.filter(entity_kind='notice', entity_id=self.notice.pk).exists())

    def test_save_then_publish_curated_dates_search_months_and_restore(self):
        original = audit.snapshot('notice', self.notice)
        legacy_fact_value = self.legacy_fact.value
        legacy_profile = self.notice.profile.payload

        saved = self.participation_post()
        self.assertEqual(saved.status_code, 302)
        self.notice.refresh_from_db()
        self.assertEqual(audit.snapshot('notice', self.notice), original)
        draft = DraftChange.objects.get(entity_kind='notice', entity_id=self.notice.pk, status='draft')
        self.assertEqual(draft.payload['extras']['keep_me'], {'source_key': 'preserve'})
        self.assertEqual(draft.payload['extras']['curated_details']['fields']['location'],
                         'CURATED_LOCATION_KEY · 图书馆A区')

        published = self.participation_post(action='publish')
        self.assertEqual(published.status_code, 302)
        self.notice.refresh_from_db()
        draft.refresh_from_db()
        published_draft = DraftChange.objects.get(entity_kind='notice', entity_id=self.notice.pk,
                                                  status='published')
        self.assertEqual(draft.status, 'discarded')
        self.assertEqual(self.notice.stage_start.isoformat(), '2027-05-05')
        self.assertEqual(self.notice.stage_end.isoformat(), '2027-05-20')
        self.assertEqual(self.notice.extras['keep_me'], {'source_key': 'preserve'})
        self.assertEqual(self.legacy_fact.value, legacy_fact_value)
        self.assertEqual(self.notice.profile.payload, legacy_profile)

        detail_response = self.client.get('/api/v1/activities/',
                                          {'q': 'CURATED_LOCATION_KEY', 'view': 'registration'})
        self.assertEqual(detail_response.status_code, 200)
        rows = detail_response.json()['results']
        entry = next(row for row in rows if row['id'] == self.activity.pk)
        version = next(row for row in entry['versions'] if row['notice_id'] == self.notice.pk)
        self.assertEqual(version['stage_start'], '2027-05-05')
        self.assertEqual(version['stage_end'], '2027-05-20')
        self.assertTrue(version['editorial_curated'])
        self.assertEqual(version['registration_windows'], [])
        self.assertTrue(any('CURATED_CONDITION_KEY' in item['text']
                            for section in version['content_profile']['sections']
                            for item in section['items']))

        exact = self.client.get(f'/api/v1/activities/{self.activity.pk}/',
                                {'notice': self.notice.pk}).json()['notice']
        body = json_text = str(exact['content_profile']) + str(exact['participation_facts'])
        self.assertIn('CURATED_LOCATION_KEY', body)
        self.assertNotIn('旧方案在旧图书馆', body)
        self.assertNotIn('旧画像时间', body)
        self.assertEqual(exact['stage_start'], '2027-05-05')
        self.assertEqual(exact['deadline'][:10], '2099-05-30')

        self.assertEqual(self.client.get('/api/v1/activities/', {'q': 'CURATED_CONDITION_KEY'}).json()['count'], 1)
        self.assertEqual(self.client.get('/api/v1/activities/', {'q': '旧方案在旧图书馆'}).json()['count'], 0)
        may = self.client.get('/api/v1/activities/', {'month': '5', 'month_basis': 'seasonal'}).json()
        self.assertIn(self.activity.pk, [row['id'] for row in may['results']])
        january = self.client.get('/api/v1/activities/', {'month': '1', 'month_basis': 'seasonal'}).json()
        self.assertNotIn(self.activity.pk, [row['id'] for row in january['results']])

        revision = published_draft.revision
        self.assertIsNotNone(revision)
        audit.restore(revision, actor=self.editor)
        self.notice.refresh_from_db()
        self.assertEqual(audit.snapshot('notice', self.notice), original)
        restored = self.client.get(f'/api/v1/activities/{self.activity.pk}/',
                                   {'notice': self.notice.pk}).json()['notice']
        restored_text = str(restored['content_profile']) + str(restored['participation_facts'])
        self.assertNotIn('CURATED_LOCATION_KEY', restored_text)
        self.assertIn('旧方案在旧图书馆', restored_text)

    def test_stale_baseline_is_rejected_without_saving(self):
        page = self.client.get(self.participation_url(), {'notice': self.notice.pk})
        baseline = page.context['baseline']
        Notice.objects.filter(pk=self.notice.pk).update(audience='另一个窗口已修改')
        response = self.participation_post(baseline=baseline)
        self.assertEqual(response.status_code, 409)
        self.assertContains(response, '这条内容刚刚发生了变化', status_code=409)
        self.notice.refresh_from_db()
        self.assertEqual(self.notice.audience, '另一个窗口已修改')
        self.assertFalse(DraftChange.objects.filter(entity_kind='notice', entity_id=self.notice.pk).exists())

    def test_new_notice_form_preserves_extra_participation_fields(self):
        url = reverse('workbench:create', args=['notice']) + f'?activity={self.activity.pk}'
        page = self.client.get(url)
        self.assertEqual(page.status_code, 200)
        data = {
            'activity': self.activity.pk, 'source': self.source.pk, 'year': '2027',
            'published': '2027-01-03', 'deadline': '2027-05-30T23:59',
            'deadline_kind': 'registration', 'stage_start': '2027-05-05',
            'stage_end': '2027-05-20', 'audience': '新通知对象', 'position': '3',
            'visibility': 'public', 'curated_enabled': 'on',
            'curated_event_time': '5月新通知活动时段', 'curated_location': 'NEW_NOTICE_LOCATION',
            'curated_registration': 'NEW_NOTICE_REGISTRATION',
            'curated_conditions': 'NEW_NOTICE_CONDITION',
            'curated_materials': 'NEW_NOTICE_MATERIAL', 'curated_benefits': '',
            'curated_fees': '', 'curated_contact': '', 'curated_notes': '',
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 302)
        created = Notice.objects.filter(activity=self.activity, year=2027).latest('created_at')
        fields = created.extras['curated_details']['fields']
        self.assertTrue(created.extras['curated_details']['enabled'])
        self.assertEqual(fields['location'], 'NEW_NOTICE_LOCATION')
        self.assertEqual(fields['registration'], 'NEW_NOTICE_REGISTRATION')
        self.assertEqual(fields['conditions'], 'NEW_NOTICE_CONDITION')
        self.assertEqual(fields['materials'], 'NEW_NOTICE_MATERIAL')
        self.assertEqual(created.stage_start.isoformat(), '2027-05-05')

    def test_activity_display_choices_save_as_draft_then_hide_without_deleting_sources(self):
        from catalog.workbench import ContentForm
        expected = {
            'home': (True, True, 'public'), 'featured': (True, False, 'public'),
            'all': (False, False, 'public'), 'hidden': (False, False, 'hidden'),
        }
        for choice, state in expected.items():
            form = ContentForm(data={'title': self.activity.title, 'summary': self.activity.summary,
                'category': '', 'tags': '', 'editorial_note': '', 'position': '0',
                'kind': 'notice', 'split_by_college': '', 'material_ids': '[]', 'visibility': 'public',
                'display_choice': choice}, instance=self.activity)
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual((form.cleaned_data['featured'], form.cleaned_data['spotlight'],
                              form.cleaned_data['visibility']), state)

        self.activity.refresh_from_db()
        before = audit.snapshot('activity', self.activity)
        before_notice = audit.snapshot('notice', self.notice)
        page = self.client.get(reverse('workbench:edit', args=['activity', self.activity.pk]))
        data = {'baseline': page.context['baseline'], 'action': 'save', 'title': self.activity.title,
                'summary': self.activity.summary, 'category': '', 'tags': '', 'editorial_note': '',
                'position': '0', 'kind': 'notice', 'split_by_college': '', 'material_ids': '[]', 'visibility': 'public',
                'display_choice': 'hidden'}
        self.assertEqual(self.client.post(reverse('workbench:edit', args=['activity', self.activity.pk]),
                                          data).status_code, 302)
        self.activity.refresh_from_db()
        self.assertEqual(audit.snapshot('activity', self.activity), before)
        draft = DraftChange.objects.get(entity_kind='activity', entity_id=self.activity.pk, status='draft')
        self.assertEqual((draft.payload['featured'], draft.payload['spotlight'], draft.payload['visibility']),
                         (False, False, 'hidden'))
        self.assertTrue(Notice.objects.filter(pk=self.notice.pk).exists())
        self.assertTrue(Fact.objects.filter(pk=self.legacy_fact.pk).exists())
        self.assertEqual(audit.snapshot('notice', self.notice), before_notice)

        page = self.client.get(reverse('workbench:edit', args=['activity', self.activity.pk]))
        data['baseline'] = page.context['baseline']
        data['action'] = 'publish'
        self.assertEqual(self.client.post(reverse('workbench:edit', args=['activity', self.activity.pk]),
                                          data).status_code, 302)
        self.activity.refresh_from_db()
        self.assertEqual((self.activity.featured, self.activity.spotlight, self.activity.visibility),
                         (False, False, 'hidden'))
        self.assertTrue(Notice.objects.filter(pk=self.notice.pk).exists())
        self.assertTrue(Fact.objects.filter(pk=self.legacy_fact.pk).exists())

    def test_activity_list_refinement_filters_and_links_to_participation_editor(self):
        response = self.client.get(reverse('workbench:list', args=['activity']), {'refinement': 'some'})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse('workbench:participation', args=[self.activity.pk]))
        self.assertNotContains(response, reverse('workbench:participation', args=[self.other_activity.pk]))
        needs = self.client.get(reverse('workbench:list', args=['activity']), {'refinement': 'needs'})
        self.assertContains(needs, self.other_activity.pk)
        self.assertNotContains(needs, self.activity.pk)

    def test_annual_month_calendar_does_not_return_superseded_facts(self):
        self.notice.extras = {'curated_details': {'enabled': True, 'fields': {
            'event_time': '5月5日至5月20日，使用新安排', 'location': '新地点'}}}
        self.notice.stage_start = date(2027, 5, 5)
        self.notice.stage_end = date(2027, 5, 20)
        self.notice.save()
        from catalog.indexing import refresh_notice
        refresh_notice(self.notice)
        result = services.calendar_annual(5)
        row = next(r for r in result['results'] if r['entry']['id'] == self.activity.pk)
        signals = [signal for version in row['versions'] for signal in version['signals']]
        self.assertTrue(any(signal.get('kind') == 'event' for signal in signals))
        self.assertFalse(any('旧方案在旧图书馆' in signal.get('text', '') for signal in signals))

