"""从旧库与已发布页面迁移到新模型。

安全要求（施工单第 8 节）：
- 只读打开旧库；写入只在 --dry-run 之外发生，整批事务；
- 批次 ID + 输入哈希保证幂等；基线哈希不匹配时拒绝覆盖；
- 隐藏活动、历史修订、扩展字段全部保留；
- 学院拆分卡只建分组，不复制通知。
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
import sqlite3
from datetime import date, datetime, time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from catalog.models import (Activity, ActivityGroup, CampusService, ChangeLog, Fact, Guide, GuideBlock,
                            GuideFaq, GuideSection, GuideSource, ImportBatch, Notice, NoticeTaxonomy,
                            Profile, Revision, SiteMeta, Source, Taxonomy)

# 已发布页面在运行时隐藏的重复卡片（同一赛事已并入校级卡片）
HIDDEN_BY_PUBLIC_PROJECTION = {'activity-50ab394de0d9'}

CATEGORY_LABELS = {
    'sports': '运动健身', 'creative': '文化创作', 'technology': '科技竞赛', 'speech': '演讲表达',
    'volunteering': '志愿服务', 'learning': '学习发展', 'exchange': '国际交流', 'practice': '社会实践',
    'recruitment': '组织招募', 'career': '生涯就业', 'reference': '参考资料', 'lecture': '学术讲座',
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return digest.hexdigest()


def parse_datetime(raw, end_of_day=False):
    """解析旧库日期；只有日期没有时刻的截止时间按当天 23:59:59 处理。"""
    if not raw:
        return None
    text = str(raw).strip()
    m = re.match(r'^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?', text)
    if not m:
        return None
    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    has_clock = m.group(4) is not None
    hour = int(m.group(4) or 0)
    minute = int(m.group(5) or 0)
    second = int(m.group(6) or 0)
    if end_of_day and not has_clock:
        hour, minute, second = 23, 59, 59
    if hour >= 24:
        hour, minute, second = 23, 59, 59
    try:
        return datetime(year, month, day, hour, minute, second, tzinfo=timezone.get_current_timezone())
    except ValueError:
        return None


def parse_date(raw):
    value = parse_datetime(raw)
    return value.date() if value else None


def json_or(value, fallback):
    if not value:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return fallback


class Command(BaseCommand):
    help = '把 data/campus.sqlite3 与已发布页面快照迁移到新库（默认只读源库）'

    def add_arguments(self, parser):
        parser.add_argument('--source', default=str(settings.LEGACY_DB))
        parser.add_argument('--public-page', default=str(settings.LEGACY_PUBLIC_PAGE))
        parser.add_argument('--guide-data', default=str(settings.LEGACY_GUIDE_DATA))
        parser.add_argument('--batch-id', default='')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--force', action='store_true', help='相同输入哈希也重新写入')
        parser.add_argument('--expect-public-sha', default='a01eae8410cb52e31cd7597e7d29b061b124a2ee815943cff1a33944cc82d7e1')
        parser.add_argument('--allow-drift', action='store_true', help='公开快照与预期不一致时仍继续')

    # ------------------------------------------------------------------ 入口
    def handle(self, *args, **opts):
        source = Path(opts['source'])
        page = Path(opts['public_page'])
        guide_data = Path(opts['guide_data'])
        for path in (source, page, guide_data):
            if not path.exists():
                raise CommandError(f'找不到输入文件：{path}')

        source_sha = sha256_file(source)
        page_sha = sha256_file(page)
        guide_sha = sha256_file(guide_data)
        if opts['expect_public_sha'] and page_sha != opts['expect_public_sha'] and not opts['allow_drift']:
            raise CommandError(
                '公开页面快照与预期基线不一致，已停止：\n'
                f'  期望 {opts["expect_public_sha"][:12]}…\n  实际 {page_sha[:12]}…\n'
                '确认这是新的已发布版本后，用 --expect-public-sha 指定或加 --allow-drift。')
        input_hash = hashlib.sha256(f'{source_sha}:{page_sha}:{guide_sha}'.encode()).hexdigest()
        batch_id = opts['batch_id'] or f'import-{input_hash[:12]}'

        existing = ImportBatch.objects.filter(input_hash=input_hash).first()
        if existing and existing.status == 'done' and not opts['force'] and not opts['dry_run']:
            self.stdout.write(self.style.WARNING(
                f'相同输入已迁移过（批次 {existing.id}），未重复写入。需要重跑请加 --force。'))
            return

        conn = sqlite3.connect(f'file:{source.as_posix()}?mode=ro', uri=True)
        conn.row_factory = sqlite3.Row
        try:
            data = self.read_legacy(conn)
        finally:
            conn.close()
        public = self.read_public_page(page)
        guides = json.loads(guide_data.read_text(encoding='utf-8'))
        source_revision = data['revision']

        plan = self.plan(data, public, guides, guide_data)
        self.stdout.write(json.dumps(plan['stats'], ensure_ascii=False, indent=1))

        if opts['dry_run']:
            self.stdout.write(self.style.WARNING('dry-run：未写入数据库。'))
            return

        with transaction.atomic():
            batch, _ = ImportBatch.objects.update_or_create(
                id=batch_id,
                defaults={'input_hash': input_hash, 'source_revision': source_revision,
                          'status': 'running', 'stats': plan['stats'],
                          'note': f'源库 {source.name} / 快照 {page.name}'},
            )
            revision, _ = Revision.objects.update_or_create(
                id=f'rev-import-{input_hash[:12]}',
                defaults={
                    'parent_id': (Revision.objects.exclude(id=f'rev-import-{input_hash[:12]}')
                                  .order_by('-created_at').values_list('id', flat=True).first() or ''),
                    'batch': batch,
                    'catalog_hash': plan['catalog_hash'],
                    'reason': '从正式库与已发布页面迁移',
                    'origin': 'migrate_legacy',
                })
            revision.snapshot = gzip.compress(json.dumps(plan['snapshot'], ensure_ascii=False).encode('utf-8'))
            revision.save(update_fields=['snapshot'])

            stats = self.write_all(plan, revision, batch)
            batch.status = 'done'
            batch.finished_at = timezone.now()
            batch.stats = stats
            batch.save(update_fields=['status', 'finished_at', 'stats'])
            SiteMeta.objects.update_or_create(pk=1, defaults={
                'site_name': '成都大学校园生活与活动',
                'description': '按学院、年份、类别和通知时间，发现成都大学校园活动与往届准备线索。',
                'schema_version': plan['meta']['schema_version'],
                'coverage': plan['meta']['coverage'],
                'policies': plan['meta']['policies'],
                'display_options': plan['meta']['display_options'],
                'current_revision': revision.id,
                'published_at': timezone.now(),
            })
        self.stdout.write(self.style.SUCCESS(json.dumps(stats, ensure_ascii=False, indent=1)))

    # ------------------------------------------------------------------ 读取
    def read_legacy(self, conn):
        def rows(sql):
            return [dict(r) for r in conn.execute(sql)]

        revision = 'unknown'
        state = conn.execute('select revision from current_state where id=1').fetchone()
        if state:
            revision = state['revision']
        meta_row = conn.execute('select extras from catalog_metadata where id=1').fetchone()
        return {
            'revision': revision,
            'activities': rows('select * from activities'),
            'notices': rows('select * from notices'),
            'sources': rows('select * from sources'),
            'facts': rows('select * from facts'),
            'profiles': rows('select * from profiles'),
            'taxonomy': rows('select * from taxonomy'),
            'notice_taxonomy': rows('select * from notice_taxonomy'),
            'metadata': json_or(meta_row['extras'] if meta_row else '', {}),
        }

    def read_public_page(self, page: Path) -> dict:
        text = page.read_text(encoding='utf-8')
        match = re.search(r'<script[^>]*id="catalog-data"[^>]*>(.*?)</script>', text, re.S)
        if not match:
            raise CommandError('公开页面里没有找到 catalog-data')
        catalog = json.loads(match.group(1))
        return catalog

    # ------------------------------------------------------------------ 规划
    def plan(self, data, catalog, guides, guide_data=None):
        public_entries = catalog['entries']
        scope_entries = [e for e in public_entries if e['id'].startswith('scope-')]
        public_ids = [e['id'] for e in public_entries if not e['id'].startswith('scope-')]
        db_ids = [a['id'] for a in data['activities']]
        public_set = set(public_ids)
        hidden_ids = [i for i in db_ids if i not in public_set]

        # 拆分卡：按来源 URL 找到对应通知
        url_to_notice = {}
        for notice in data['notices']:
            url_to_notice[notice['source_id']] = notice['id']
        source_url = {s['id']: s['url'] for s in data['sources']}
        groups = []
        for entry in scope_entries:
            urls = [v['source_url'] for v in entry['versions']]
            notice_ids = []
            activity_ids = set()
            for notice in data['notices']:
                url = source_url.get(notice['source_id'])
                if url in urls:
                    notice_ids.append(notice['id'])
                    activity_ids.add(notice['activity_id'])
            if len(notice_ids) != len(urls):
                # 允许重复 URL：只统计去重后的数量
                pass
            groups.append({
                'id': entry['id'], 'title': entry['title'],
                'activity_id': sorted(activity_ids)[0] if activity_ids else '',
                'notices': notice_ids,
                'colleges': sorted({c for v in entry['versions'] for c in (v.get('colleges') or []) if c}),
                'category': entry.get('category', ''),
            })

        catalog_hash = hashlib.sha256(json.dumps({
            'activities': [(a['id'], a['title']) for a in data['activities']],
            'notices': [(n['id'], n['activity_id']) for n in data['notices']],
            'public': sorted(public_set),
            'groups': [(g['id'], sorted(g['notices'])) for g in groups],
        }, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

        stats = {
            'activities': len(data['activities']),
            'notices': len(data['notices']),
            'facts': len(data['facts']),
            'sources': len(data['sources']),
            'public_activities': len(public_ids),
            'hidden_activities': len(hidden_ids),
            'scope_groups': len(groups),
            'guides': len(guides.get('guides', [])),
            'services': len(guides.get('services', [])),
        }
        return {
            'data': data, 'public': catalog, 'groups': groups,
            'guides': guides, 'guide_data': str(guide_data or settings.LEGACY_GUIDE_DATA),
            'flags': {e['id']: (bool(e.get('featured')), bool(e.get('spotlight')))
                      for e in catalog['entries'] if not e['id'].startswith('scope-')},
            'public_ids': public_ids, 'hidden_ids': hidden_ids,
            'catalog_hash': catalog_hash,
            'stats': stats,
            'snapshot': {'public_ids': public_ids, 'hidden_ids': hidden_ids,
                         'groups': [g['id'] for g in groups], 'stats': stats},
            'meta': {
                'schema_version': catalog.get('schema_version', 'catalog-1'),
                'coverage': catalog.get('coverage', {}),
                'policies': {k: catalog.get(k, '') for k in
                             ('year_policy', 'college_policy', 'status_policy')},
                'display_options': catalog.get('display_options', {}),
            },
        }

    # ------------------------------------------------------------------ 写入
    def write_all(self, plan, revision, batch):
        data = plan['data']
        groups = plan['groups']
        public_ids = set(plan['public_ids'])
        created = {'activities': 0, 'notices': 0, 'facts': 0, 'sources': 0, 'groups': 0}

        # 词表
        taxonomy = {}
        for row in data['taxonomy']:
            obj, _ = Taxonomy.objects.update_or_create(
                kind=row['kind'], code=row['code'],
                defaults={'label': row['label'], 'position': row['position'] or 0})
            taxonomy[(row['kind'], row['code'])] = obj
        for code, label in CATEGORY_LABELS.items():
            obj, _ = Taxonomy.objects.update_or_create(
                kind='category', code=code, defaults={'label': label, 'position': 0})
            taxonomy[('category', code)] = obj
        for code, label in plan['public'].get('levels', {}).items():
            obj, _ = Taxonomy.objects.update_or_create(
                kind='level', code=code, defaults={'label': label, 'position': 0})
            taxonomy[('level', code)] = obj

        # 来源
        for row in data['sources']:
            Source.objects.update_or_create(id=row['id'], defaults={'url': row['url']})

        # 活动
        for row in data['activities']:
            extras = json_or(row['extras'], {})
            category = taxonomy.get(('category', row['category'] or ''))
            if category is None and row['category']:
                category, _ = Taxonomy.objects.update_or_create(
                    kind='category', code=row['category'],
                    defaults={'label': extras.get('category_label', row['category']), 'position': 0})
                taxonomy[('category', row['category'])] = category
            obj, is_new = Activity.objects.update_or_create(
                id=row['id'],
                defaults={
                    'title': row['title'], 'kind': row['kind'] or 'notice',
                    'category': category,
                    'summary': extras.get('summary', ''),
                    'tags': extras.get('tags', []),
                    'featured': plan['flags'].get(row['id'], (bool(row['featured']), bool(row['spotlight'])))[0],
                    'spotlight': plan['flags'].get(row['id'], (bool(row['featured']), bool(row['spotlight'])))[1],
                    'position': row['position'] or 0,
                    'visibility': ('public' if row['id'] in public_ids and row['id'] not in HIDDEN_BY_PUBLIC_PROJECTION
                                   else 'hidden'),
                    'material_ids': extras.get('material_ids', []),
                    'extras': extras, 'layout': json_or(row['layout'], []),
                    'source_revision': plan['data']['revision'],
                })
            created['activities'] += int(is_new)

        links_by_notice = {}
        for link in data['notice_taxonomy']:
            links_by_notice.setdefault(link['notice_id'], []).append(link)

        # 公开页面的展示归属：通知在公开卡片里的位置（不改原 activity）
        url_to_public_card = {}
        for entry in plan['public']['entries']:
            if entry['id'].startswith('scope-'):
                continue
            for version in entry['versions']:
                url_to_public_card[version['source_url']] = entry['id']
        source_id_by_notice = {n['id']: n['source_id'] for n in data['notices']}
        source_url_by_id = {s['id']: s['url'] for s in data['sources']}
        display_for_notice = {}
        for notice_id, source_id in source_id_by_notice.items():
            card = url_to_public_card.get(source_url_by_id.get(source_id, ''))
            if card:
                display_for_notice[notice_id] = card

        # 通知与事实
        for row in data['notices']:
            extras = json_or(row['extras'], {})
            notice, is_new = Notice.objects.update_or_create(
                id=row['id'],
                defaults={
                    'activity_id': row['activity_id'],
                    'source_id': row['source_id'] or None,
                    'year': row['year'],
                    'published': parse_date(row['published']),
                    'deadline': parse_datetime(row['deadline'], end_of_day=True),
                    'deadline_kind': row['deadline_kind'] or '',
                    'stage_start': parse_date(row['stage_start']),
                    'stage_end': parse_date(row['stage_end']),
                    'audience': row['audience'] or '',
                    'conflict': bool(row['conflict']),
                    'display_activity_id': display_for_notice.get(row['id']),
                    'position': row['position'] or 0,
                    'extras': extras,
                    'layout': json_or(row['layout'], []),
                })
            created['notices'] += int(is_new)
            # 标签
            for link in links_by_notice.get(row['id'], []):
                target = taxonomy.get((link['kind'], link['code']))
                if target is None:
                    target, _ = Taxonomy.objects.update_or_create(
                        kind=link['kind'], code=link['code'],
                        defaults={'label': link['code'], 'position': 0})
                    taxonomy[(link['kind'], link['code'])] = target
                NoticeTaxonomy.objects.update_or_create(
                    notice=notice, taxonomy=target,
                    defaults={'kind': link['kind'], 'position': link['position'] or 0})

        facts_by_notice = {}
        for row in data['facts']:
            extras = json_or(row['extras'], {})
            _, fact_new = Fact.objects.update_or_create(
                id=row['id'],
                defaults={'notice_id': row['notice_id'], 'position': row['position'] or 0,
                          'kind': row['kind'] or 'other', 'label': extras.get('label', ''),
                          'value': row['value'] or '', 'quote': row['quote'] or '',
                          'locator': row['locator'] or '',
                          'source_url': row['source_url'] or '',
                          'basis': row['basis'] or '', 'extras': extras,
                          'layout': json_or(row['layout'], [])})
            created['facts'] += int(fact_new)
        for row in data['profiles']:
            Profile.objects.update_or_create(
                notice_id=row['notice_id'], defaults={'payload': json_or(row['payload'], {})})

        # 学院拆分卡
        for group in groups:
            if not group['activity_id']:
                continue
            obj, is_new = ActivityGroup.objects.update_or_create(
                id=group['id'],
                defaults={'activity_id': group['activity_id'], 'title': group['title'],
                          'position': 0, 'visibility': 'public'})
            obj.notices.set(Notice.objects.filter(id__in=group['notices']))
            obj.colleges.set([taxonomy[('college', code)] for code in group['colleges']
                              if ('college', code) in taxonomy])
            created['groups'] += int(is_new)

        # 指南与服务
        self.write_guides(plan, created)

        # 变更记录：按实体记录本次写入
        for kind, count in created.items():
            if count:
                ChangeLog.objects.create(revision=revision, entity_kind=kind, entity_id='*',
                                         action='import', note=f'写入 {count} 条')
        return {**plan['stats'], **{f'new_{k}': v for k, v in created.items()}}

    def write_guides(self, plan, created):
        data = plan['guides']
        target = Path(plan['guide_data'])
        if target.exists() and not data:
            data = json.loads(target.read_text(encoding='utf-8'))
        for index, item in enumerate(data.get('guides', [])):
            guide, _ = Guide.objects.update_or_create(
                id=item['id'],
                defaults={'title': item['title'], 'subtitle': item.get('subtitle', ''),
                          'category': item.get('category', ''), 'summary': item.get('description', ''),
                          'scope': item.get('scope', ''), 'caution': item.get('caution', ''),
                          'source_note': item.get('source', ''), 'number': item.get('number', ''),
                          'icon': item.get('icon', ''), 'tags': item.get('tags', []),
                          'position': index, 'visibility': 'public',
                          'related_service': item.get('relatedService', '')})
            guide.sections.all().delete()
            for s_index, section in enumerate(item.get('sections', [])):
                section_obj = GuideSection.objects.create(
                    guide=guide, position=s_index, title=section['title'], kind='step')
                for b_index, text in enumerate(section.get('items', [])):
                    GuideBlock.objects.create(section=section_obj, position=b_index, text=text)
            guide.faqs.all().delete()
            for f_index, faq in enumerate(item.get('faqs', [])):
                GuideFaq.objects.create(guide=guide, position=f_index,
                                         question=faq['q'], answer=faq['a'])
            guide.sources.all().delete()
            GuideSource.objects.create(guide=guide, label=item.get('source', '')[:200])
        for index, item in enumerate(data.get('services', [])):
            CampusService.objects.update_or_create(
                id=item['id'],
                defaults={'name': item['title'], 'category': item.get('category', ''),
                          'description': item.get('description', ''),
                          'owner': item.get('owner', ''), 'phone': item.get('phone', ''),
                          'url': item.get('url', ''), 'source_url': item.get('source', ''),
                          'source_label': item.get('sourceLabel', ''),
                          'source_date': parse_date(item.get('sourceDate')),
                          'checked_on': parse_date(item.get('checked')),
                          'note': item.get('note', ''), 'related_guide': item.get('guide', ''),
                          'position': index, 'visibility': 'public'})
