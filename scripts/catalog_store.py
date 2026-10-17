"""SQLite content repository with lossless public projection and atomic revisions.

Only validated public catalog projections enter this database. Raw documents and
private evidence stay in their existing folders. Legacy import remains an explicit
adapter; normal website builds never rerun historical ingestion.
"""
import gzip
import hashlib
import json
import re
import sqlite3
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urldefrag

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / 'data/campus.sqlite3'
SCHEMA = ROOT / 'scripts/schema/001_initial.sql'
ACTIVITY_FIELDS = ('id', 'title', 'kind', 'category', 'featured', 'spotlight')
NOTICE_FIELDS = ('year', 'published', 'deadline', 'deadline_kind', 'stage_start',
                 'stage_end', 'audience', 'conflict')
FACT_FIELDS = ('kind', 'value', 'quote', 'locator', 'source_url', 'basis')


class Connection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def digest(value):
    return hashlib.sha256(dump(value).encode('utf-8')).hexdigest()


def split_payload(value, fields, nested=()):
    return dump({k: v for k, v in value.items() if k not in fields and k not in nested}), dump(list(value))


def assemble(extra, layout, fields):
    values = json.loads(extra)
    values.update(fields)
    return {key: values[key] for key in json.loads(layout) if key in values}


def official_url(url):
    try:
        p = urlsplit(url)
        return p.scheme in {'https', 'http'} and not p.username and not p.password and (
            p.hostname == 'cdu.edu.cn' or (p.hostname or '').endswith('.cdu.edu.cn'))
    except (TypeError, ValueError):
        return False


def valid_date(value):
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    m = re.fullmatch(r'(\d{4}-\d{2}-\d{2})(?:T((?:[01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?|24:00(?::00)?))?', value)
    if not m:
        return False
    try:
        date.fromisoformat(m[1])
        return True
    except ValueError:
        return False


def validate_catalog(catalog):
    from public_guard import check_public
    if not isinstance(catalog, dict) or catalog.get('schema_version') != 'catalog-1':
        raise ValueError('不支持的数据版本')
    if not isinstance(catalog.get('entries'), list):
        raise ValueError('活动列表缺失')
    for key in ('colleges', 'levels'):
        if not isinstance(catalog.get(key), dict):
            raise ValueError('分类词表缺失：' + key)
    ids, urls = set(), set()
    for entry in catalog['entries']:
        if not isinstance(entry.get('id'), str) or not entry['id'] or entry['id'] in ids:
            raise ValueError('活动 ID 缺失或重复')
        ids.add(entry['id'])
        categories = {'sports', 'creative', 'technology', 'speech', 'volunteering', 'learning',
                      'lecture', 'exchange', 'practice', 'recruitment', 'career', 'reference'}
        if not entry.get('title') or entry.get('category') not in categories or entry.get('kind') not in {'official', 'notice'}:
            raise ValueError('活动缺少名称、类别或公开来源类型：' + entry['id'])
        if entry.get('material_ids'):
            raise ValueError('公开活动不能包含本地材料引用')
        if not entry.get('versions'):
            raise ValueError('活动缺少公告版本：' + entry['id'])
        for v in entry['versions']:
            url = v.get('source_url')
            canonical = urldefrag(url)[0] if isinstance(url, str) else None
            if not official_url(url) or canonical in urls:
                raise ValueError('公告来源异常或重复：' + str(url))
            urls.add(canonical)
            if v.get('year') is not None and (type(v['year']) is not int or not 1900 <= v['year'] <= 2100):
                raise ValueError('公告年份不合法')
            for field in ('published', 'deadline', 'stage_start', 'stage_end'):
                if not valid_date(v.get(field)):
                    raise ValueError('日期格式不合法：' + field)
            if v.get('stage_start') and v.get('stage_end') and v['stage_end'][:10] < v['stage_start'][:10]:
                raise ValueError('活动结束时间早于开始时间')
            for c in v.get('colleges', []):
                if c not in catalog['colleges']:
                    raise ValueError('学院代码不在词表中')
            for level in v.get('levels', []):
                if level not in catalog['levels']:
                    raise ValueError('级别代码不在词表中')
            scope = v.get('audience_scope')
            if scope:
                if scope.get('kind') not in {'unknown', 'campus', 'college'} or any(
                        code not in catalog['colleges'] for code in scope.get('colleges', [])):
                    raise ValueError('参与对象范围不在规范词表中')
            for window in v.get('registration_windows', []):
                if not window.get('start') or not window.get('end') or not valid_date(window['start']) or not valid_date(window['end']) or window['start'] > window['end']:
                    raise ValueError('报名期不合法')
            for fact in v.get('participation_facts', []):
                if not all(isinstance(fact.get(k), str) and fact[k].strip() for k in ('kind', 'value', 'quote')):
                    raise ValueError('分条事实缺少类别、内容或引文：' + url)
                if fact.get('source_url') and not official_url(fact['source_url']):
                    raise ValueError('分条事实来源异常')
    check_public(dump(catalog))


