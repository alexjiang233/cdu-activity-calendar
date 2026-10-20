"""迁移后核对：公开投影与已发布快照逐项比较，并检查隐藏记录是否保留。"""
import json
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from catalog import services
from catalog.models import Activity, Fact, Notice, Profile, Revision


class Command(BaseCommand):
    help = '对比公开投影与已发布快照，输出无损核对结果'

    def add_arguments(self, parser):
        parser.add_argument('--public-page', default=str(settings.LEGACY_PUBLIC_PAGE))
        parser.add_argument('--output', default='work/backend-migration-2026-10-20/verify.json')

    def handle(self, *args, **opts):
        page = Path(opts['public_page'])
        catalog = json.loads(re.search(
            r'<script[^>]*id="catalog-data"[^>]*>(.*?)</script>',
            page.read_text(encoding='utf-8'), re.S).group(1))
        hidden_runtime = {'activity-50ab394de0d9'}
        expected = {e['id']: {v['source_url'] for v in e['versions']}
                    for e in catalog['entries'] if e['id'] not in hidden_runtime}
        actual = {e['id']: {v['source_url'] for v in e['versions']} for e in services.load_entries()}

        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))
        mismatched = [{'id': key, 'missing': sorted(expected[key] - actual[key]),
                       'extra': sorted(actual[key] - expected[key])}
                      for key in expected if key in actual and expected[key] != actual[key]]

        report = {
            'expected_cards': len(expected),
            'actual_cards': len(actual),
            'expected_versions': sum(len(v) for v in expected.values()),
            'actual_versions': sum(len(v) for v in actual.values()),
            'missing_cards': missing,
            'extra_cards': extra,
            'version_mismatches': mismatched,
            'database': {
                'activities': Activity.objects.count(),
                'public_activities': Activity.objects.filter(visibility='public').count(),
                'hidden_activities': Activity.objects.filter(visibility='hidden').count(),
                'notices': Notice.objects.count(),
                'facts': Fact.objects.count(),
                'profiles': Profile.objects.count(),
                'revisions': Revision.objects.count(),
            },
            'hidden_samples': list(Activity.objects.filter(visibility='hidden')
                                   .values_list('id', 'title')[:5]),
            'ok': not (missing or extra or mismatched),
        }
        out = Path(settings.PROJECT_DIR) / opts['output']
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        self.stdout.write(json.dumps({k: report[k] for k in
                                      ('expected_cards', 'actual_cards', 'expected_versions',
                                       'actual_versions', 'ok')}, ensure_ascii=False, indent=1))
        self.stdout.write(f'完整结果：{out}')
        if not report['ok']:
            raise SystemExit(1)
