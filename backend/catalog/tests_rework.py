"""返工单（2026-10-20）指出的具体失败案例，逐条固化成回归测试。"""
from datetime import date

from django.test import TestCase

from catalog import indexing, services
from catalog.models import Activity, ActivityGroup, Fact, Notice, Source, Taxonomy


class CardAccessTests(TestCase):
    """P1-1：卡片实际包含哪些通知，只有一个口径。"""

    @classmethod
    def setUpTestData(cls):
        cat = Taxonomy.objects.create(kind='category', code='technology', label='科技竞赛')
        cls.origin = Activity.objects.create(id='act-origin', title='原归属活动', category=cat,
                                            visibility='hidden')
        cls.target = Activity.objects.create(id='act-target', title='展示归属活动', category=cat,
                                             visibility='public')
        cls.group = ActivityGroup.objects.create(id='scope-g1', activity=cls.target,
                                                 title='某学院选拔', visibility='public')
        cls.other = ActivityGroup.objects.create(id='scope-g2', activity=cls.target,
                                                 title='另一学院选拔', visibility='public')
        source = Source.objects.create(id='src', url='https://example.cdu.edu.cn/x.htm')
        # 通知原归属隐藏活动，公开页面展示在校级活动下
        cls.displayed = Notice.objects.create(id='n-displayed', activity=cls.origin, source=source,
                                              year=2026, published='2026-09-10',
                                              display_activity=cls.target)
        # 同一父级下、只属于另一个分组的通知
        cls.grouped = Notice.objects.create(id='n-grouped', activity=cls.target, source=source,
                                            year=2026, published='2026-09-11')
        cls.group.notices.add(cls.grouped)

    def test_display_attribution_detail_is_200(self):
        response = self.client.get('/api/v1/activities/act-target/notices/n-displayed/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['notice']['notice_id'], 'n-displayed')

    def test_notice_cannot_be_reached_from_its_original_hidden_card(self):
        self.assertEqual(
            self.client.get('/api/v1/activities/act-origin/notices/n-displayed/').status_code, 404)

    def test_notice_of_other_group_is_404(self):
        self.assertEqual(
            self.client.get('/api/v1/activities/scope-g2/notices/n-grouped/').status_code, 404)
        self.assertEqual(
            self.client.get('/api/v1/activities/scope-g1/notices/n-grouped/').status_code, 200)

    def test_activity_card_does_not_repeat_grouped_notice(self):
        payload = self.client.get('/api/v1/activities/act-target/').json()
        ids = [v['notice_id'] for v in payload['entry']['versions']]
        self.assertIn('n-displayed', ids)
        self.assertNotIn('n-grouped', ids)

    def test_unknown_card_is_404(self):
        self.assertEqual(self.client.get('/api/v1/activities/nope/').status_code, 404)

    def test_hidden_notice_deep_link_is_404(self):
        hidden = Notice.objects.create(id='n-hidden', activity=self.origin, year=2026)
        self.assertEqual(
            self.client.get(f'/api/v1/activities/act-target/notices/{hidden.id}/').status_code, 404)


class FactCompletenessTests(TestCase):
    """P1-2：详情返回全部事实；列表不返回正文。"""

    @classmethod
    def setUpTestData(cls):
        cat = Taxonomy.objects.create(kind='category', code='creative', label='创作')
        cls.activity = Activity.objects.create(id='act-facts', title='事实很多的活动',
                                               category=cat, visibility='public')
        cls.notice = Notice.objects.create(id='n-facts', activity=cls.activity, year=2026,
                                           published='2026-09-01')
        for index in range(13):
            Fact.objects.create(id=f'n-facts-{index}', notice=cls.notice, position=index,
                                kind='registration', label=f'条款{index}', value=f'第 {index} 条要求')

    def test_detail_returns_every_fact(self):
        payload = self.client.get(
            '/api/v1/activities/act-facts/notices/n-facts/').json()
        self.assertEqual(len(payload['notice']['participation_facts']), 13)
        self.assertEqual(payload['notice']['fact_count'], 13)

    def test_list_does_not_ship_full_facts(self):
        payload = self.client.get('/api/v1/activities/?view=all').json()
        version = payload['results'][0]['versions'][0]
        self.assertLessEqual(len(version['participation_facts']), 12)
        self.assertTrue(version['content_profile'].get('truncated'))


class SearchAndMonthTests(TestCase):
    """P2-2：搜索覆盖公开事实；跨月征集只记开始月。"""

    @classmethod
    def setUpTestData(cls):
        cat = Taxonomy.objects.create(kind='category', code='career', label='生涯就业')
        cls.activity = Activity.objects.create(id='act-search', title='暑期研学',
                                               category=cat, visibility='public')
        cls.notice = Notice.objects.create(id='n-search', activity=cls.activity, year=2025,
                                           published='2025-06-01',
                                           stage_start=date(2025, 1, 21),
                                           stage_end=date(2025, 3, 30))
        cls.fact = Fact.objects.create(id='n-search-0', notice=cls.notice, position=0,
                                       kind='registration', label='联系电话',
                                       value='咨询电话 14215')
        indexing.refresh_notice(cls.notice)

    def test_search_matches_fact_text(self):
        payload = self.client.get('/api/v1/activities/?q=14215').json()
        self.assertEqual(payload['count'], 1)
        self.assertEqual(payload['results'][0]['id'], 'act-search')

    def test_search_is_case_insensitive_for_latin(self):
        self.activity.title = 'Campus Innovation'
        self.activity.save()
        indexing.refresh_activity(self.activity)
        self.assertEqual(self.client.get('/api/v1/activities/?q=campus').json()['count'], 1)

    def test_cross_month_only_counts_start_month(self):
        self.assertEqual(services.decode_months(self.notice.seasonal_months), {1})
        self.assertEqual(services.seasonal_months_for_notice(self.notice), {1})

    def test_month_filter_follows_start_month(self):
        self.assertEqual(self.client.get('/api/v1/activities/?month=1').json()['count'], 1)
        self.assertEqual(self.client.get('/api/v1/activities/?month=3').json()['count'], 0)