def connect(path=DEFAULT_DB, initialize=False):
    path = Path(path)
    if initialize:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(path, factory=Connection)
    else:
        # Read-only callers must never create an empty replacement database.
        connection = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True, factory=Connection)
    connection.row_factory = sqlite3.Row
    connection.execute('PRAGMA foreign_keys=ON')
    version = connection.execute('PRAGMA user_version').fetchone()[0]
    if initialize and version == 0:
        connection.executescript(SCHEMA.read_text(encoding='utf-8'))
        connection.commit()
        version = 1
    if version != 1:
        connection.close()
        raise ValueError('数据库版本不兼容，停止操作')
    return connection


def notice_id(version):
    # A notice keeps its identity even if later moved into a different series.
    return 'notice-' + hashlib.sha256(urldefrag(version['source_url'])[0].encode()).hexdigest()[:24]


def read_catalog(connection):
    meta = connection.execute('SELECT * FROM catalog_metadata WHERE id=1').fetchone()
    if not meta:
        raise ValueError('数据库尚未导入；先执行 migrate 或 sync-legacy')
    vocab = {}
    for kind in ('college', 'level'):
        vocab[kind] = {r['code']: r['label'] for r in connection.execute(
            'SELECT code,label FROM taxonomy WHERE kind=? ORDER BY position', (kind,))}
    facts, profiles, colleges, levels = {}, {}, {}, {}
    for r in connection.execute('SELECT * FROM facts ORDER BY notice_id,position'):
        fields = {key: r[key] for key in FACT_FIELDS}
        facts.setdefault(r['notice_id'], []).append(assemble(r['extras'], r['layout'], fields))
    for r in connection.execute('SELECT * FROM profiles'):
        profiles[r['notice_id']] = json.loads(r['payload'])
    for r in connection.execute('SELECT * FROM notice_taxonomy ORDER BY position'):
        target = colleges if r['kind'] == 'college' else levels
        target.setdefault(r['notice_id'], []).append(r['code'])
    notices = {}
    for r in connection.execute('SELECT n.*,s.url FROM notices n JOIN sources s ON s.id=n.source_id ORDER BY n.position'):
        fields = {key: bool(r[key]) if key == 'conflict' else r[key] for key in NOTICE_FIELDS}
        fields.update(source_url=r['url'], participation_facts=facts.get(r['id'], []),
                      content_profile=profiles.get(r['id']), colleges=colleges.get(r['id'], []),
                      levels=levels.get(r['id'], []))
        notices.setdefault(r['activity_id'], []).append(assemble(r['extras'], r['layout'], fields))
    entries = []
    for r in connection.execute('SELECT * FROM activities ORDER BY position'):
        fields = {key: bool(r[key]) if key in {'featured', 'spotlight'} else r[key] for key in ACTIVITY_FIELDS}
        fields['versions'] = notices.get(r['id'], [])
        entries.append(assemble(r['extras'], r['layout'], fields))
    return assemble(meta['extras'], meta['layout'], {'entries': entries, 'colleges': vocab['college'], 'levels': vocab['level']})


def load_catalog(path=None):
    return load_site_data(path)[0]


def load_site_data(path=None):
    with connect(path or DEFAULT_DB) as connection:
        catalog = read_catalog(connection)
        documents = {r['name']: json.loads(r['payload']) for r in connection.execute('SELECT * FROM site_documents')}
        validate_catalog(catalog)
        validate_documents(documents)
        revision = current_revision(connection)
        row = connection.execute('SELECT catalog_hash FROM revisions WHERE revision=?', (revision,)).fetchone()
        if row is None or row['catalog_hash'] != digest({'catalog': catalog, 'documents': documents}):
            raise ValueError('数据库内容与版本记录不一致，停止导出')
        return catalog, documents['batch'], documents['verification']


