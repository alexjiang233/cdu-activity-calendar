"""Small loopback-only content desk. No account system or public write service."""
import base64
import copy
import hashlib
import hmac
import json
import os
import secrets
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

import catalog_store as store
import manage_content as maintenance

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'scripts/admin'
REPOSITORY = 'alexjiang233/cdu-activity-calendar'
LIVE_URL = 'https://alexjiang233.github.io/cdu-activity-calendar/'
CATEGORIES = {'technology': '科技竞赛', 'creative': '文化创作', 'sports': '运动健身',
              'speech': '演讲表达', 'volunteering': '志愿服务', 'practice': '社会实践',
              'recruitment': '组织招募', 'learning': '学习发展', 'lecture': '学术讲座',
              'exchange': '国际交流', 'career': '生涯就业', 'reference': '参考资料'}
EDITABLE = {'title', 'category', 'category_label', 'editorial_note', 'featured', 'spotlight'}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def git_credential():
    """Use an existing credential only; never start login or expose it in output."""
    git = shutil.which('git')
    if not git:
        return None
    env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GCM_INTERACTIVE': 'Never'}
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        result = subprocess.run([git, '-c', 'credential.interactive=never', 'credential', 'fill'],
                                input='protocol=https\nhost=github.com\n\n', capture_output=True,
                                text=True, timeout=8, env=env, creationflags=flags)
        if result.returncode:
            return None
        fields = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        return fields.get('password')
    except (OSError, subprocess.TimeoutExpired):
        return None


