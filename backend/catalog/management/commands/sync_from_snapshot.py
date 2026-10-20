"""把已发布页面上的内容修正搬进数据库（一次一条修订，旧值留在修订里）。

只处理当前库仍是旧值、页面已经改过的字段：
活动标题/摘要/标签，通知的 edition_label。
--dry-run 只列差异不写库。
"""
import json
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from catalog import audit, services
from catalog.models import Activity, Notice, SiteMeta

RUNTIME_HIDDEN = {'activity-50ab394de0d9'}


class Command(BaseCommand):
    help = '按已发布页面同步标题/摘要/标签/版本标签，并生成一条修订'

    def add_arguments(self, parser):
        parser.add_argument('--public-page', default=str(settings.LEGACY_PUBLIC_PAGE))
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **opts):
        page = Path(opts['public_page'])
        catalog = json.loads(re.search(
            r'<script[^>]*id="catalog-data"[^>]*>(.*?)</script>',
            page.read_text(encoding='utf-8'), re.S).group(1))
        entries = {e['id']: e for e in catalog['entries'] if e['id'] not in RUNTIME_HIDDEN}

        activity_plan, notice_plan, group_plan = [], [], []
        for card_id, entry in entries.items():
            card = services.resolve_card(card_id)
            if card is None:
                continue
            if card.is_group:
                if list(entry.get('tags') or []) != list(card.group.tags or []):
                    group_plan.append((card.group, {'tags': list(entry.get('tags') or [])}))
            else:
                activity = card.activity
                updates = {}
                if entry.get('title') and entry['title'] != activity.title:
                    updates['title'] = entry['title']
                if (entry.get('summary') or '') != (activity.summary or ''):
                    updates['summary'] = entry.get('summary') or ''
                if list(entry.get('tags') or []) != list(activity.tags or []):
                    updates['tags'] = list(entry.get('tags') or [])
                if updates:
                    activity_plan.append((activity, updates))

            notices = list(services.card_notice_qs(card, with_content=False))
            by_url = {}
            for notice in notices:
                if notice.source_id:
                    by_url.setdefault((notice.source.url if notice.source_id else ''), notice)
            for version in entry.get('versions') or []:
                label = version.get('edition_label')
                url = version.get('source_url')
                if not label or not url:
                    continue
                notice = by_url.get(url)
                if notice is None or (notice.extras or {}).get('edition_label') == label:
                    continue
                extras = dict(notice.extras or {})
                extras['edition_label'] = label
                notice_plan.append((notice, {'extras': extras}))

        summary = {
            'activities_to_update': len(activity_plan),
            'notices_to_update': len(notice_plan),
            'groups_to_update': len(group_plan),
            'dry_run': opts['dry_run'],
        }
        if opts['dry_run'] or not (activity_plan or notice_plan):
            self.stdout.write(json.dumps(summary, ensure_ascii=False))
            return

        with transaction.atomic():
            meta = SiteMeta.objects.first()
            revision = audit.open_revision(
                f'对齐已发布页面：标题/摘要/标签 {len(activity_plan)} 条，版本标签 {len(notice_plan)} 条',
                'sync_public_page')
            for activity, updates in activity_plan:
                audit.apply_updates('activity', activity, updates,
                                    reason='对齐已发布页面', origin='sync_public_page',
                                    note='页面已上线的措辞修正', revision=revision)
            for group, updates in group_plan:
                group.tags = updates['tags']
                group.save(update_fields=['tags'])
            for notice, updates in notice_plan:
                audit.apply_updates('notice', notice, updates,
                                    reason='对齐已发布页面', origin='sync_public_page',
                                    note='页面已上线的版本标签', revision=revision)
            audit.publish_revision(revision)

        summary['revision'] = revision.id
        summary['previous_revision'] = meta.current_revision if meta else ''
        self.stdout.write(json.dumps(summary, ensure_ascii=False))
