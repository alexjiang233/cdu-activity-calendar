import copy
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import catalog_store as store
import manage_content as manage


def fixture():
    return {'schema_version': 'catalog-1', 'colleges': {'film': '影视与动画学院'},
            'levels': {'campus': '校级'}, 'entries': [
                {'id': 'activity-a', 'title': '校园创作比赛', 'kind': 'notice', 'category': 'creative',
                 'featured': True, 'spotlight': False, 'material_ids': [], 'summary': '作品征集',
                 'versions': [{'year': 2025, 'published': '2025-10-01', 'deadline': '2025-11-30T24:00',
                               'deadline_kind': 'submission', 'stage_start': None, 'stage_end': None,
                               'audience': '全校学生', 'conflict': False, 'colleges': ['film'],
                               'levels': ['campus'], 'source_url': 'https://news.cdu.edu.cn/info/1/2.htm',
                               'participation_facts': [{'kind': 'materials', 'value': '提交三幅原创作品。',
                                                        'quote': '提交三幅原创作品。', 'locator': '材料1',
                                                        'source_url': 'https://news.cdu.edu.cn/info/1/2.htm'}],
                               'content_profile': {'sections': [], 'attachments': [], 'pending': []}}]}],
            'coverage': None, 'college_policy': '组织相关不代表报名资格'}


DOCUMENTS = {'batch': {'schema_version': 'official-public-1', 'records': [], 'inventory': []},
             'verification': {'records': [], 'checked_on': '2026-10-18'}}


class CatalogStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / 'campus.sqlite3'
        self.catalog = fixture()
        self.first = store.apply_catalog(self.catalog, 'initial', 'test baseline', self.db, documents=DOCUMENTS)['revision']

    def tearDown(self):
        self.temp.cleanup()

    def test_lossless_roundtrip_and_indexed_associations(self):
        self.assertEqual(store.load_catalog(self.db), self.catalog)
        self.assertEqual(manage.health(self.db)['facts'], 1)
        with store.connect(self.db) as c:
            self.assertEqual(c.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual(c.execute('SELECT url FROM sources').fetchone()[0], self.catalog['entries'][0]['versions'][0]['source_url'])

    def test_repeat_import_is_noop(self):
        result = store.apply_catalog(self.catalog, 'repeat', 'same content', self.db, self.first)
        self.assertEqual(result['status'], 'unchanged')
        self.assertEqual(manage.health(self.db)['revisions'], 1)

    def test_stale_revision_cannot_overwrite(self):
        with self.assertRaisesRegex(ValueError, '数据库已变更'):
            store.apply_catalog(self.catalog, 'stale', 'stale', self.db, 'wrong')
        self.assertEqual(manage.health(self.db)['revision'], self.first)

    def test_failed_transaction_preserves_original_and_history(self):
        updated = copy.deepcopy(self.catalog)
        updated['entries'][0]['summary'] = '调整说明'
        with patch.object(store, '_write_catalog', side_effect=RuntimeError('simulated interruption')):
            with self.assertRaises(RuntimeError):
                store.apply_catalog(updated, 'failed', 'interruption', self.db, self.first)
        self.assertEqual(store.load_catalog(self.db), self.catalog)
        self.assertEqual(manage.health(self.db)['revisions'], 1)

    def test_rollback_is_new_revision_and_keeps_history(self):
        changed = copy.deepcopy(self.catalog)
        changed['entries'][0]['title'] = '校园原创作品比赛'
        second = store.apply_catalog(changed, 'update', 'rename', self.db, self.first)['revision']
        restored = store.rollback(self.first, 'rollback', 'restore previous', self.db, second)
        self.assertNotEqual(restored['revision'], self.first)
        self.assertEqual(store.load_catalog(self.db), self.catalog)
        self.assertEqual(manage.health(self.db)['revisions'], 3)

    def test_removal_requires_explicit_flag(self):
        removed = {**self.catalog, 'entries': []}
        with self.assertRaisesRegex(ValueError, '移除历史公告'):
            store.apply_catalog(removed, 'remove', 'remove', self.db, self.first)
        self.assertEqual(store.load_catalog(self.db), self.catalog)

    def test_duplicate_url_fragments_and_private_data_are_rejected(self):
        duplicate = copy.deepcopy(self.catalog)
        other = copy.deepcopy(duplicate['entries'][0])
        other['id'] = 'another'
        other['versions'][0]['source_url'] += '#section'
        duplicate['entries'].append(other)
        with self.assertRaisesRegex(ValueError, '来源异常或重复'):
            store.apply_catalog(duplicate, 'dup', 'dup', self.db, self.first)
        private = copy.deepcopy(self.catalog)
        private['entries'][0]['summary'] = '联系 private@example.com'
        with self.assertRaisesRegex(ValueError, '私人信息'):
            store.apply_catalog(private, 'private', 'private', self.db, self.first)

    def test_bad_dates_and_taxonomy_are_rejected(self):
        for field, value in [('published', '2026-02-30'), ('year', '2026'), ('colleges', ['invented'])]:
            changed = copy.deepcopy(self.catalog)
            changed['entries'][0]['versions'][0][field] = value
            with self.assertRaises(ValueError):
                store.apply_catalog(changed, 'bad', 'bad', self.db, self.first)

    def test_direct_sql_edits_fail_closed_on_build(self):
        with sqlite3.connect(self.db, factory=store.Connection) as c:
            c.execute("UPDATE activities SET title='untracked modification'")
        with self.assertRaisesRegex(ValueError, '版本记录不一致'):
            store.load_site_data(self.db)
        with self.assertRaisesRegex(ValueError, '版本记录不一致'):
            store.apply_catalog(self.catalog, 'overwrite', 'overwrite', self.db, self.first)

    def test_backup_can_be_opened_without_original_database(self):
        dest = Path(self.temp.name) / 'backup.sqlite3'
        manage.backup(self.db, dest)
        self.assertEqual(store.load_catalog(dest), self.catalog)
        with self.assertRaisesRegex(ValueError, '拒绝覆盖'):
            manage.backup(self.db, dest)

    def test_build_does_not_run_legacy_processing(self):
        import share_demo
        with patch.object(share_demo, 'build_catalog', side_effect=AssertionError('legacy catalog used')), \
             patch.object(share_demo, 'public_data', side_effect=AssertionError('legacy evidence used')), \
             patch.object(share_demo, 'expansion_data', side_effect=AssertionError('legacy intake used')):
            page = share_demo.share_html(None, public_only=True, database=self.db)
        self.assertIn('校园创作比赛', page)
        self.assertIn('提交三幅原创作品', page)

    def test_fact_ids_survive_insertion_and_notice_moves(self):
        with store.connect(self.db) as c:
            original = c.execute('SELECT id FROM facts').fetchone()[0]
        updated = copy.deepcopy(self.catalog)
        updated['entries'][0]['id'] = 'new-series-id'
        v = updated['entries'][0]['versions'][0]
        v['participation_facts'].insert(0, {'kind': 'audience', 'value': '全校学生', 'quote': '全校学生'})
        store.apply_catalog(updated, 'regroup', 'move series', self.db, self.first)
        with store.connect(self.db) as c:
            self.assertIn(original, [r[0] for r in c.execute('SELECT id FROM facts')])

    def test_missing_database_does_not_create_blank_file(self):
        missing = Path(self.temp.name) / 'missing.sqlite3'
        with self.assertRaises(sqlite3.OperationalError):
            store.load_catalog(missing)
        self.assertFalse(missing.exists())
