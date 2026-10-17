"""Single local entry point for migrations, validated intake, builds and recovery."""
import argparse
import json
import sqlite3
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

import catalog_store as store


class EmbeddedData(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.key = None
        self.blocks = {}

    def handle_starttag(self, tag, attrs):
        key = dict(attrs).get('id')
        if tag == 'script' and key in {'batch', 'catalog-data', 'verification-data'}:
            if key in self.blocks:
                raise ValueError('网页包含重复的数据块')
            self.key = key
            self.blocks[key] = ''

    def handle_data(self, data):
        if self.key:
            self.blocks[self.key] += data

    def handle_endtag(self, tag):
        if tag == 'script':
            self.key = None


def read_release(path):
    parser = EmbeddedData()
    parser.feed(Path(path).read_text(encoding='utf-8-sig'))
    catalog = json.loads(parser.blocks['catalog-data'])
    documents = {'batch': json.loads(parser.blocks['batch']),
                 'verification': json.loads(parser.blocks['verification-data'])}
    store.validate_catalog(catalog)
    store.validate_documents(documents)
    return catalog, documents


def get_revision(db):
    if not Path(db).exists():
        return None
    with store.connect(db) as connection:
        return store.current_revision(connection)


def health(db):
    catalog, _, _ = store.load_site_data(db)
    with store.connect(db) as connection:
        integrity = connection.execute('PRAGMA integrity_check').fetchone()[0]
        foreign = connection.execute('PRAGMA foreign_key_check').fetchall()
        if integrity != 'ok' or foreign:
            raise ValueError('数据库完整性检查未通过')
        revision = store.current_revision(connection)
        saved = connection.execute('SELECT catalog_hash FROM revisions WHERE revision=?', (revision,)).fetchone()
        documents = {r['name']: json.loads(r['payload']) for r in connection.execute('SELECT * FROM site_documents')}
        if not saved or saved['catalog_hash'] != store.digest({'catalog': catalog, 'documents': documents}):
            raise ValueError('数据库被绕过导入入口修改，内容与版本记录不一致')
        counts = {table: connection.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0]
                  for table in ('activities', 'notices', 'sources', 'facts', 'profiles', 'revisions')}
        return {'status': 'passed', 'revision': revision, **counts}


def backup(db, target):
    target = Path(target)
    if target.exists() or target.resolve() == Path(db).resolve():
        raise ValueError('备份目标已存在，拒绝覆盖')
    target.parent.mkdir(parents=True, exist_ok=True)
    with store.connect(db) as source, sqlite3.connect(target, factory=store.Connection) as dest:
        source.backup(dest)
    return {'status': 'backed_up', 'path': str(target)}


def main(argv=None):
    parser = argparse.ArgumentParser(description='校园活动资料统一维护入口')
    parser.add_argument('--db', type=Path, default=store.DEFAULT_DB)
    commands = parser.add_subparsers(dest='command', required=True)
    migrate = commands.add_parser('migrate', help='仅首次：从已验收的公开网页无损迁移')
    migrate.add_argument('--release', type=Path, default=store.ROOT / 'public/index.html')
    for command in (migrate, commands.add_parser('sync-legacy', help='经旧证据校验适配器接入资料更新')):
        command.add_argument('--batch-id', required=True)
        command.add_argument('--reason', required=True)
        command.add_argument('--expected-revision')
        command.add_argument('--allow-removal', action='store_true')
    commands.add_parser('check', help='检查结构、隐私、关联、内容哈希和完整性')
    export = commands.add_parser('export', help='导出兼容的公开数据包')
    export.add_argument('--output', type=Path, required=True)
    commands.add_parser('history', help='查看导入与回退历史')
    changes = commands.add_parser('changes', help='查看某次更新的逐活动变更记录')
    changes.add_argument('--revision', required=True)
    rollback = commands.add_parser('rollback', help='回到某个资料版本，保留全部历史')
    rollback.add_argument('--target', required=True)
    rollback.add_argument('--expected-revision', required=True)
    rollback.add_argument('--batch-id', required=True)
    rollback.add_argument('--reason', required=True)
    build = commands.add_parser('build', help='只从数据库构建网页，不重新处理旧批次')
    build.add_argument('--output', type=Path, default=store.ROOT / 'public/index.html')
    backup_cmd = commands.add_parser('backup', help='创建一致的数据库备份')
    backup_cmd.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command in {'migrate', 'sync-legacy'}:
        current = get_revision(args.db)
        if args.command == 'migrate':
            if current:
                raise ValueError('已经迁移过；后续更新使用 sync-legacy，不重新灌入网页')
            catalog, documents = read_release(args.release)
        else:
            if not current:
                raise ValueError('先执行首次 migrate')
            if not args.expected_revision:
                raise ValueError('更新必须指定 --expected-revision，防止覆盖其他更新')
            if current != args.expected_revision:
                raise ValueError('当前版本已改变，请先 check')
            health(args.db)
            catalog = store.legacy_catalog()
            from build_verification import public_data
            documents = {'batch': {'schema_version': 'official-public-1', 'records': [], 'inventory': []},
                         'verification': public_data()}
        if current and current != args.expected_revision:
            raise ValueError('当前版本已改变，请先 check')
        if current:
            with store.connect(args.db) as c:
                saved = c.execute('SELECT catalog_hash FROM revisions WHERE revision=?', (current,)).fetchone()[0]
            if saved != store.digest({'catalog': catalog, 'documents': documents}):
                stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
                backup(args.db, args.db.parent / 'backups' / (stamp + '.sqlite3'))
        result = store.apply_catalog(catalog, args.batch_id, args.reason, args.db,
                                     args.expected_revision, args.allow_removal,
                                     origin='baseline-migration' if args.command == 'migrate' else 'validated-legacy-adapter',
                                     documents=documents)
    elif args.command == 'check':
        result = health(args.db)
    elif args.command == 'history':
        with store.connect(args.db) as connection:
            result = [dict(r) for r in connection.execute('SELECT revision,batch_id,parent_revision,created_at,reason,origin FROM revisions ORDER BY rowid')]
    elif args.command == 'changes':
        with store.connect(args.db) as connection:
            result = [dict(r) for r in connection.execute('SELECT entity_kind,entity_id,action,before_hash,after_hash FROM changes WHERE revision=?', (args.revision,))]
    elif args.command == 'rollback':
        health(args.db)
        result = store.rollback(args.target, args.batch_id, args.reason, args.db, args.expected_revision)
    elif args.command == 'backup':
        health(args.db)
        result = backup(args.db, args.output)
    elif args.command == 'export':
        health(args.db)
        catalog, batch, proof = store.load_site_data(args.db)
        args.output.mkdir(parents=True, exist_ok=True)
        for name, value in [('catalog.json', catalog), ('batch.json', batch), ('verification.json', proof)]:
            (args.output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
        result = {'status': 'exported', 'path': str(args.output), 'revision': get_revision(args.db)}
    else:
        health(args.db)
        import share_demo
        page = share_demo.share_html(None, public_only=True, database=args.db)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        temp = args.output.with_name(args.output.name + '.tmp')
        temp.write_text(page, encoding='utf-8')
        temp.replace(args.output)
        result = {'status': 'built', 'path': str(args.output), 'revision': get_revision(args.db)}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, sqlite3.Error, OSError) as exc:
        raise SystemExit('停止操作：' + str(exc)) from exc
