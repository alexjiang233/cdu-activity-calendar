import copy
import hashlib
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import catalog_store as store
from admin_server import Desk, Handler
from test_catalog_store import fixture, DOCUMENTS


class DeskTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / 'campus.sqlite3'
        self.catalog = fixture()
        self.revision = store.apply_catalog(self.catalog, 'initial', 'fixture', self.db, documents=DOCUMENTS)['revision']
        self.desk = Desk(self.db, credentials=False)

    def tearDown(self):
        self.temp.cleanup()

    def save(self, **values):
        return self.desk.save({'id': 'activity-a', 'revision': self.revision, 'decision': 'save', **values})

    def test_trial_and_skip_do_not_modify_official_data(self):
        self.assertEqual(self.desk.status()['pending'], 0)
        self.desk.trial()
        self.assertEqual(self.desk.status()['pending'], 1)
        self.save(decision='skip')
        self.assertEqual(store.load_catalog(self.db), self.catalog)
        self.assertEqual(self.desk.status()['revision'], self.revision)
        self.assertEqual(Desk(self.db, credentials=False).status()['pending'], 0)

    def test_edit_and_undo_preserve_source_facts(self):
        original_version = copy.deepcopy(self.catalog['entries'][0]['versions'][0])
        result = self.save(decision='selected', fields={'title': '校园原创作品赛', 'editorial_note': '适合喜欢创作的同学。'})
        updated = store.load_catalog(self.db)['entries'][0]
        self.assertTrue(updated['spotlight'])
        self.assertEqual(updated['versions'][0], original_version)
        self.assertEqual(len(list((Path(self.temp.name) / 'backups').glob('*.sqlite3'))), 1)
        self.desk.undo(result['revision'])
        self.assertEqual(store.load_catalog(self.db), self.catalog)

    def test_stale_editor_cannot_overwrite(self):
        self.save(fields={'title': '第一次修改'})
        with self.assertRaisesRegex(ValueError, '刚刚有更新'):
            self.save(fields={'title': '过期修改'})

    def test_private_notes_and_date_edits_are_blocked(self):
        with self.assertRaises(ValueError):
            self.save(fields={'editorial_note': '邮箱 someone@example.com'})
        with self.assertRaises(ValueError):
            self.save(fields={'deadline': '2026-10-01'})
        self.assertEqual(store.load_catalog(self.db), self.catalog)

    def test_preview_required_and_stale_preview_is_rejected(self):
        with self.assertRaisesRegex(ValueError, '生成预览'):
            self.desk.handoff()
        self.desk.make_preview()
        self.save(fields={'title': '预览之后的新修改'})
        with self.assertRaisesRegex(ValueError, '生成预览'):
            self.desk.handoff()

    def test_handoff_is_explicitly_not_online_and_hash_matches(self):
        self.save(fields={'editorial_note': '一条补充介绍'})
        self.desk.make_preview()
        with patch.object(self.desk, 'github', side_effect=AssertionError('unexpected upload')):
            result = self.desk.publish()
        self.assertIn('还没有上线', result['message'])
        request = json.loads((Path(self.temp.name) / 'publish-outbox/request.json').read_text(encoding='utf-8'))
        raw = (Path(self.temp.name) / 'publish-outbox/index.html').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), request['sha256'])
        self.assertEqual(request['status'], 'awaiting_publisher')
        self.assertIn('一条补充介绍', raw.decode('utf-8'))
        self.assertIsNone(self.desk.state['last_published'])

    def test_tampered_preview_cannot_be_published(self):
        self.desk.make_preview()
        self.desk.preview['path'].write_text('tampered', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, '发生变化'):
            self.desk.handoff()

    def test_uploaded_files_are_local_only_and_paths_are_confined(self):
        self.desk.upload('../../source.txt', b'original-content')
        item = self.desk.state['inbox'][0]
        path = Path(item['path'])
        self.assertTrue(path.resolve().is_relative_to((Path(self.temp.name) / 'inbox').resolve()))
        self.assertEqual(path.read_bytes(), b'original-content')
        self.assertEqual(self.desk.status()['pending'], 0)
        self.assertEqual(store.load_catalog(self.db), self.catalog)

    def test_legacy_updates_preserve_only_owned_editorial_fields(self):
        self.save(fields={'title': '手动名称', 'editorial_note': '手动说明'})
        fresh = copy.deepcopy(self.catalog)
        merged = store.preserve_editorial(fresh, store.load_catalog(self.db),
                                         {'activity-a': ['title', 'editorial_note', 'versions']})
        self.assertEqual(merged['entries'][0]['title'], '手动名称')
        self.assertEqual(merged['entries'][0]['versions'], self.catalog['entries'][0]['versions'])

    def test_new_candidate_is_excluded_until_explicit_acceptance(self):
        proposed = copy.deepcopy(self.catalog)
        entry = copy.deepcopy(proposed['entries'][0])
        entry['id'] = 'new-candidate'
        entry['title'] = '新的校园作品征集'
        entry['versions'][0]['source_url'] = 'https://news.cdu.edu.cn/info/1/3.htm'
        proposed['entries'].append(entry)
        self.desk.stage(proposed)
        self.assertEqual(len(store.load_catalog(self.db)['entries']), 1)
        self.desk.make_preview()
        self.assertNotIn('新的校园作品征集', self.desk.preview['path'].read_text(encoding='utf-8'))
        self.desk.save({'id': 'new-candidate', 'revision': self.revision, 'review': True, 'decision': 'selected'})
        self.assertEqual(len(store.load_catalog(self.db)['entries']), 2)
        self.desk.make_preview()
        self.assertIn('新的校园作品征集', self.desk.preview['path'].read_text(encoding='utf-8'))

    def test_skipped_candidate_never_enters_database(self):
        proposed = copy.deepcopy(self.catalog)
        proposed['entries'][0]['title'] = '尚未确认的新标题'
        self.desk.stage(proposed)
        self.assertEqual(self.desk.activity('activity-a')['entry']['title'], '校园创作比赛')
        self.assertEqual(self.desk.activity('activity-a', True)['entry']['title'], '尚未确认的新标题')
        self.save(decision='skip', review=True)
        self.assertEqual(store.load_catalog(self.db), self.catalog)

    def test_publisher_marks_live_only_after_exact_match(self):
        import io
        page = b'<html>verified preview</html>'
        with patch.object(self.desk, 'github', side_effect=[{'sha': 'previous'}, {'commit': {'sha': 'test-commit'}}]), \
             patch('admin_server.urllib.request.urlopen', return_value=io.BytesIO(page)):
            self.desk._publish_worker(page, self.revision)
        self.assertEqual(self.desk.job['status'], 'success')
        self.assertEqual(self.desk.state['last_published'], self.revision)

    def test_upload_without_live_confirmation_is_not_success(self):
        with patch.object(self.desk, 'github', return_value={'sha': 'old', 'commit': {'sha': 'uploaded'}}), \
             patch('admin_server.urllib.request.urlopen', side_effect=OSError('offline')), \
             patch('admin_server.time.sleep'):
            self.desk._publish_worker(b'<html>preview</html>', self.revision)
        self.assertEqual(self.desk.job['status'], 'error')
        self.assertIsNone(self.desk.state['last_published'])


