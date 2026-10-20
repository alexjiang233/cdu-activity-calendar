"""草稿与发布：保存草稿不碰公开内容，发布时才写正式字段并生成修订。

后台的「保存草稿」按钮走 save_draft；「发布」在草稿列表里执行。
预览只读，直接按草稿内容临时拼出条目，不写库。
"""
from __future__ import annotations

from django.utils import timezone
from django.db import transaction

from . import audit, services
from .models import Activity, CampusService, DraftChange, Guide, Notice

KIND_MODEL = {'activity': Activity, 'notice': Notice, 'guide': Guide, 'service': CampusService}


@transaction.atomic
def save_draft(kind: str, entity_id: str, payload: dict, *, note: str = '', author=None) -> DraftChange:
    model = KIND_MODEL[kind]
    entity = model.objects.select_for_update().get(pk=entity_id)
    allowed = audit.snapshot(kind, entity)
    clean = {key: value for key, value in payload.items() if key in allowed and key != 'id'}
    if hasattr(entity, 'draft'):
        entity.draft = clean
        entity.save(update_fields=['draft'])
    clean['_base_hash'] = audit.content_hash(allowed)
    return DraftChange.objects.create(entity_kind=kind, entity_id=entity_id, payload=clean,
                                      note=note, author=author, status='draft')


@transaction.atomic
def publish(draft: DraftChange, *, actor=None) -> DraftChange:
    draft = DraftChange.objects.select_for_update().get(pk=draft.pk)
    if draft.status != 'draft':
        raise ValueError('只有草稿状态的记录可以发布')
    model = KIND_MODEL[draft.entity_kind]
    entity = model.objects.select_for_update().get(pk=draft.entity_id)
    baseline = draft.payload.get('_base_hash')
    if baseline and baseline != audit.content_hash(audit.snapshot(draft.entity_kind, entity)):
        raise ValueError('公开内容在草稿保存后发生了变化，请重新核对后再发布。')
    revision = audit.apply_updates(draft.entity_kind, entity, draft.payload,
                                   reason=draft.note or '发布草稿', origin='draft',
                                   actor=actor or draft.author, note=draft.note)
    if hasattr(entity, 'draft'):
        entity.draft = None
        entity.save(update_fields=['draft'])
    draft.status = 'published'
    draft.published_at = timezone.now()
    draft.revision = revision
    draft.save(update_fields=['status', 'published_at', 'revision'])
    return draft


def discard(draft: DraftChange) -> DraftChange:
    draft.status = 'discarded'
    draft.save(update_fields=['status'])
    return draft


def preview(draft: DraftChange) -> dict:
    """把草稿叠在当前内容上，用于预览；不写库。"""
    model = KIND_MODEL[draft.entity_kind]
    entity = model.objects.get(pk=draft.entity_id)
    merged = {**audit.snapshot(draft.entity_kind, entity), **(draft.payload or {})}
    if draft.entity_kind == 'activity':
        card = services.resolve_card(draft.entity_id)
        entry = services.serialize_entry(card, list(services.card_notice_qs(card))) if card else {}
        entry.update({key: merged[key] for key in ('title', 'summary', 'tags', 'editorial_note')
                      if key in merged})
        return {'kind': 'activity', 'entity': merged, 'entry': entry}
    if draft.entity_kind == 'guide':
        detail = services.guide_detail(draft.entity_id) or {}
        detail.update({key: merged[key] for key in
                       ('title', 'subtitle', 'summary', 'scope', 'caution', 'source_note')
                       if key in merged})
        return {'kind': 'guide', 'entity': merged, 'guide': detail}
    return {'kind': draft.entity_kind, 'entity': merged}