class Desk:
    def __init__(self, db=store.DEFAULT_DB, data_dir=None, token=None, credentials=True):
        self.db = Path(db)
        self.data = Path(data_dir) if data_dir else self.db.parent
        self.state_path = self.data / 'admin-state.json'
        self.lock = threading.RLock()
        self.token = token or secrets.token_urlsafe(32)
        self.github_token = git_credential() if credentials else None
        self.job = None
        self.preview = None
        self.state = json.loads(self.state_path.read_text(encoding='utf-8')) if self.state_path.exists() else {
            'reviews': {}, 'override_fields': {}, 'inbox': [], 'last_published': None}
        self.state.setdefault('candidates', {})
        if not self.db.exists():
            release = ROOT / 'public/index.html'
            if not release.exists():
                release = ROOT / 'index.html'
            catalog, documents = maintenance.read_release(release)
            store.apply_catalog(catalog, 'desk-initial-restore', '从已发布网页恢复管理台', self.db, documents=documents)
        maintenance.health(self.db)
        baseline = ROOT / 'work/architecture-v1/verification.json'
        if self.state.get('last_published') is None and baseline.exists() and self.db.resolve() == store.DEFAULT_DB.resolve():
            verified = json.loads(baseline.read_text(encoding='utf-8'))
            if verified.get('status') == 'live_verified':
                self.state['last_published'] = verified.get('revision')

    def persist(self):
        write_json(self.state_path, self.state)

    def snapshot(self):
        catalog = store.load_catalog(self.db)
        return catalog, maintenance.get_revision(self.db)

    def busy(self):
        if self.job and self.job['status'] == 'running':
            raise ValueError('正在发布，请等发布结束后再修改。')

    def status(self):
        with self.lock:
            catalog, revision = self.snapshot()
            with store.connect(self.db) as c:
                last = c.execute('SELECT origin,parent_revision FROM revisions WHERE revision=?', (revision,)).fetchone()
            return {'app': 'cdu-content-desk-1', 'activities': len(catalog['entries']), 'notices': sum(len(e['versions']) for e in catalog['entries']),
                    'pending': sum(r['status'] == 'pending' for r in self.state['reviews'].values()),
                    'inbox': len(self.state['inbox']), 'revision': revision, 'can_publish': bool(self.github_token),
                    'unpublished': self.state.get('last_published') != revision,
                    'can_undo': bool(last and last['origin'] == 'local-admin' and last['parent_revision']),
                    'job': self.job, 'categories': CATEGORIES, 'preview_ready': bool(self.preview and self.preview['revision'] == revision),
                    'handoff_ready': bool(self.state.get('handoff'))}

    def entries(self, view='catalog', query='', page=1):
        with self.lock:
            catalog, revision = self.snapshot()
            entries = catalog['entries']
            if view == 'pending':
                combined = {e['id']: e for e in entries}
                combined.update(self.state['candidates'])
                entries = [e for e in combined.values() if self.state['reviews'].get(e['id'], {}).get('status') == 'pending']
            query = query.strip().lower()
            if query:
                entries = [e for e in entries if query in (e['title'] + ' ' + e.get('summary', '')).lower()]
            start = (max(1, page) - 1) * 20
            return {'revision': revision, 'total': len(entries), 'entries': [
                {'id': e['id'], 'title': e['title'], 'category': e['category_label'],
                 'selected': bool(e.get('spotlight')), 'years': sorted({v['year'] for v in e['versions'] if v.get('year')}, reverse=True),
                 'versions': len(e['versions'])} for e in entries[start:start + 20]]}

    def activity(self, entry_id, review=False):
        catalog, revision = self.snapshot()
        entry = next((e for e in catalog['entries'] if e['id'] == entry_id), None)
        pending = self.state['reviews'].get(entry_id, {}).get('status') == 'pending'
        if review and pending and entry_id in self.state['candidates']:
            entry = self.state['candidates'][entry_id]
        if entry is None:
            raise ValueError('没有找到这项活动，请刷新列表。')
        return {'entry': entry, 'revision': revision, 'pending': pending}

    def stage(self, candidate_catalog):
        """Called by the evidence-validated adapter, never by raw file upload."""
        with self.lock:
            self.busy()
            store.validate_catalog(candidate_catalog)
            current, _ = self.snapshot()
            previous = {e['id']: e for e in current['entries']}
            count = 0
            for entry in candidate_catalog['entries']:
                if entry == previous.get(entry['id']):
                    continue
                old_candidate = self.state['candidates'].get(entry['id'])
                if old_candidate == entry:
                    continue
                self.state['candidates'][entry['id']] = copy.deepcopy(entry)
                self.state['reviews'][entry['id']] = {'status': 'pending', 'existing': entry['id'] in previous}
                count += 1
            # Preserve vocabulary for new official college codes until accepted.
            self.state['candidate_colleges'] = candidate_catalog['colleges']
            self.state['candidate_levels'] = candidate_catalog['levels']
            self.persist()
            return {'status': 'staged', 'pending_added': count, 'message': '已准备待确认卡片，正式库和线上网站没有改变。'}

    def trial(self):
        with self.lock:
            self.busy()
            catalog, _ = self.snapshot()
            pool = [e for e in catalog['entries'] if e['id'] not in self.state['reviews']]
            pool.sort(key=lambda e: (not bool(e.get('spotlight')), not bool(e.get('featured'))))
            fresh = pool[:10]
            for e in fresh:
                self.state['reviews'][e['id']] = {'status': 'pending', 'existing': True}
            self.persist()
            return {'message': f'已放入 {len(fresh)} 项已收录活动供你试用，线上内容没有改变。'}

    def save(self, payload):
        with self.lock:
            self.busy()
            catalog, revision = self.snapshot()
            if payload.get('revision') != revision:
                raise ValueError('资料刚刚有更新。请刷新这张卡片后再保存，避免覆盖。')
            entry_id = payload.get('id')
            entry = next((e for e in catalog['entries'] if e['id'] == entry_id), None)
            candidate = self.state['candidates'].get(entry_id) if payload.get('review') and self.state['reviews'].get(entry_id, {}).get('status') == 'pending' else None
            if candidate:
                entry = copy.deepcopy(candidate)
            if entry is None:
                raise ValueError('活动不存在。')
            decision = payload.get('decision', 'save')
            if decision not in {'save', 'keep', 'selected', 'skip'}:
                raise ValueError('不支持的操作。')
            if decision == 'skip':
                self.state['reviews'][entry['id']] = {'status': 'skipped', 'existing': any(e['id'] == entry_id for e in catalog['entries'])}
                self.persist()
                return {'status': 'skipped', 'revision': revision, 'message': '已暂时跳过。已收录内容保持原样，新资料不会发布。'}
            changed = set()
            fields = payload.get('fields', {})
            if set(fields) - {'title', 'category', 'editorial_note'}:
                raise ValueError('这里只能修改活动名称、类型和补充说明。')
            for key, value in fields.items():
                if not isinstance(value, str):
                    raise ValueError('请输入文字。')
                value = value.strip()
                if key == 'title' and not 1 <= len(value) <= 160:
                    raise ValueError('活动名称请控制在1到160个字。')
                if key == 'editorial_note' and len(value) > 1200:
                    raise ValueError('说明太长了，请控制在1200个字以内。')
                if key == 'category' and value not in CATEGORIES:
                    raise ValueError('请从已有活动类型中选择。')
                if entry.get(key, '') != value:
                    entry[key] = value
                    changed.add(key)
                    if key == 'category':
                        entry['category_label'] = CATEGORIES[value]
                        changed.add('category_label')
            if decision in {'keep', 'selected'}:
                entry['featured'] = decision == 'selected' or entry['category'] not in {'lecture', 'reference'}
                entry['spotlight'] = decision == 'selected'
                changed.update({'featured', 'spotlight'})
            if candidate:
                if decision == 'save':
                    self.state['candidates'][entry_id] = entry
                    self.persist()
                    return {'status': 'draft_saved', 'revision': revision, 'message': '待确认卡片已保存，还没有收录或发布。'}
                catalog['entries'] = [entry if e['id'] == entry_id else e for e in catalog['entries']]
                if not any(e['id'] == entry_id for e in catalog['entries']):
                    catalog['entries'].append(entry)
                catalog['colleges'].update(self.state.get('candidate_colleges', {}))
                catalog['levels'].update(self.state.get('candidate_levels', {}))
            if not changed and not candidate:
                return {'status': 'unchanged', 'revision': revision, 'message': '没有需要保存的修改。'}
            store.validate_catalog(catalog)
            # Keep both content and operation journal recoverable before mutation.
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
            maintenance.backup(self.db, self.data / 'backups' / ('desk-' + stamp + '.sqlite3'))
            if self.state_path.exists():
                shutil.copyfile(self.state_path, self.data / 'backups' / ('desk-' + stamp + '-admin-state.json'))
            # Journal field ownership before commit, so a crash cannot silently
            # hand edited fields back to an automated legacy import.
            self.state['override_fields'][entry['id']] = sorted(set(self.state['override_fields'].get(entry['id'], [])) | changed)
            self.persist()
            result = store.apply_catalog(catalog, 'desk-' + stamp, '管理页：' + entry['title'], self.db,
                                         expected_revision=revision, origin='local-admin')
            if decision in {'keep', 'selected'}:
                self.state['reviews'][entry['id']] = {'status': decision, 'existing': True}
            self.persist()
            return {**result, 'message': '已保存到本机。预览满意后再发布到网站。'}

    def undo(self, revision):
        with self.lock:
            self.busy()
            if maintenance.get_revision(self.db) != revision:
                raise ValueError('内容已改变，请刷新后再撤销。')
            with store.connect(self.db) as c:
                row = c.execute('SELECT parent_revision,origin FROM revisions WHERE revision=?', (revision,)).fetchone()
            if not row or row['origin'] != 'local-admin' or not row['parent_revision']:
                raise ValueError('当前没有可撤销的管理页修改。')
            result = store.rollback(row['parent_revision'], 'undo-' + secrets.token_hex(8), '管理页：撤销上次修改', self.db, revision)
            with store.connect(self.db) as c:
                changed_ids = [r['entity_id'] for r in c.execute('SELECT entity_id FROM changes WHERE revision=?', (revision,))]
            for entry_id in changed_ids:
                if entry_id in self.state['reviews']:
                    self.state['reviews'][entry_id] = {'status': 'pending', 'existing': True}
            self.persist()
            return {**result, 'message': '已恢复修改前的内容。线上网站尚未改变。'}

    def make_preview(self):
        with self.lock:
            self.busy()
            maintenance.health(self.db)
            _, revision = self.snapshot()
            from share_demo import share_html
            page = share_html(None, public_only=True, database=self.db)
            folder = self.data / 'admin-preview'
            folder.mkdir(parents=True, exist_ok=True)
            target = folder / 'index.html'
            target.write_bytes(page.encode('utf-8'))
            self.preview = {'revision': revision, 'path': target, 'sha256': hashlib.sha256(page.encode()).hexdigest()}
            return {'message': '预览已准备好。', 'url': '/preview/#discover', 'revision': revision}

    def handoff(self):
        with self.lock:
            self.busy()
            revision = maintenance.get_revision(self.db)
            if not self.preview or self.preview['revision'] != revision:
                raise ValueError('先点“生成预览”，看过效果后再准备发布。')
            if hashlib.sha256(self.preview['path'].read_bytes()).hexdigest() != self.preview['sha256']:
                raise ValueError('预览文件发生变化，请重新生成。')
            folder = self.data / 'publish-outbox'
            folder.mkdir(parents=True, exist_ok=True)
            release = folder / 'index.html'
            shutil.copyfile(self.preview['path'], release)
            request = {'status': 'awaiting_publisher', 'revision': revision, 'sha256': self.preview['sha256'],
                       'repository': REPOSITORY, 'release': str(release)}
            write_json(folder / 'request.json', request)
            prompt = ('请发布本地活动管理页准备好的修改。发布文件：' + str(release) +
                      '。先核对同目录request.json与当前数据库版本，运行隐私和构建检查，再提交' + REPOSITORY +
                      '并核验GitHub Pages。成功后更新data/admin-state.json里的last_published为本次revision，保留审核与手动修改记录。')
            (folder / '发给Sol.txt').write_text(prompt, encoding='utf-8')
            self.state['handoff'] = request
            self.job = None
            self.persist()
            return {'message': '发布文件已准备好，还没有上线。复制下面这句话发给Sol即可。', 'prompt': prompt}

    def upload(self, filename, raw):
        with self.lock:
            name = Path(filename.replace('\\', '/')).name
            if not name or len(name) > 180 or Path(name).suffix.lower() not in {'.pdf', '.doc', '.docx', '.txt', '.html', '.zip', '.xlsx', '.xls', '.png', '.jpg', '.jpeg'}:
                raise ValueError('支持公告文档、表格、图片和ZIP资料包。')
            folder = self.data / 'inbox'
            folder.mkdir(parents=True, exist_ok=True)
            path = folder / (secrets.token_hex(6) + '-' + name)
            path.write_bytes(raw)
            self.state['inbox'].append({'name': name, 'path': str(path), 'size': len(raw)})
            self.persist()
            return {'message': '文件已留在本机资料箱，尚未提取或发布。', 'name': name}

    def inbox_request(self):
        return {'prompt': '请整理本地活动管理台资料箱：' + str(self.data / 'inbox') +
                '。逐条读取原文和附件、核验证据后，用manage_content.py prepare-review放入待确认卡片，先不发布。保留原件，不恢复其他暂停队列。'}

    def github(self, method, suffix, body=None):
        data = json.dumps(body).encode() if body is not None else None
        accept = 'application/vnd.github.object+json' if method == 'GET' and suffix.startswith('/contents/') else 'application/vnd.github+json'
        request = urllib.request.Request('https://api.github.com/repos/' + REPOSITORY + suffix, data=data, method=method,
                                         headers={'Authorization': 'Bearer ' + self.github_token, 'Accept': accept,
                                                  'User-Agent': 'CDU-Local-Desk', 'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.load(response)

    def publish(self):
        with self.lock:
            self.busy()
            if not self.github_token:
                return self.handoff()
            revision = maintenance.get_revision(self.db)
            if not self.preview or self.preview['revision'] != revision:
                raise ValueError('内容有变化，请先重新生成预览。')
            page = self.preview['path'].read_bytes()
            if hashlib.sha256(page).hexdigest() != self.preview['sha256']:
                raise ValueError('预览文件发生变化，请重新生成。')
            self.job = {'status': 'running', 'message': '正在上传，先别关闭管理页。'}
            threading.Thread(target=self._publish_worker, args=(page, revision), daemon=True).start()
            return {'message': self.job['message'], 'started': True}

    def _publish_worker(self, page, revision):
        try:
            remote = self.github('GET', '/contents/index.html?ref=main')
            blob_sha = hashlib.sha1(b'blob ' + str(len(page)).encode() + b'\0' + page).hexdigest()
            commit = None
            if remote['sha'] != blob_sha:
                updated = self.github('PUT', '/contents/index.html', {'message': 'Update activities from local content desk',
                                      'branch': 'main', 'sha': remote['sha'], 'content': base64.b64encode(page).decode()})
                commit = updated['commit']['sha']
            self.job = {'status': 'running', 'message': '已上传，正在等网站更新。'}
            for _ in range(24):
                try:
                    with urllib.request.urlopen(LIVE_URL + '?desk=' + secrets.token_hex(6), timeout=15) as response:
                        live = response.read().decode('utf-8').replace('\r\n', '\n')
                    if live == page.decode('utf-8').replace('\r\n', '\n'):
                        with self.lock:
                            self.state['last_published'] = revision
                            self.state.pop('handoff', None)
                            self.persist()
                            self.job = {'status': 'success', 'message': '已上线，线上内容检查通过。', 'commit': commit, 'url': LIVE_URL}
                        return
                except (OSError, UnicodeError):
                    pass
                time.sleep(5)
            self.job = {'status': 'error', 'message': '文件已上传，但还没确认网站更新。请让Sol检查发布进度，不必重复上传。', 'commit': commit}
        except (OSError, KeyError, ValueError):
            self.job = {'status': 'error', 'message': '发布未完成，网站原有内容仍可访问。可使用“交给Sol发布”。'}


class Handler(BaseHTTPRequestHandler):
    server_version = 'CampusDesk'

    def log_message(self, *args):
        pass

    def send(self, status, body, content_type='application/json; charset=utf-8'):
        raw = json.dumps(body, ensure_ascii=False).encode() if isinstance(body, (dict, list)) else body
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'SAMEORIGIN' if self.path.startswith('/preview/') else 'DENY')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.end_headers()
        self.wfile.write(raw)

    def allowed_host(self):
        return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}

    def do_GET(self):
        if not self.allowed_host():
            return self.send(403, {'error': '请从本机入口打开。'})
        desk = self.server.desk
        path = urlsplit(self.path)
        params = parse_qs(path.query)
        try:
            if path.path == '/api/status':
                return self.send(200, desk.status())
            if path.path == '/favicon.ico':
                return self.send(204, b'', 'image/x-icon')
            if path.path == '/api/list':
                return self.send(200, desk.entries(params.get('view', ['catalog'])[0], params.get('q', [''])[0], int(params.get('page', ['1'])[0])))
            if path.path == '/api/activity':
                return self.send(200, desk.activity(params.get('id', [''])[0], params.get('review', [''])[0] == '1'))
            if path.path == '/preview/':
                if not desk.preview:
                    raise ValueError('请先生成预览。')
                return self.send(200, desk.preview['path'].read_bytes(), 'text/html; charset=utf-8')
            assets = {'/': ('index.html', 'text/html; charset=utf-8'), '/admin.js': ('admin.js', 'text/javascript; charset=utf-8'),
                      '/admin.css': ('admin.css', 'text/css; charset=utf-8'), '/guide.svg': ('guide.svg', 'image/svg+xml')}
            if path.path in assets:
                name, kind = assets[path.path]
                raw = (ASSETS / name).read_bytes()
                if path.path == '/':
                    raw = raw.replace(b'__DESK_TOKEN__', desk.token.encode())
                return self.send(200, raw, kind)
            return self.send(404, {'error': '页面不存在。'})
        except (ValueError, OSError, KeyError) as exc:
            self.send(400, {'error': str(exc)})

    def do_POST(self):
        expected = {f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'}
        token = self.headers.get('X-Desk-Token', '')
        if not self.allowed_host() or self.headers.get('Origin') not in expected or not hmac.compare_digest(token, self.server.desk.token):
            return self.send(403, {'error': '请刷新本机管理页后重试。'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            path = urlsplit(self.path)
            limit = 50 * 1024 * 1024 if path.path == '/api/upload' else 100000
            if not 0 < length <= limit:
                return self.send(413, {'error': '文件太大；单个文件请控制在50MB以内。'})
            raw = self.rfile.read(length)
            desk = self.server.desk
            if path.path == '/api/upload':
                from urllib.parse import unquote
                return self.send(200, desk.upload(unquote(self.headers.get('X-Filename', '')), raw))
            data = json.loads(raw)
            if not isinstance(data, dict):
                raise ValueError('请求格式不正确，请刷新管理页。')
            routes = {'/api/trial': lambda: desk.trial(), '/api/save': lambda: desk.save(data),
                      '/api/undo': lambda: desk.undo(data.get('revision')), '/api/preview': lambda: desk.make_preview(),
                      '/api/publish': lambda: desk.publish(), '/api/handoff': lambda: desk.handoff(),
                      '/api/inbox-request': lambda: desk.inbox_request()}
            if path.path not in routes:
                return self.send(404, {'error': '操作不存在。'})
            self.send(200, routes[path.path]())
        except (ValueError, OSError, KeyError) as exc:
            self.send(400, {'error': str(exc)})


def serve(port=8768, db=store.DEFAULT_DB, credentials=True):
    desk = Desk(db, credentials=credentials)
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.desk = desk
    write_json(desk.data / 'admin-launch.json', {'url': f'http://127.0.0.1:{server.server_port}/', 'pid': os.getpid()})
    server.serve_forever()


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8768)
    parser.add_argument('--db', type=Path, default=store.DEFAULT_DB)
    parser.add_argument('--no-publish', action='store_true', help='验证界面时禁用云端授权')
    options = parser.parse_args()
    serve(options.port, options.db, not options.no_publish)
