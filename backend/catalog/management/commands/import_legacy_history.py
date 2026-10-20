"""把旧库的修订与变更搬进新库，历史不再只留在旧文件里。

旧库：data/campus.sqlite3（只读打开，不修改）
- revisions 31 条：带 gzip 快照、原因、来源、时间、父修订
- changes 2128 条：对象类型/ID、动作、前后哈希（旧库没有时间，用所属修订时间）

重复执行安全：按修订 ID 与 (修订, 类型, 对象, 动作, 前哈希, 后哈希) 去重。
"""
import sqlite3
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.dateparse import parse_datetime

from catalog.models import ChangeLog, ImportBatch, Revision


class Command(BaseCommand):
    help = '导入旧库修订（31）与变更（2128），保留原 ID、原因、快照与时间'

    def add_arguments(self, parser):
        parser.add_argument('--source', default=str(settings.LEGACY_DB))
        parser.add_argument('--dry-run', action='store_true')

    def handle(self, *args, **opts):
        source = Path(opts['source'])
        if not source.exists():
            raise SystemExit(f'找不到旧库：{source}')
        con = sqlite3.connect(f'file:{source}?mode=ro', uri=True)
        revisions = con.execute(
            'select revision, batch_id, parent_revision, created_at, reason, origin, '
            'catalog_hash, snapshot from revisions order by created_at').fetchall()
        changes = con.execute(
            'select revision, entity_kind, entity_id, action, before_hash, after_hash '
            'from changes').fetchall()
        con.close()

        stats = {'revisions': len(revisions), 'changes': len(changes),
                 'new_revisions': 0, 'new_changes': 0, 'dry_run': opts['dry_run']}
        if opts['dry_run']:
            self.stdout.write(str(stats))
            return

        with transaction.atomic():
            batch, _ = ImportBatch.objects.get_or_create(
                id='legacy-history-import',
                defaults={'input_hash': 'legacy-history-v1', 'status': 'done',
                          'note': '旧库 revisions/changes 全量导入', 'stats': {}})
            # 旧库每条修订都挂着批次号，先把批次补齐，否则外键过不去
            for legacy_batch in sorted({row[1] for row in revisions if row[1]}):
                ImportBatch.objects.get_or_create(
                    id=legacy_batch,
                    defaults={'input_hash': f'legacy-batch-{legacy_batch}', 'status': 'done',
                              'note': '旧库批次（随修订一起导入）', 'stats': {}})
            for revision_id, batch_id, parent, created, reason, origin, catalog_hash, snapshot in revisions:
                obj, created_flag = Revision.objects.get_or_create(
                    id=revision_id,
                    defaults={
                        'parent_id': parent or '',
                        'catalog_hash': catalog_hash or '',
                        'snapshot': snapshot,
                        'reason': reason or '',
                        'origin': origin or 'legacy',
                        'created_at': parse_datetime(created) if created else None,
                        'batch_id': batch_id if batch_id else None,
                    })
                if created_flag:
                    stats['new_revisions'] += 1

            existing = set(ChangeLog.objects
                           .filter(revision_id__in=[r[0] for r in revisions])
                           .values_list('revision_id', 'entity_kind', 'entity_id', 'action',
                                        'before_hash', 'after_hash'))
            rows, seen_times = [], {}
            for revision_id, kind, entity_id, action, before, after in changes:
                key = (revision_id, kind, entity_id, action, before or '', after or '')
                if key in existing:
                    continue
                rows.append(ChangeLog(revision=Revision(id=revision_id), entity_kind=kind,
                                      entity_id=entity_id, action=action,
                                      before_hash=before or '', after_hash=after or '',
                                      note='迁移自旧库（旧库无时间戳）'))
                existing.add(key)
            ChangeLog.objects.bulk_create(rows, batch_size=500)
            stats['new_changes'] = len(rows)

            # 旧库没有单条时间，统一落成所属修订的时间
            for revision_id, created, *_ in [(r[0], r[3]) for r in revisions]:
                stamp = parse_datetime(created) if created else None
                if stamp:
                    (ChangeLog.objects.filter(revision_id=revision_id, note__startswith='迁移自旧库')
                     .update(created_at=stamp))

            batch.stats = {'revisions': stats['new_revisions'], 'changes': stats['new_changes']}
            batch.save(update_fields=['stats'])

        self.stdout.write(str(stats))
