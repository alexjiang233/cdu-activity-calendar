"""One explicit, reversible editorial view over imported notice content."""
FIELDS = (
    ('event_time', '具体时段', 'schedule'),
    ('location', '活动地点', 'location'),
    ('registration', '怎么报名', 'registration'),
    ('conditions', '报名条件', 'conditions'),
    ('materials', '需要准备什么', 'materials'),
    ('benefits', '奖励或收获', 'benefits'),
    ('fees', '费用', 'fees'),
    ('contact', '咨询方式', 'contact'),
    ('notes', '其他必要说明', 'other'),
)


def curated(notice):
    value = (notice.extras or {}).get('curated_details')
    return value if isinstance(value, dict) and value.get('enabled') is True else None


def sections(notice):
    value = curated(notice)
    if value is None:
        return None
    fields = value.get('fields') or {}
    result = []
    if notice.audience:
        result.append({'kind': 'audience', 'title': '参与对象',
                       'items': [{'text': notice.audience}]})
    for key, title, kind in FIELDS:
        text = fields.get(key, '')
        if not isinstance(text, str):
            continue
        items = [{'text': line.strip()} for line in text.splitlines() if line.strip()]
        if items:
            result.append({'kind': kind, 'title': title, 'items': items})
    return result


def seed_fields(notice):
    """Only prefill explicitly classified facts; never guess a venue from arbitrary prose."""
    saved = (notice.extras or {}).get('curated_details') or {}
    if isinstance(saved, dict) and 'fields' in saved:
        return saved['fields'] if isinstance(saved['fields'], dict) else {}
    profile = getattr(notice, 'profile', None)
    result = {}
    for key, _, kind in FIELDS:
        texts = [f.value.strip() for f in notice.facts.all()
                 if f.kind == kind and f.value.strip()]
        if not texts and profile:
            texts = [item.get('text', '').strip()
                     for section in (profile.payload or {}).get('sections', [])
                     if section.get('kind') == kind for item in section.get('items', [])
                     if isinstance(item, dict) and item.get('text', '').strip()]
        result[key] = '\n'.join(dict.fromkeys(texts))
    return result
