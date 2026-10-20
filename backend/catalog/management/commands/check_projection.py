"""逐字段核对：后端公开投影 vs 已发布页面快照。

比 check_public 更严：标题、摘要、类别、标签、精选、每个版本的日期/对象/事实/画像。
运行时把一条隐藏院级通知并进校级详情（collegeSelections），这里按同一口径解释。
"""
import json
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from catalog import services
from catalog.models import Notice

ENTRY_FIELDS = ('title', 'summary', 'category', 'tags', 'featured', 'spotlight')
VERSION_FIELDS = ('year', 'published', 'deadline', 'deadline_kind', 'stage_start', 'stage_end',
                  'colleges', 'levels', 'audience', 'conflict', 'source_url', 'edition_label')
RUNTIME_HIDDEN = {'activity-50ab394de0d9'}
# 已发布页面在浏览器里把这条隐藏院级通知并进校级详情（CduProjection.apply），
# 快照 JSON 里没有这个字段，所以按页面运行时语义核对。
RUNTIME_COLLEGE_SELECTIONS = {
    'activity-59984d77d57d': ['https://ftva.cdu.edu.cn/info/1207/1681.htm'],
}


def _norm_facts(facts):
    return sorted((f.get('kind') or '', f.get('value') or '', f.get('quote') or '')
                  for f in facts or [])


def _norm_profile(profile):
    sections = (profile or {}).get('sections') or []
    return [(s.get('kind') or '', s.get('title') or '',
             tuple(i.get('text') or '' for i in s.get('items') or [])) for s in sections]


def _date_only(value):
    return str(value)[:10] if value else None


def _blank(value):
    return None if value in (None, '', [], {}) else value


def _sorted(value):
    return sorted(value or [], key=str)


class Command(BaseCommand):
    help = '逐字段比较公开投影与已发布快照，输出差异清单'

    def add_arguments(self, parser):
        parser.add_argument('--public-page', default=str(settings.LEGACY_PUBLIC_PAGE))
        parser.add_argument('--output', default='work/backend-migration-2026-10-20/projection-diff.json')
        parser.add_argument('--limit', type=int, default=40, help='每种差异最多列出的样例数')

    def handle(self, *args, **opts):
        page = Path(opts['public_page'])
        catalog = json.loads(re.search(
            r'<script[^>]*id="catalog-data"[^>]*>(.*?)</script>',
            page.read_text(encoding='utf-8'), re.S).group(1))
        expected = {e['id']: e for e in catalog['entries'] if e['id'] not in RUNTIME_HIDDEN}

        notices = {}
        for notice in (Notice.objects.select_related('source', 'profile')
                       .prefetch_related('facts', 'taxonomies')):
            notices[notice.id] = notice
        actual = {row.card.id: services.serialize_entry(row.card, row.notices)
                  for row in services.load_cards()}

        missing = sorted(set(expected) - set(actual))
        extra = sorted(set(actual) - set(expected))

        entry_diffs, version_diffs, fact_diffs, profile_diffs = [], [], [], []
        for card_id in sorted(set(expected) & set(actual)):
            want, got = expected[card_id], actual[card_id]
            for key in ENTRY_FIELDS:
                if key == 'tags':
                    if _sorted(want.get(key)) != _sorted(got.get(key)):
                        entry_diffs.append({'id': card_id, 'field': key,
                                            'published': want.get(key), 'backend': got.get(key)})
                    continue
                if _blank(want.get(key)) != _blank(got.get(key)):
                    entry_diffs.append({'id': card_id, 'field': key,
                                        'published': want.get(key), 'backend': got.get(key)})
            expected_selections = RUNTIME_COLLEGE_SELECTIONS.get(card_id)
            if expected_selections is not None:
                got_selections = got.get('collegeSelections') or []
                urls = [item.get('url') for item in got_selections]
                texts_ok = all('学院内部选拔' in (item.get('text') or '') for item in got_selections)
                if urls != expected_selections or not texts_ok:
                    entry_diffs.append({'id': card_id, 'field': 'collegeSelections',
                                        'published': expected_selections, 'backend': got_selections})
            elif _blank(want.get('collegeSelections')) != _blank(got.get('collegeSelections')):
                entry_diffs.append({'id': card_id, 'field': 'collegeSelections',
                                    'published': want.get('collegeSelections'),
                                    'backend': got.get('collegeSelections')})

            want_versions = {v.get('source_url'): v for v in want.get('versions') or []}
            got_versions = {v.get('source_url'): v for v in got.get('versions') or []}
            if set(want_versions) != set(got_versions):
                version_diffs.append({'id': card_id, 'field': 'source_urls',
                                      'published': sorted(k or '' for k in want_versions),
                                      'backend': sorted(k or '' for k in got_versions)})
                continue
            for url, want_v in want_versions.items():
                got_v = got_versions[url]
                for key in VERSION_FIELDS:
                    if key in ('published', 'stage_start', 'stage_end', 'deadline'):
                        want_value, got_value = _date_only(want_v.get(key)), _date_only(got_v.get(key))
                    elif key in ('colleges', 'levels'):
                        want_value, got_value = _sorted(want_v.get(key)), _sorted(got_v.get(key))
                    else:
                        want_value, got_value = _blank(want_v.get(key)), _blank(got_v.get(key))
                    if want_value != got_value:
                        version_diffs.append({'id': card_id, 'field': key, 'source_url': url,
                                              'published': want_value, 'backend': got_value})
                notice = notices.get(got_v.get('notice_id'))
                if notice is None:
                    continue
                full = services.serialize_notice(notice, detail=True)
                if _norm_facts(want_v.get('participation_facts')) != _norm_facts(full['participation_facts']):
                    fact_diffs.append({'id': card_id, 'source_url': url,
                                       'published_count': len(want_v.get('participation_facts') or []),
                                       'backend_count': len(full['participation_facts']),
                                       'published': _norm_facts(want_v.get('participation_facts'))[:3],
                                       'backend': _norm_facts(full['participation_facts'])[:3]})
                if _norm_profile(want_v.get('content_profile')) != _norm_profile(full['content_profile']):
                    profile_diffs.append({'id': card_id, 'source_url': url,
                                          'published_sections': len((want_v.get('content_profile') or {}).get('sections') or []),
                                          'backend_sections': len(full['content_profile'].get('sections') or [])})

        report = {
            'expected_cards': len(expected),
            'actual_cards': len(actual),
            'expected_versions': sum(len(v.get('versions') or []) for v in expected.values()),
            'actual_versions': sum(len(v.get('versions') or []) for v in actual.values()),
            'missing_cards': missing,
            'extra_cards': extra,
            'entry_diff_count': len(entry_diffs),
            'version_diff_count': len(version_diffs),
            'fact_diff_count': len(fact_diffs),
            'profile_diff_count': len(profile_diffs),
            'entry_diffs': entry_diffs[:opts['limit']],
            'version_diffs': version_diffs[:opts['limit']],
            'fact_diffs': fact_diffs[:opts['limit']],
            'profile_diffs': profile_diffs[:opts['limit']],
            'ok': not (missing or extra or entry_diffs or version_diffs or fact_diffs or profile_diffs),
        }
        out = Path(settings.PROJECT_DIR) / opts['output']
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        summary = {k: report[k] for k in ('expected_cards', 'actual_cards', 'expected_versions',
                                          'actual_versions', 'entry_diff_count', 'version_diff_count',
                                          'fact_diff_count', 'profile_diff_count', 'ok')}
        self.stdout.write(json.dumps(summary, ensure_ascii=False, indent=1))
        self.stdout.write(f'完整结果：{out}')