def validate_documents(documents):
    from public_guard import check_public
    if set(documents) != {'batch', 'verification'}:
        raise ValueError('网站公开数据包缺少 batch 或 verification')
    batch = documents['batch']
    if batch.get('records') != [] or batch.get('inventory') != []:
        raise ValueError('公开站不能包含本地原始资料记录')
    if not isinstance(documents['verification'].get('records'), list):
        raise ValueError('网站来源依据格式不正确')
    check_public(dump(documents))


def _write_catalog(connection, catalog):
    for table in ('notice_taxonomy', 'facts', 'profiles', 'notices', 'activities', 'sources', 'taxonomy', 'catalog_metadata'):
        connection.execute('DELETE FROM ' + table)
    extra, layout = split_payload(catalog, (), ('entries', 'colleges', 'levels'))
    connection.execute('INSERT INTO catalog_metadata VALUES (1,?,?)', (extra, layout))
    for kind, key in [('college', 'colleges'), ('level', 'levels')]:
        connection.executemany('INSERT INTO taxonomy VALUES (?,?,?,?)',
                              [(kind, code, label, i) for i, (code, label) in enumerate(catalog[key].items())])
    for pos, entry in enumerate(catalog['entries']):
        extra, layout = split_payload(entry, ACTIVITY_FIELDS, ('versions',))
        connection.execute('INSERT INTO activities VALUES (?,?,?,?,?,?,?,?,?)',
                           tuple(entry.get(k) for k in ACTIVITY_FIELDS) + (pos, extra, layout))
        for index, v in enumerate(entry['versions']):
            nid, url = notice_id(v), v['source_url']
            sid = hashlib.sha256(url.encode()).hexdigest()
            connection.execute('INSERT INTO sources VALUES (?,?)', (sid, url))
            extra, layout = split_payload(v, NOTICE_FIELDS, ('source_url', 'colleges', 'levels', 'participation_facts', 'content_profile'))
            connection.execute('INSERT INTO notices VALUES (' + ','.join('?' for _ in range(14)) + ')',
                               (nid, entry['id'], sid) + tuple(v.get(k) for k in NOTICE_FIELDS) + (index, extra, layout,))
            for kind, key in [('college', 'colleges'), ('level', 'levels')]:
                connection.executemany('INSERT INTO notice_taxonomy VALUES (?,?,?,?)',
                                      [(nid, kind, code, i) for i, code in enumerate(v.get(key, []))])
            if v.get('content_profile') is not None:
                connection.execute('INSERT INTO profiles VALUES (?,?)', (nid, dump(v['content_profile'])))
            occurrences = {}
            for i, fact in enumerate(v.get('participation_facts', [])):
                extra, layout = split_payload(fact, FACT_FIELDS)
                identity = digest(fact)
                occurrence = occurrences.get(identity, 0)
                occurrences[identity] = occurrence + 1
                fid = nid + '-' + identity[:24] + '-' + str(occurrence)
                connection.execute('INSERT INTO facts VALUES (' + ','.join('?' for _ in range(11)) + ')',
                                   (fid, nid, i) + tuple(fact.get(k) for k in FACT_FIELDS) + (extra, layout))


def current_revision(connection):
    row = connection.execute('SELECT revision FROM current_state WHERE id=1').fetchone()
    return row['revision'] if row else None


