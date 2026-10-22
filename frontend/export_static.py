"""把当前 Django 公开投影导出为可独立托管的静态站点。

用法（在项目根目录）：
    .venv-backend/Scripts/python.exe frontend/export_static.py

设计要点：
- 先用 SQLite backup API 做一致性副本，再从副本读取；不写正式库。
- 活动列表/筛选规则复用 catalog.services，不另起一套分类口径。
- 首屏只取 meta/taxonomies/home；活动索引、详情、指南正文、日历均按需读取。
- 所有路径相对 site 根目录，支持普通静态服务器和子路径部署。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import quote
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
BACKEND = PROJECT / 'backend'
SRC = HERE / 'src'
DEPLOY = PROJECT / 'deploy' / 'edgeone-drop'
SITE = DEPLOY / 'site'
DATA = SITE / 'data'
EXPORT_DATE = datetime.now(ZoneInfo('Asia/Shanghai')).strftime('%Y-%m-%d')
WORK = PROJECT / 'work' / f'edgeone-static-export-{EXPORT_DATE}'
SAFE_ID = re.compile(r'^[A-Za-z0-9._-]+$')


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def safe_key(value: str, kind: str) -> str:
    text = str(value)
    if not SAFE_ID.match(text):
        raise SystemExit(f'{kind} 含不适合作为静态文件名的字符：{text!r}')
    return text


def write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, separators=(',', ':')),
        encoding='utf-8', newline='\n',
    )


def snapshot_database(source: Path, destination: Path) -> dict:
    """使用 SQLite backup API 复制一致性快照；不直接复制主文件。"""
    if not source.exists():
        raise SystemExit(f'找不到数据库：{source}')
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    source_connection = sqlite3.connect(str(source), timeout=30)
    try:
        source_connection.execute('PRAGMA query_only=ON')
        destination_connection = sqlite3.connect(str(destination))
        try:
            source_connection.backup(destination_connection)
            destination_connection.commit()
            check = destination_connection.execute('PRAGMA quick_check').fetchone()
        finally:
            destination_connection.close()
    finally:
        source_connection.close()
    if not check or check[0] != 'ok':
        raise SystemExit(f'快照校验失败：{check!r}')
    return {
        'source_database': str(source.resolve()),
        'snapshot_path': str(destination.resolve()),
        'snapshot_bytes': destination.stat().st_size,
        'snapshot_sha256': sha256_file(destination),
        'snapshot_at': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds'),
        'quick_check': check[0],
    }


def setup_django(snapshot: Path) -> None:
    for key in ('POSTGRES_DB', 'POSTGRES_USER', 'POSTGRES_PASSWORD', 'POSTGRES_HOST', 'POSTGRES_PORT'):
        os.environ.pop(key, None)
    os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
    os.environ['DJANGO_DB'] = str(snapshot)
    os.environ['DEBUG'] = '1'
    sys.path.insert(0, str(BACKEND))
    import django
    django.setup()


def build_selection_overrides(services, notices: dict) -> dict:
    """记录少数“同日期并列”卡片在后端实际选中的通知。

    版本数组仍用稳定顺序；只有后端选择与稳定顺序不同、且筛选条件完全匹配
    单维条件时才使用覆盖，避免静态页默认展开另一份同日期公告。
    """
    from catalog.models import Taxonomy

    levels = list(Taxonomy.objects.filter(kind='level').order_by('code').values_list('code', flat=True))
    colleges = list(Taxonomy.objects.filter(kind='college').order_by('code').values_list('code', flat=True))
    years = [str(year) for year in sorted({item['year'] for item in notices.values() if item['year']})]
    years.append('unknown')
    months = [str(month) for month in range(1, 13)] + ['unknown']

    specs = []
    for code in levels:
        specs.append((f'level:{code}', services.Filters(level=code, page_size=48)))
    for code in colleges:
        specs.append((f'college:{code}', services.Filters(college=code, page_size=48)))
    for year in years:
        specs.append((f'year:{year}', services.Filters(year=year, page_size=48)))
        for month in months:
            specs.append((f'year:{year}|month:{month}', services.Filters(
                year=year, month=month, month_basis='seasonal', page_size=48)))
    for month in months:
        specs.append((f'month:{month}', services.Filters(
            month=month, month_basis='seasonal', page_size=48)))

    overrides: dict[str, dict[str, str]] = {}
    for key, filters in specs:
        scope = services._sql_scope(filters)
        if scope is None:
            rows = services.load_cards()
        else:
            rows = services.load_cards(activity_ids=scope[0], group_ids=scope[1])
        changed = {}
        for row in rows:
            if not services.row_matches(row, filters):
                continue
            backend = services.select_version(row.notices, filters)
            if backend is None:
                continue
            candidates = [notice for notice in row.notices if services._version_ok(notice, filters)]
            candidates.sort(key=lambda notice: notices.get(notice.id, {}).get('order', 0))
            if not candidates:
                continue
            stable = candidates[0]
            stable_key = (stable.year or 0, stable.published.isoformat() if stable.published else '')
            for notice in candidates[1:]:
                candidate_key = (notice.year or 0, notice.published.isoformat() if notice.published else '')
                if candidate_key > stable_key:
                    stable = notice
                    stable_key = candidate_key
            if stable.id != backend.id:
                changed[row.card.id] = backend.id
        if changed:
            overrides[key] = changed
    return overrides


def build_catalog_export() -> tuple[dict, dict]:
    from catalog import services
    from catalog.models import Activity, ActivityGroup, Notice

    rows = list(services.load_cards())
    cards: list[dict] = []
    notices: dict[str, dict] = {}
    card_ids: set[str] = set()
    activity_cards: dict[str, Activity] = {}
    group_cards: list[ActivityGroup] = []

    for row in rows:
        card = row.card
        card_id = safe_key(card.id, '卡片 ID')
        card_ids.add(card_id)
        entry = services.serialize_entry(card, row.notices)
        notice_ids: list[str] = []
        for notice in row.notices:
            notice_id = safe_key(notice.id, '通知 ID')
            notice_ids.append(notice_id)
            colleges = [t.code for t in notice.taxonomies.all() if t.kind == 'college']
            levels = [t.code for t in notice.taxonomies.all() if t.kind == 'level']
            meta = {
                'version': services.serialize_notice(notice),
                'activity_id': notice.activity_id,
                'display_activity_id': notice.display_activity_id,
                'group_ids': sorted(notice.groups.filter(visibility='public').values_list('id', flat=True)),
                'position': notice.position,
                'year': notice.year,
                'colleges': colleges,
                'levels': levels,
                'seasonal_months': sorted(services.decode_months(notice.seasonal_months)),
                'search': notice.search_text or '',
                'facts_preview': [services._fact_payload(fact) for fact in list(notice.facts.all())[:12]],
            }
            existing = notices.get(notice_id)
            if existing is not None:
                for key in ('activity_id', 'display_activity_id', 'group_ids', 'year', 'colleges',
                            'levels', 'seasonal_months', 'search', 'version'):
                    if existing[key] != meta[key]:
                        raise SystemExit(f'同一通知在不同卡片上的元数据不一致：{notice_id} / {key}')
            else:
                notices[notice_id] = meta
        cards.append({
            'card_id': card_id,
            'kind': 'group' if card.is_group else 'activity',
            'entry': entry,
            'activity_search': card.activity.search_text or '',
            'notice_ids': notice_ids,
        })
        if card.is_group:
            group_cards.append(card.group)
        else:
            activity_cards[card.activity.id] = card.activity

    def notice_order_key(notice: Notice):
        return (
            notice.year or 0,
            notice.published.isoformat() if notice.published else '',
            -notice.position,
        )
    # 先用 queryset 的默认顺序（-year,-published,position），再做稳定排序，
    # 这样同年同发布日同 position 的通知在静态侧也与 services._notice_order 保持一致。
    ordered_notices = list(services._notice_qs())
    ordered_notices.sort(key=notice_order_key, reverse=True)
    for order, notice in enumerate(ordered_notices):
        if notice.id in notices:
            notices[notice.id]['order'] = order

    scope_activities = []
    for activity in activity_cards.values():
        own_ids = list(
            Notice.objects.filter(activity_id=activity.id, visibility='public')
            .order_by('id').values_list('id', flat=True)
        )
        missing = [nid for nid in own_ids if nid not in notices]
        if missing:
            # 当前公开活动没有“未落到任何卡片”的通知；出现时要先核对公开投影，
            # 不能把未展示的通知搜索文本私自发布。
            raise SystemExit(f'公开活动 {activity.id} 存在未进入卡片投影的通知：{missing[:5]}')
        scope_activities.append({
            'id': activity.id,
            'category': activity.category.code if activity.category_id else '',
            'search': activity.search_text or '',
            'notice_ids': own_ids,
        })

    scope_groups = []
    for group in ActivityGroup.objects.filter(visibility='public').order_by('id'):
        group_ids = list(
            group.notices.filter(visibility='public').order_by('id').values_list('id', flat=True)
        )
        missing = [nid for nid in group_ids if nid not in notices]
        if missing:
            raise SystemExit(f'公开分组卡 {group.id} 存在未进入卡片投影的通知：{missing[:5]}')
        scope_groups.append({'id': group.id, 'title': group.title, 'notice_ids': group_ids})

    plain_chunk, plain_total, _, _ = services._page_card_ids(
        services.Filters(page=1, page_size=1_000_000)
    )
    plain_items = []
    for kind, card_id, latest, title in plain_chunk:
        plain_items.append({
            'kind': kind,
            'id': card_id,
            'latest': latest.isoformat() if latest else None,
            'title': title,
            'has_card': card_id in card_ids,
        })

    selection_overrides = build_selection_overrides(services, notices)
    catalog = {
        'schema': 1,
        'counts': services.public_counts(),
        'cards': cards,
        'notices': notices,
        'scope': {'activities': scope_activities, 'groups': scope_groups},
        'plain_items': plain_items,
        'selection_overrides': selection_overrides,
    }
    detail_sources = {
        'rows': rows,
        'card_ids': card_ids,
    }
    return catalog, detail_sources


def export_details(detail_sources: dict) -> int:
    from catalog.api import public as public_api
    from catalog import services

    rows = detail_sources['rows']
    written = 0
    for row in rows:
        card_id = safe_key(row.card.id, '卡片 ID')
        bundle = {'default': None, 'notices': {}}
        default = services.activity_detail(row.card.id)
        if default is None:
            raise SystemExit(f'卡片默认详情为空：{row.card.id}')
        bundle['default'] = public_api._clean(default)
        written += 1
        for notice in row.notices:
            notice_id = safe_key(notice.id, '通知 ID')
            payload = services.activity_detail(row.card.id, notice.id)
            if payload is None:
                raise SystemExit(f'通知详情为空：{row.card.id} / {notice.id}')
            bundle['notices'][notice_id] = public_api._clean(payload)
            written += 1
        write_json(DATA / 'details' / f'{card_id}.json', bundle)
    return written


def export_public_payloads(exported_at: str) -> dict:
    from catalog.api import public as public_api
    from catalog import services

    meta = public_api._clean(services.meta_payload())
    meta['generated_at'] = exported_at
    home = public_api._clean(services.home_payload())
    taxonomies = services.taxonomy_payload()
    guides = services.guide_list()
    services_rows = services.service_list()

    write_json(DATA / 'meta.json', meta)
    write_json(DATA / 'home.json', home)
    write_json(DATA / 'taxonomies.json', taxonomies)
    write_json(DATA / 'guides.json', {'count': len(guides), 'results': guides})
    write_json(DATA / 'services.json', {'count': len(services_rows), 'results': services_rows})

    guide_count = 0
    for item in guides:
        payload = services.guide_detail(item['id'])
        if payload is None:
            raise SystemExit(f'指南详情为空：{item["id"]}')
        safe = safe_key(item['id'], '指南 ID')
        write_json(DATA / 'guides' / f'{safe}.json', payload)
        guide_count += 1

    annual_counts = {'mode': 'annual_counts', 'counts': services.annual_counts()}
    write_json(DATA / 'calendar' / 'annual-all.json', annual_counts)
    for month in range(1, 13):
        write_json(
            DATA / 'calendar' / f'annual-{month:02d}.json',
            public_api._clean(services.calendar_annual(month)),
        )

    return {
        'meta': meta,
        'home': home,
        'taxonomies': taxonomies,
        'guides': guides,
        'services': services_rows,
        'guide_count': guide_count,
    }


def assemble_site(exported_at: str, snapshot_info: dict) -> dict:
    sys.path.insert(0, str(HERE))
    import build as frontend_build

    template = (SRC / 'index.template.html').read_text(encoding='utf-8')
    css = (SRC / 'styles' / 'app.css').read_text(encoding='utf-8')
    for name in frontend_build.SCRIPTS:
        if not (SRC / 'scripts' / name).exists():
            raise SystemExit(f'缺少脚本：{name}')
    adapter_template = (SRC / 'scripts' / 'api-static.js').read_text(encoding='utf-8')
    if '__CDU_BUILD_REVISION__' not in adapter_template:
        raise SystemExit('静态适配器缺少版本占位符')

    data_files = sorted(path for path in DATA.rglob('*.json'))
    asset_sources = [
        SRC / 'index.template.html',
        SRC / 'styles' / 'app.css',
        SRC / 'scripts' / 'api-static.js',
        *[SRC / 'scripts' / name for name in frontend_build.SCRIPTS],
    ]
    seed = {
        'meta_revision': json.loads((DATA / 'meta.json').read_text(encoding='utf-8')).get('revision'),
        'data': [{'path': str(path.relative_to(SITE)), 'sha256': sha256_file(path)} for path in data_files],
        'assets': [{'path': str(path.relative_to(SRC)), 'sha256': sha256_file(path)} for path in asset_sources],
        'build_py': sha256_file(HERE / 'build.py'),
    }
    build_id = 'rev-static-' + datetime.strptime(EXPORT_DATE, '%Y-%m-%d').strftime('%Y%m%d') + '-' + \
        hashlib.sha256(json.dumps(seed, sort_keys=True, ensure_ascii=False).encode('utf-8')).hexdigest()[:10]

    assets = SITE / 'assets'
    assets.mkdir(parents=True, exist_ok=True)
    (assets / 'app.css').write_text(css + frontend_build.BOOT_STYLE, encoding='utf-8', newline='\n')
    for name in frontend_build.SCRIPTS:
        shutil.copyfile(SRC / 'scripts' / name, assets / name)
    adapter = adapter_template.replace('__CDU_BUILD_REVISION__', build_id)
    (assets / 'api.js').write_text(adapter, encoding='utf-8', newline='\n')

    boot = frontend_build.BOOT_SCRIPT.replace(
        'SCRIPTS_PLACEHOLDER', json.dumps([f'assets/{name}' for name in frontend_build.SCRIPTS])
    )
    boot = boot.replace(
        '<script src="assets/api.js"></script>',
        f'<script src="assets/api.js?v={build_id}"></script>',
    )
    page = template.replace(
        '</head>',
        f' <meta name="cdu-static-revision" content="{build_id}">'
        f'<style>{frontend_build.BOOT_STYLE}</style><link rel="stylesheet" href="assets/app.css?v={build_id}"></head>',
    )
    page = re.sub(
        r'(<body[^>]*>)',
        lambda m:m.group(1)+frontend_build.BOOT_MARKUP,
        page, count=1,
    )
    page = page.replace('</body>', boot + '</body>')
    if 'id="catalog-data"' in page or 'id="campus-life-data"' in page:
        raise SystemExit('模板里仍然内嵌数据块，已停止构建')
    (SITE / 'index.html').write_text(page, encoding='utf-8', newline='\n')

    write_json(SITE / 'data' / 'build.json', {
        'build_revision': build_id,
        'exported_at': exported_at,
        'meta_revision': seed['meta_revision'],
        'snapshot_sha256': snapshot_info['snapshot_sha256'],
    })
    return {'build_revision': build_id, 'seed': seed}


def package_site(snapshot_info: dict, build_id: str) -> dict:
    files = sorted(path for path in SITE.rglob('*') if path.is_file())
    if len(files) > 1000:
        raise SystemExit(f'上传资源文件数 {len(files)} 超过 EdgeOne Drop 1000 个限制')
    if any(path.stat().st_size > 25_000_000 for path in files):
        raise SystemExit('上传资源存在超过 25MB 的文件，停止打包')
    records = []
    for path in files:
        records.append({
            'path': str(path.relative_to(SITE)).replace('\\', '/'),
            'bytes': path.stat().st_size,
            'sha256': sha256_file(path),
        })
    largest = max(records, key=lambda item: item['bytes'])
    site_bytes = sum(item['bytes'] for item in records)
    zip_path = DEPLOY / 'site.zip'
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            archive.write(path, str(path.relative_to(SITE)).replace('\\', '/'))
    first_screen = ['data/meta.json', 'data/taxonomies.json', 'data/home.json']
    first_screen_bytes = sum(
        (SITE / item).stat().st_size for item in first_screen if (SITE / item).exists()
    )
    return {
        'site_bytes': site_bytes,
        'site_files': len(records),
        'largest_file': largest,
        'zip_bytes': zip_path.stat().st_size,
        'zip_sha256': sha256_file(zip_path),
        'zip_path': str(zip_path.resolve()),
        'site_path': str(SITE.resolve()),
        'first_screen': {
            'files': first_screen,
            'bytes': first_screen_bytes,
        },
        'files': records,
    }


def write_manifest(exported_at: str, snapshot_info: dict, package: dict, build_id: str,
                   counts: dict) -> None:
    manifest = {
        'generated_at': exported_at,
        'build_revision': build_id,
        'source': snapshot_info,
        'counts': counts,
        'site': {
            'path': package['site_path'],
            'bytes': package['site_bytes'],
            'files': package['site_files'],
            'largest_file': package['largest_file'],
            'first_screen': package['first_screen'],
        },
        'zip': {
            'path': package['zip_path'],
            'bytes': package['zip_bytes'],
            'sha256': package['zip_sha256'],
        },
        'files': package['files'],
    }
    write_json(DEPLOY / 'manifest.json', manifest)


def main() -> None:
    parser = argparse.ArgumentParser(description='导出 EdgeOne 静态站点')
    parser.add_argument('--db', help='正式数据库路径；默认 DJANGO_DB 或 backend/db.sqlite3')
    parser.add_argument('--snapshot', help='一致性快照输出路径')
    args = parser.parse_args()

    source = Path(args.db or os.environ.get('DJANGO_DB') or (BACKEND / 'db.sqlite3')).resolve()
    snapshot = Path(args.snapshot).resolve() if args.snapshot else (WORK / 'snapshot.sqlite3')
    WORK.mkdir(parents=True, exist_ok=True)
    snapshot_info = snapshot_database(source, snapshot)

    setup_django(snapshot)
    from catalog import services
    counts = services.public_counts()
    exported_at = datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')

    DEPLOY.mkdir(parents=True, exist_ok=True)
    if SITE.exists():
        shutil.rmtree(SITE)
    DATA.mkdir(parents=True, exist_ok=True)

    catalog, detail_sources = build_catalog_export()
    write_json(DATA / 'catalog.json', catalog)
    detail_count = export_details(detail_sources)
    payloads = export_public_payloads(exported_at)
    assembled = assemble_site(exported_at, snapshot_info)
    package = package_site(snapshot_info, assembled['build_revision'])
    write_manifest(exported_at, snapshot_info, package, assembled['build_revision'], counts)

    summary = {
        'exported_at': exported_at,
        'build_revision': assembled['build_revision'],
        'counts': counts,
        'cards_in_export': len(catalog['cards']),
        'notices_in_export': len(catalog['notices']),
        'details_written': detail_count,
        'guides': payloads['guide_count'],
        'site_bytes': package['site_bytes'],
        'largest_file': package['largest_file'],
        'first_screen_bytes': package['first_screen']['bytes'],
        'zip': package['zip_path'],
        'zip_sha256': package['zip_sha256'],
        'snapshot': snapshot_info,
    }
    write_json(WORK / 'export-summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
