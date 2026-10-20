"""统一的编辑入口：任何对外可见的改动都要在这里落修订与变更记录。

为什么集中：后台批量动作、导入命令、草稿发布、回退如果各写一套，
审计就会缺行、公开内容也可能绕过修订直接改掉。
"""
from __future__ import annotations

import gzip
import hashlib
import json
from datetime import date, datetime
from uuid import uuid4

from django.utils import timezone
from django.db import transaction
from django.core.exceptions import FieldDoesNotExist

from . import indexing
from .models import (Activity, CampusService, ChangeLog, Fact, Guide, GuideBlock,
                     GuideFaq, GuideSection, Notice, Revision, SiteMeta)


def _jsonable(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return value


def content_hash(payload: dict) -> str:
    raw = json.dumps(_jsonable(payload), sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def matches_snapshot(kind,entity,previous):
    """Old revisions predate newly editable fields; compare their recorded fields only."""
    current=snapshot(kind,entity)
    return bool(previous) and all(key in current and current[key]==value for key,value in previous.items())


def snapshot(kind: str, entity) -> dict:
    """可恢复的内容快照：只包含公开/编辑关心的字段与子条目。"""
    if kind == 'activity':
        return {
            'id': entity.id, 'title': entity.title, 'summary': entity.summary,
            'tags': entity.tags, 'editorial_note': entity.editorial_note,
            'featured': entity.featured, 'spotlight': entity.spotlight,
            'position': entity.position, 'visibility': entity.visibility,
            'category': entity.category_id,
            'kind': entity.kind, 'split_by_college': entity.split_by_college, 'material_ids':entity.material_ids,
        }
    if kind == 'notice':
        return {
            'id': entity.id, 'activity': entity.activity_id,
            'display_activity': entity.display_activity_id,
            'year': entity.year,
            'visibility':entity.visibility,
            'published': _jsonable(entity.published), 'deadline': _jsonable(entity.deadline),
            'deadline_kind': entity.deadline_kind, 'stage_start': _jsonable(entity.stage_start),
            'stage_end': _jsonable(entity.stage_end), 'audience': entity.audience,
            'conflict': entity.conflict, 'position': entity.position,
            'extras': entity.extras,
            'facts': list(entity.facts.order_by('position', 'id').values(
                'id', 'kind', 'label', 'value', 'quote', 'locator', 'source_url', 'basis', 'position')),
        }
    if kind == 'guide':
        return {
            'id': entity.id, 'title': entity.title, 'subtitle': entity.subtitle,
            'summary': entity.summary, 'scope': entity.scope, 'caution': entity.caution,
            'source_note': entity.source_note, 'category': entity.category,
            'visibility': entity.visibility, 'related_service': entity.related_service,
            'number':entity.number,'icon':entity.icon,'tags':entity.tags,'position':entity.position,
            'sections': [{'id': s.pk, 'title': s.title, 'kind': s.kind, 'position': s.position,
                          'blocks': list(s.blocks.order_by('position', 'pk').values('id', 'text', 'kind', 'position'))}
                         for s in entity.sections.order_by('position', 'pk')],
            'faqs': list(entity.faqs.order_by('position', 'pk').values('id', 'question', 'answer', 'position')),
        }
    if kind == 'service':
        return {
            'id': entity.id, 'name': entity.name, 'category': entity.category,
            'description': entity.description, 'owner': entity.owner, 'phone': entity.phone,
            'url': entity.url, 'location': entity.location, 'open_hours': entity.open_hours,
            'note': entity.note, 'visibility': entity.visibility,
            'position':entity.position,'source_url':entity.source_url,'source_label':entity.source_label,
            'source_date':_jsonable(entity.source_date),'checked_on':_jsonable(entity.checked_on),'related_guide':entity.related_guide,
        }
    raise ValueError(f'未知对象类型 {kind}')


def _model_for(kind: str):
    return {'activity': Activity, 'notice': Notice, 'guide': Guide,
            'service': CampusService}[kind]


def _assign(entity, updates):
    """Restore typed model fields and explicitly scoped child rows from our snapshots."""
    for key, value in updates.items():
        if key in ('id', 'facts', 'sections', 'faqs'):
            continue
        try:
            field = entity._meta.get_field(key)
        except FieldDoesNotExist:
            continue
        if field.concrete:
            setattr(entity, field.attname, field.target_field.to_python(value)
                    if field.many_to_one else field.to_python(value))
    entity.save()
    if isinstance(entity, Notice) and 'facts' in updates:
        existing = set(entity.facts.values_list('pk', flat=True))
        for row in updates['facts']:
            if row['id'] not in existing:
                raise ValueError('事实条目已变化，请重新打开后编辑。')
            entity.facts.filter(pk=row['id']).update(**{k: row[k] for k in
                ('kind', 'label', 'value', 'quote', 'locator', 'source_url', 'basis', 'position') if k in row})
    if isinstance(entity, Guide):
        for section in updates.get('sections', []):
            qs = entity.sections.filter(pk=section['id'])
            if not qs.exists():
                raise ValueError('指南步骤已变化，请重新打开后编辑。')
            qs.update(**{k: section[k] for k in ('title', 'kind', 'position')})
            for block in section.get('blocks', []):
                changed = GuideBlock.objects.filter(pk=block['id'], section_id=section['id'],
                                                    section__guide=entity).update(
                    **{k: block[k] for k in ('text', 'kind', 'position')})
                if not changed:
                    raise ValueError('指南条目已变化，请重新打开后编辑。')
        for faq in updates.get('faqs', []):
            if not entity.faqs.filter(pk=faq['id']).update(
                    **{k: faq[k] for k in ('question', 'answer', 'position')}):
                raise ValueError('指南问答已变化，请重新打开后编辑。')


def apply_snapshot(kind: str, payload: dict):
    """把快照写回对象（用于回退），只认白名单字段。"""
    model = _model_for(kind)
    entity = model.objects.get(pk=payload['id'])
    allowed = snapshot(kind, entity)
    _assign(entity, {key: value for key, value in payload.items() if key in allowed})
    if kind == 'notice':
        indexing.refresh_notice(entity)
    if kind == 'activity':
        indexing.refresh_activity(entity)
    return entity


def open_revision(reason: str, origin: str, actor=None, payload: dict | None = None) -> Revision:
    revision = Revision.objects.create(
        id=f"rev-{timezone.localtime():%Y%m%d%H%M%S}-{uuid4().hex[:6]}",
        parent_id=(SiteMeta.objects.first().current_revision if SiteMeta.objects.exists() else ''),
        reason=reason, origin=origin,
        snapshot=gzip.compress(json.dumps(_jsonable(payload or {}), ensure_ascii=False).encode('utf-8')),
        catalog_hash=content_hash(payload or {}),
        created_at=timezone.now(),
    )
    return revision


def publish_revision(revision: Revision) -> Revision:
    meta, _ = SiteMeta.objects.get_or_create(id=1)
    meta.current_revision = revision.id
    meta.published_at = timezone.now()
    meta.save(update_fields=['current_revision', 'published_at'])
    return revision


def log_change(revision: Revision, kind: str, entity_id: str, action: str,
               before: dict | None = None, after: dict | None = None,
               actor=None, note: str = '') -> ChangeLog:
    return ChangeLog.objects.create(
        revision=revision, entity_kind=kind, entity_id=entity_id, action=action,
        before_hash=content_hash(before or {}), after_hash=content_hash(after or {}),
        note=note[:200], actor=actor,
    )


@transaction.atomic
def apply_updates(kind: str, entity, updates: dict, *, reason: str, origin: str,
                  actor=None, note: str = '', publish: bool = True,
                  revision: Revision | None = None) -> Revision | None:
    """改内容 + 记修订 + 更新索引。没有实际变化时返回 None。

    传入 revision 可以把同一批改动归到一条修订里，由调用方统一发布。
    """
    entity = type(entity).objects.select_for_update().get(pk=entity.pk)
    before = snapshot(kind, entity)
    changed = {key: value for key, value in updates.items()
               if key in before and before[key] != _jsonable(value)}
    if not changed:
        return None
    own = revision is None
    if own:
        revision = open_revision(reason, origin, actor=actor,
                                 payload={'kind': kind, 'id': entity.id,
                                          'before': before, 'after': {**before, **changed}})
    _assign(entity, changed)
    if kind == 'notice':
        indexing.refresh_notice(entity)
    elif kind == 'activity':
        indexing.refresh_activity(entity)
    log_change(revision, kind, entity.id, 'update', before, snapshot(kind, entity),
               actor=actor, note=note or reason)
    if publish and own:
        publish_revision(revision)
    return revision


@transaction.atomic
def restore(revision: Revision, *, actor=None, note: str = '') -> list[str]:
    """按修订里的 before 内容回退；回退本身也生成一条新修订。"""
    payload = json.loads(gzip.decompress(revision.snapshot).decode('utf-8')) if revision.snapshot else {}
    kind, entity_id, before = payload.get('kind'), payload.get('id'), payload.get('before')
    if not (kind and entity_id and before):
        raise ValueError('这条修订没有可恢复的内容快照')
    rollback = open_revision(f'回退到 {revision.id}', 'restore', actor=actor,
                             payload={'kind': kind, 'id': entity_id,
                                      'before': snapshot(kind, _model_for(kind).objects.get(pk=entity_id)),
                                      'after': before})
    apply_snapshot(kind, before)
    log_change(rollback, kind, entity_id, 'restore', None, before, actor=actor,
               note=note or f'回退到 {revision.id}')
    publish_revision(rollback)
    return [rollback.id]
