"""Public projection tests for one current notice per activity/group and year."""
from datetime import date
from pathlib import Path
import sys

from django.contrib.auth import get_user_model
from django.test import TestCase

from catalog import services
from catalog.models import Activity, ActivityGroup, Fact, Notice, Source


class LatestPublicNoticePolicyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.owner = Activity.objects.create(id='latest-owner', title='展示活动', visibility='public')
        cls.origin = Activity.objects.create(id='latest-origin', title='原活动', visibility='public')
        cls.other = Activity.objects.create(id='latest-other', title='另一活动', visibility='public')
        cls.staff = get_user_model().objects.create_superuser('latest-notice-staff', password='test-only')
        cls.src_old = Source.objects.create(id='latest-src-old', title='旧通知原文',
                                            url='https://example.test/latest-old')
        cls.src_new = Source.objects.create(id='latest-src-new', title='新通知原文',
                                            url='https://example.test/latest-new')
        cls.old = Notice.objects.create(id='latest-a-old', activity=cls.owner, source=cls.src_old,
            year=2026, published=date(2026, 2, 1), stage_start=date(2026, 4, 5),
            audience='旧年度对象', position=0)
        cls.new = Notice.objects.create(id='latest-a-new', activity=cls.origin, display_activity=cls.owner,
            source=cls.src_new, year=2026, published=date(2026, 5, 1), stage_start=date(2026, 5, 6),
            audience='新年度对象', position=9)
        cls.new_fact = Fact.objects.create(id='latest-a-new-fact', notice=cls.new, kind='schedule',
            label='新时间', value='五月新通知事实 ONLY_NEW_FACT')
        cls.old_fact = Fact.objects.create(id='latest-a-old-fact', notice=cls.old, kind='schedule',
            label='旧时间', value='四月旧通知事实 OLD_ONLY_FACT')
        cls.other_activity_notice = Notice.objects.create(id='latest-other-2026', activity=cls.other,
            source=cls.src_old, year=2026, published=date(2026, 3, 1))
        cls.cross_year = Notice.objects.create(id='latest-owner-2025', activity=cls.owner,
            source=cls.src_old, year=2025, published=date(2025, 8, 1))

        cls.group_one = ActivityGroup.objects.create(id='latest-group-one', activity=cls.owner,
            title='分组一', visibility='public')
        cls.group_two = ActivityGroup.objects.create(id='latest-group-two', activity=cls.owner,
            title='分组二', visibility='public')
        cls.group_three = ActivityGroup.objects.create(id='latest-group-three', activity=cls.owner,
            title='交叠分组', visibility='public')
        cls.group_one_old = Notice.objects.create(id='latest-g1-old', activity=cls.owner,
            source=cls.src_old, year=2026, published=date(2026, 1, 1))
        cls.group_one_new = Notice.objects.create(id='latest-g1-new', activity=cls.owner,
            source=cls.src_new, year=2026, published=date(2026, 6, 1))
        cls.group_one.notices.add(cls.group_one_old, cls.group_one_new)
        cls.overlap_notice = Notice.objects.create(id='latest-group-overlap', activity=cls.owner,
            source=cls.src_old, year=2026, published=date(2026, 5, 15))
        cls.group_one.notices.add(cls.overlap_notice)
        cls.group_three.notices.add(cls.overlap_notice)
        cls.group_two_tie_z = Notice.objects.create(id='latest-g2-z', activity=cls.owner,
            source=cls.src_old, year=2026, published=date(2026, 7, 1), position=3)
        cls.group_two_tie_b = Notice.objects.create(id='latest-g2-b', activity=cls.owner,
            source=cls.src_new, year=2026, published=date(2026, 7, 1), position=1)
        cls.group_two_tie_a = Notice.objects.create(id='latest-g2-a', activity=cls.owner,
            source=cls.src_new, year=2026, published=date(2026, 7, 1), position=1)
        cls.group_two.notices.add(cls.group_two_tie_z, cls.group_two_tie_b, cls.group_two_tie_a)

        cls.unknown_date_one = Notice.objects.create(id='latest-date-unknown-a', activity=cls.owner,
            source=cls.src_old, year=2026, published=None)
        cls.unknown_date_two = Notice.objects.create(id='latest-date-unknown-b', activity=cls.owner,
            source=cls.src_new, year=2026, published=None)
        cls.unknown_year_one = Notice.objects.create(id='latest-year-unknown-a', activity=cls.owner,
            source=cls.src_old, year=None, published=date(2026, 9, 1))
        cls.unknown_year_two = Notice.objects.create(id='latest-year-unknown-b', activity=cls.owner,
            source=cls.src_new, year=None, published=date(2026, 10, 1))
        cls.hidden_newer = Notice.objects.create(id='latest-hidden-newer', activity=cls.owner,
            source=cls.src_new, year=2026, published=date(2026, 12, 1), visibility='hidden')

    def public_ids(self):
        return set(services._notice_qs().values_list('pk', flat=True))

    def test_latest_by_effective_display_activity_year_and_other_years(self):
        ids = self.public_ids()
        self.assertIn(self.new.pk, ids)
        self.assertNotIn(self.old.pk, ids)
        self.assertIn(self.cross_year.pk, ids)
        self.assertIn(self.other_activity_notice.pk, ids)
        self.assertNotIn(self.hidden_newer.pk, ids)

    def test_groups_are_independent_scopes_and_same_day_ties_are_stable(self):
        ids = self.public_ids()
        self.assertNotIn(self.group_one_old.pk, ids)
        self.assertIn(self.group_one_new.pk, ids)
        self.assertIn(self.group_two_tie_a.pk, ids)
        self.assertNotIn(self.group_two_tie_b.pk, ids)
        self.assertNotIn(self.group_two_tie_z.pk, ids)

    def test_overlapping_notice_is_selected_per_card_not_union_of_group_winners(self):
        group_one_ids = set(services.card_notice_qs(self.group_one.id).values_list('pk', flat=True))
        group_three_ids = set(services.card_notice_qs(self.group_three.id).values_list('pk', flat=True))
        self.assertIn(self.group_one_new.pk, group_one_ids)
        self.assertNotIn(self.overlap_notice.pk, group_one_ids)
        self.assertEqual(group_three_ids, {self.overlap_notice.pk})
        self.assertFalse(services.card_has_notice(self.group_one.id, self.overlap_notice.pk))
        self.assertTrue(services.card_has_notice(self.group_three.id, self.overlap_notice.pk))
        loaded = {row.card.id: {notice.pk for notice in row.notices}
                  for row in services.load_cards()}
        for group in (self.group_one, self.group_two, self.group_three):
            self.assertEqual(loaded[group.pk],
                set(services.card_notice_qs(group.pk).values_list('pk', flat=True)))
        self.assertEqual(self.client.get(
            f'/api/v1/activities/{self.group_one.pk}/notices/{self.overlap_notice.pk}/').status_code, 404)
        self.assertEqual(self.client.get(
            f'/api/v1/activities/{self.group_three.pk}/notices/{self.overlap_notice.pk}/').status_code, 200)

    def test_missing_date_or_year_is_not_guessed_into_a_latest_family(self):
        ids = self.public_ids()
        self.assertIn(self.unknown_date_one.pk, ids)
        self.assertIn(self.unknown_date_two.pk, ids)
        self.assertIn(self.unknown_year_one.pk, ids)
        self.assertIn(self.unknown_year_two.pk, ids)

    def test_old_notice_is_hidden_from_api_and_calendar_but_stays_editable(self):
        client = self.client
        latest_detail = client.get(f'/api/v1/activities/{self.owner.pk}/', {'notice': self.new.pk})
        self.assertEqual(latest_detail.status_code, 200)
        payload = latest_detail.json()['notice']
        self.assertEqual(payload['notice_id'], self.new.pk)
        self.assertIn('ONLY_NEW_FACT', str(payload))
        self.assertNotIn('OLD_ONLY_FACT', str(payload))
        self.assertEqual(client.get(f'/api/v1/activities/{self.owner.pk}/',
                                    {'notice': self.old.pk}).status_code, 404)
        annual_april = client.get('/api/v1/calendar/', {'year': '2026', 'month': '4'}).json()
        self.assertNotIn('OLD_ONLY_FACT', str(annual_april))

        self.old.refresh_from_db()
        self.old_fact.refresh_from_db()
        self.src_old.refresh_from_db()
        self.assertEqual(self.old.source_id, self.src_old.pk)
        self.assertEqual(self.old_fact.value, '四月旧通知事实 OLD_ONLY_FACT')
        self.assertEqual(self.old.visibility, 'public')
        self.client.force_login(self.staff)
        editor = self.client.get(f'/manage/activity/{self.owner.pk}/participation/',
                                  {'notice': self.old.pk})
        self.assertEqual(editor.status_code, 200)
        self.assertEqual(editor.context['obj'].pk, self.old.pk)
        self.assertEqual(editor.context['obj'].source_id, self.src_old.pk)

    def test_static_catalog_uses_the_same_winning_notice_projection(self):
        frontend = Path(__file__).resolve().parents[2] / 'frontend'
        sys.path.insert(0, str(frontend))
        import export_static

        catalog, _ = export_static.build_catalog_export()
        self.assertIn(self.new.pk, catalog['notices'])
        self.assertNotIn(self.old.pk, catalog['notices'])
        self.assertIn(self.group_one_new.pk, catalog['notices'])
        self.assertNotIn(self.group_one_old.pk, catalog['notices'])
        cards = {card['card_id']: card for card in catalog['cards']}
        self.assertNotIn(self.overlap_notice.pk, cards[self.group_one.pk]['notice_ids'])
        self.assertIn(self.overlap_notice.pk, cards[self.group_three.pk]['notice_ids'])