class HttpBoundaryTests(unittest.TestCase):
    def setUp(self):
        DeskTests.setUp(self)
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.desk = self.desk
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.origin = 'http://127.0.0.1:' + str(self.server.server_port)

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        DeskTests.tearDown(self)

    def request(self, path, data=None, origin=None, token=None, host=None):
        headers = {}
        if origin is not None: headers['Origin'] = origin
        if token is not None: headers['X-Desk-Token'] = token
        if host is not None: headers['Host'] = host
        req = urllib.request.Request(self.origin + path, data=json.dumps(data).encode() if data is not None else None, headers=headers)
        return urllib.request.urlopen(req, timeout=5)

    def test_writes_require_origin_and_token(self):
        for origin, token in [(None, None), ('https://other.example', self.desk.token), (self.origin, 'wrong')]:
            with self.assertRaises(urllib.error.HTTPError) as caught:
                self.request('/api/trial', {}, origin, token)
            self.assertEqual(caught.exception.code, 403)
        with self.request('/api/trial', {}, self.origin, self.desk.token) as response:
            self.assertEqual(response.status, 200)

    def test_no_raw_directory_or_host_rebinding_access(self):
        for path, host, code in [('/data/campus.sqlite3', None, 404), ('/../../data/campus.sqlite3', None, 404), ('/api/status', 'other.example', 403)]:
            with self.assertRaises(urllib.error.HTTPError) as caught:
                self.request(path, host=host)
            self.assertEqual(caught.exception.code, code)
