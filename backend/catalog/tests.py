"""少量高价值测试：公开口径、隐藏保护、分页与参数校验。用临时测试库。"""
import json
from django.test import TestCase

from catalog import services
from catalog.models import Activity, Notice, Source, Taxonomy


class PublicApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        category = Taxonomy.objects.create(kind='category', code='technology', label='科技竞赛')
        cls.public = Activity.objects.create(id='act-public', title='公开活动', category=category,
                                             summary='摘要', featured=True, spotlight=True,
                                             visibility='public')
        cls.hidden = Activity.objects.create(id='act-hidden', title='隐藏活动', category=category,
                                             visibility='hidden')
        source = Source.objects.create(id='src-1', url='https://example.cdu.edu.cn/1.htm')
        cls.notice = Notice.objects.create(id='n-public', activity=cls.public, source=source,
                                           year=2026, published='2026-09-01', audience='全体本科生')
        cls.hidden_notice = Notice.objects.create(id='n-hidden', activity=cls.hidden, source=source,
                                                  year=2026, published='2026-09-02')

    def test_list_only_returns_public_cards(self):
        response = self.client.get('/api/v1/activities/?view=all')
        payload = response.json()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload['count'], 1)
        self.assertEqual(payload['results'][0]['id'], 'act-public')

    def test_hidden_activity_detail_is_404(self):
        self.assertEqual(self.client.get('/api/v1/activities/act-hidden/').status_code, 404)

    def test_invalid_month_is_400(self):
        self.assertEqual(self.client.get('/api/v1/activities/?month=13').status_code, 400)

    def test_pagination_shape(self):
        payload = self.client.get('/api/v1/activities/?page=1&page_size=1').json()
        for key in ('count', 'page', 'page_size', 'total_pages', 'results'):
            self.assertIn(key, payload)


class RegistrationRuleTests(TestCase):
    def test_deadline_without_window_counts_as_open(self):
        category = Taxonomy.objects.create(kind='category', code='career', label='生涯就业')
        activity = Activity.objects.create(id='a', title='报名中', category=category, visibility='public')
        source = Source.objects.create(id='s', url='https://example.cdu.edu.cn/2.htm')
        notice = Notice.objects.create(id='n', activity=activity, source=source, year=2026,
                                       published='2026-10-01',
                                       deadline='2099-01-01T23:59:00+08:00',
                                       deadline_kind='registration')
        self.assertTrue(services.registration_open(notice))
        notice.deadline_kind = 'event'
        notice.save()
        self.assertFalse(services.registration_open(notice))


class AdminSmokeTests(TestCase):
    def test_admin_requires_login(self):
        response = self.client.get('/manage/activity/')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/manage/login/', response['Location'])
