"""Create an explicitly requested shareable demo, excluding local review evidence."""
import copy
import json
import re
import zipfile
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1]


def public_data():
    from build_verification import public_data as legacy_proof
    return legacy_proof()


def build_catalog(*args):
    from catalog import build_catalog as legacy_catalog
    return legacy_catalog(*args)


def expansion_data():
    from review_year import public_data as legacy_expansion
    return legacy_expansion()


def share_payload(batch):
    """Allowlist presentation fields; never serialize the full review batch."""
    records = []
    for i, item in enumerate(batch['records'], 1):
        records.append({
            'id': item['id'], 'title': item['title'], 'category': item['category'],
            'record_kind': item.get('record_kind', 'opportunity'),
            'tags': list(item['tags']), 'summary': item['summary'],
            'source': {'path': Path(item['source']['path']).name,
                       'publisher': item['source']['publisher'],
                       'published_on': item['source']['published_on'], 'url': None},
            'facts': copy.deepcopy(item['facts']),
            'editorial': copy.deepcopy(item['editorial']),
            'related_record_ids': list(item['related_record_ids']),
            'evidence': [],
        })
    return {'schema_version': 'demo-share-1.1', 'batch_id': 'share-all-documents-001',
            'records': records, 'inventory': []}


def share_html(batch,public_only=False,database=None):
    if public_only:
        from catalog_store import load_site_data
        catalog,data,proof=load_site_data(database)
    else:
        data=share_payload(batch)
        proof=public_data()
        catalog=build_catalog(data,proof,expansion_data())
    template=(PROJECT/'scripts/catalog-template.html').read_text(encoding='utf-8')
    def encoded(value):return json.dumps(value,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    years=sorted({str(v['year']) for e in catalog['entries'] for v in e.get('versions',[]) if v.get('year')},reverse=True)
    year_options='<option value="">全部年份</option>'+''.join(f'<option value="{year}">{year} 年</option>' for year in years)+'<option value="unknown">年份待确认</option>'
    template=re.sub(r'(<select id="year" name="year">).*?(</select>)',lambda m:m.group(1)+year_options+m.group(2),template,count=1,flags=re.S)
    if public_only:
        # The public site carries only official-source records. Keep private
        # local material metadata out of embedded JSON, even when collapsed.
        data={'schema_version':'official-public-1','records':[],'inventory':[]}
        catalog['entries']=[e for e in catalog['entries'] if e['kind'] in {'official','notice'}]
        for entry in catalog['entries']:entry['material_ids']=[]
        template=template.replace('现有 15 份本地 Word 材料均保留摘要入口；同一活动的多个文件会合并展示，并保留版本差异。','公开页面只展示可追溯到官网的条目，本地未公开材料不在页面展示。')
    template=template.replace('<!--__CALENDAR__-->',(PROJECT/'scripts/calendar.html').read_text(encoding='utf-8'))
    template=template.replace('<!--__HOME__-->',(PROJECT/'scripts/site-home.html').read_text(encoding='utf-8'))
    template=template.replace('<!--__CONTACT__-->',(PROJECT/'scripts/site-contact.html').read_text(encoding='utf-8'))
    result=template.replace('/*__DATA__*/',encoded(data)).replace('/*__CATALOG__*/',encoded(catalog)).replace('/*__VERIFICATION__*/',encoded(proof))
    for marker,path in [('/*__DISCOVERY_STYLE__*/','discovery.css'),('/*__CALENDAR_CORE__*/','calendar-core.js'),('/*__CALENDAR_UI__*/','calendar-ui.js'),('/*__CALENDAR_STYLE__*/','calendar.css'),('/*__CORE__*/','catalog-core.js'),('/*__UI__*/','catalog-ui.js'),('/*__MOTION__*/','catalog-motion.css'),('/*__PAGES__*/','site-pages.js'),('/*__SITE_STYLE__*/','site-home.css'),('/*__SECTION_STYLE__*/','section-motion.css'),('/*__PROFILE_STYLE__*/','activity-profile.css'),('/*__THEME_STYLE__*/','red-theme.css'),('/*__DISPLAY_STYLE__*/','display-motion.css'),('/*__FONTS__*/','display-fonts.css')]:
        result=result.replace(marker,(PROJECT/'scripts'/path).read_text(encoding='utf-8'))
    # One gate scans both embedded data and rendered page, including preview mode.
    from public_guard import check_public
    check_public(result)
    return result


def main():
    from manage_content import health
    from catalog_store import DEFAULT_DB
    health(DEFAULT_DB)
    page = share_html(None,public_only=True)
    public = PROJECT / 'public'
    share = PROJECT / 'share'
    public.mkdir(exist_ok=True)
    share.mkdir(exist_ok=True)
    (public / 'index.html').write_text(page, encoding='utf-8')
    (public / '.nojekyll').write_text('', encoding='utf-8')
    note = ('校园活动 Demo\n\n解压后双击 index.html 即可查看。\n'
            '这是产品功能演示，不是官方通知或报名入口。资料尚未完整核实，请勿据此报名。\n'
            '原始 Word 文件、私人联系信息、本地路径及内部审核证据均未打包。\n')
    (share / '使用说明.txt').write_text(note, encoding='utf-8')
    with zipfile.ZipFile(share / 'cdu-activity-calendar-demo.zip', 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('index.html', page)
        z.writestr('使用说明.txt', note)
    print('Public website and offline package built from SQLite; private sources excluded.')


if __name__ == '__main__':
    main()