def apply_catalog(catalog, batch_id, reason, path=DEFAULT_DB, expected_revision=None, allow_removal=False, origin='legacy-adapter', documents=None):
    validate_catalog(catalog)
    if not batch_id or not reason.strip():
        raise ValueError('批次编号和更新原因不能为空')
    connection = connect(path, initialize=True)
    try:
        connection.execute('BEGIN IMMEDIATE')
        current = current_revision(connection)
        if current != expected_revision:
            raise ValueError('数据库已变更，请重新检查基线后导入')
        existing = connection.execute('SELECT catalog_hash FROM revisions WHERE revision=?', (current,)).fetchone()
        if documents is None:
            documents = {r['name']: json.loads(r['payload']) for r in connection.execute('SELECT * FROM site_documents')}
        validate_documents(documents)
        bundle = {'catalog': catalog, 'documents': documents}
        catalog_hash = digest(bundle)
        old = read_catalog(connection) if current else None
        previous_documents = {r['name']: json.loads(r['payload']) for r in connection.execute('SELECT * FROM site_documents')}
        if current and (existing is None or existing['catalog_hash'] != digest({'catalog': old, 'documents': previous_documents})):
            raise ValueError('数据库原有内容与版本记录不一致，停止导入')
        if existing and existing['catalog_hash'] == catalog_hash:
            connection.rollback()
            return {'status': 'unchanged', 'revision': current}
        if connection.execute('SELECT 1 FROM revisions WHERE batch_id=?', (batch_id,)).fetchone():
            raise ValueError('批次编号已使用，不能覆盖历史')
        old_urls = {v['source_url'] for e in (old or {}).get('entries', []) for v in e['versions']}
        new_urls = {v['source_url'] for e in catalog['entries'] for v in e['versions']}
        if old_urls - new_urls and not allow_removal:
            raise ValueError('本批会移除历史公告；必须显式指定 --allow-removal 并说明原因')
        revision = 'rev-' + hashlib.sha256((batch_id + catalog_hash).encode()).hexdigest()[:24]
        timestamp = datetime.now(timezone.utc).isoformat()
        connection.execute('INSERT INTO revisions VALUES (?,?,?,?,?,?,?,?)',
                           (revision, batch_id, current, timestamp, reason, origin, catalog_hash,
                            gzip.compress(dump(bundle).encode('utf-8'), mtime=0)))
        old_entities = {('activity', e['id']): e for e in (old or {}).get('entries', [])}
        new_entities = {('activity', e['id']): e for e in catalog['entries']}
        for kind, key in sorted(old_entities.keys() | new_entities.keys()):
            before, after = old_entities.get((kind, key)), new_entities.get((kind, key))
            if before == after:
                continue
            action = 'add' if before is None else 'remove' if after is None else 'update'
            connection.execute('INSERT INTO changes VALUES (?,?,?,?,?,?)',
                               (revision, kind, key, action, digest(before) if before else None, digest(after) if after else None))
        _write_catalog(connection, catalog)
        connection.execute('DELETE FROM site_documents')
        connection.executemany('INSERT INTO site_documents VALUES (?,?)', [(k, dump(v)) for k, v in documents.items()])
        restored = read_catalog(connection)
        if restored != catalog:
            raise ValueError('数据库往返校验不一致，撤销本批导入')
        if connection.execute('PRAGMA foreign_key_check').fetchall():
            raise ValueError('数据库关联检查失败')
        connection.execute('INSERT OR REPLACE INTO current_state VALUES (1,?)', (revision,))
        connection.commit()
        return {'status': 'imported', 'revision': revision, 'activities': len(catalog['entries']), 'notices': len(new_urls)}
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def rollback(target, batch_id, reason, path=DEFAULT_DB, expected_revision=None):
    with connect(path) as connection:
        row = connection.execute('SELECT snapshot,catalog_hash FROM revisions WHERE revision=?', (target,)).fetchone()
        if row is None:
            raise ValueError('找不到目标版本')
        bundle = json.loads(gzip.decompress(row['snapshot']))
        if digest(bundle) != row['catalog_hash']:
            raise ValueError('回退快照校验失败')
    return apply_catalog(bundle['catalog'], batch_id, reason, path, expected_revision,
                         allow_removal=True, origin='rollback:' + target, documents=bundle['documents'])


def legacy_catalog():
    """Explicit compatibility adapter; never used by routine public builds."""
    try:
        from pipeline import load
        from share_demo import share_payload
        from catalog import build_catalog
        from build_verification import public_data
        from review_year import public_data as expansion_data
    except ModuleNotFoundError as exc:
        raise ValueError('旧资料接入需完整本地维护环境；公开源码可执行迁移、检查、构建和恢复') from exc
    catalog = build_catalog(share_payload(load(ROOT / 'work/demo-batch.json')), public_data(), expansion_data())
    catalog['entries'] = [e for e in catalog['entries'] if e['kind'] in {'official', 'notice'}]
    for e in catalog['entries']:
        e['material_ids'] = []
    validate_catalog(catalog)
    return catalog


def preserve_editorial(catalog, current, field_ownership):
    """Keep user-edited values from the DB; sidecar records field names only."""
    allowed = {'title', 'category', 'category_label', 'editorial_note', 'featured', 'spotlight'}
    previous = {entry['id']: entry for entry in current['entries']}
    for entry in catalog['entries']:
        if entry['id'] not in previous:
            continue
        for key in set(field_ownership.get(entry['id'], [])) & allowed:
            if key in previous[entry['id']]:
                entry[key] = previous[entry['id']][key]
            else:
                entry.pop(key, None)
    return catalog
