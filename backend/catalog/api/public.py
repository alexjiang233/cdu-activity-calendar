"""公开只读接口实现：/api/v1/。"""
from __future__ import annotations

import json
from datetime import date

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .. import services
from ..models import Activity, ActivityGroup

MAX_PAGE_SIZE = settings.PUBLIC_MAX_PAGE_SIZE
DEFAULT_PAGE_SIZE = settings.PUBLIC_PAGE_SIZE


class BadRequest(Exception):
    pass


def ok(payload, status=200):
    response = JsonResponse(payload, status=status, safe=False,
                            json_dumps_params={'ensure_ascii': False})
    # 后台改动后刷新即可看到最新内容，不缓存旧结果
    response['Cache-Control'] = 'no-store, max-age=0'
    return response


def error(message, status=400):
    return ok({'detail': message}, status=status)


def _int_param(request, name, default=None, minimum=None, maximum=None):
    raw = request.GET.get(name)
    if raw in (None, ''):
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise BadRequest(f'参数 {name} 需要整数')
    if minimum is not None and value < minimum:
        raise BadRequest(f'参数 {name} 不能小于 {minimum}')
    if maximum is not None and value > maximum:
        raise BadRequest(f'参数 {name} 不能大于 {maximum}')
    return value


def _clean(payload):
    """去掉内部字段，避免私有标记进入公开响应。"""
    if isinstance(payload, dict):
        return {k: _clean(v) for k, v in payload.items() if not k.startswith('_')}
    if isinstance(payload, list):
        return [_clean(item) for item in payload]
    return payload


@require_GET
def meta(request):
    return ok(services.meta_payload())


@require_GET
def home(request):
    return ok(_clean(services.home_payload()))


@require_GET
def taxonomies(request):
    return ok(services.taxonomy_payload())


@require_GET
def activity_list(request):
    view = request.GET.get('view', 'all')
    if view not in ('all', 'discover', 'registration', 'compare'):
        raise BadRequest('view 只能是 all / discover / registration / compare')
    month = request.GET.get('month', '')
    if month and month != 'unknown':
        try:
            month = int(month)
        except ValueError:
            raise BadRequest('month 需要 1-12 或 unknown')
        if not 1 <= month <= 12:
            raise BadRequest('month 需要 1-12 或 unknown')
        month = str(month)
    year = request.GET.get('year', '')
    if year and year != 'unknown' and not (len(year) == 4 and year.isdigit()):
        raise BadRequest('year 需要四位年份或 unknown')
    basis = request.GET.get('month_basis', 'seasonal')
    if basis not in ('seasonal', 'deadline', 'event'):
        raise BadRequest('month_basis 只能是 seasonal / deadline / event')

    page = _int_param(request, 'page', 1, minimum=1)
    page_size = _int_param(request, 'page_size', DEFAULT_PAGE_SIZE, minimum=1, maximum=MAX_PAGE_SIZE)
    filters = services.Filters(
        q=request.GET.get('q', '')[:120],
        view=view,
        category=request.GET.get('categories') or request.GET.get('category', ''),
        college=request.GET.get('college', ''),
        level=request.GET.get('level', ''),
        year=year,
        month=month,
        month_basis=basis,
        interest=request.GET.get('interest', 'any'),
        page=page,
        page_size=page_size,
    )
    data = services.query_entries(filters)
    results = data['results']
    dates = [r.get('published') for r in results if r.get('published')]
    return ok(_clean({
        'count': data['count'],
        'page': data['page'],
        'page_size': data['page_size'],
        'total_pages': data['total_pages'],
        'page_date_range': {'newest': max(dates), 'oldest': min(dates)} if len(dates) == len(results) and dates else None,
        'results': results,
    }))


@require_GET
def activity_detail(request, activity_id):
    notice_id = request.GET.get('notice')
    payload = services.activity_detail(activity_id, notice_id)
    if payload is None:
        return error('没有找到这条公开活动', status=404)
    return ok(_clean(payload))


@require_GET
def notice_detail(request, activity_id, notice_id):
    payload = services.activity_detail(activity_id, notice_id)
    if payload is None:
        return error('没有找到这条公开通知', status=404)
    return ok(_clean({'entry': {'id': payload['entry']['id'], 'title': payload['entry']['title']},
                      'notice': payload['notice']}))


@require_GET
def calendar(request):
    mode = request.GET.get('mode', 'annual')
    if mode not in ('annual', 'actual', 'actual_counts'):
        raise BadRequest('mode 只能是 annual / actual')
    if mode == 'annual':
        raw = request.GET.get('month', '')
        if raw == 'all':
            return ok({'mode': 'annual_counts', 'counts': services.annual_counts()})
        month = _int_param(request, 'month', None, minimum=1, maximum=12)
        if month is None:
            month = services.china_now().month
        return ok(_clean(services.calendar_annual(month)))
    if mode == 'actual_counts':
        year = _int_param(request, 'year', None, minimum=2000, maximum=2100)
        if year is None:
            raise BadRequest('actual_counts 需要 year')
        return ok({'mode': 'actual_counts', 'year': year, 'counts': services.actual_counts(year)})
    year = _int_param(request, 'year', None, minimum=2000, maximum=2100)
    month = _int_param(request, 'month', services.china_now().month, minimum=1, maximum=12)
    if year is None:
        raise BadRequest('actual 模式需要 year 参数')
    return ok(_clean(services.calendar_actual(year, month)))


@require_GET
def guides(request):
    category = request.GET.get('category', '')
    q = request.GET.get('q', '')[:80]
    rows = services.guide_list(category, q)
    return ok({'count': len(rows), 'results': rows})


@require_GET
def guide_detail(request, guide_id):
    payload = services.guide_detail(guide_id)
    if payload is None:
        return error('没有找到这篇校园指南', status=404)
    return ok(payload)


@require_GET
def services_list(request):
    category = request.GET.get('category', '')
    q = request.GET.get('q', '')[:80]
    rows = services.service_list(category, q)
    return ok({'count': len(rows), 'results': rows})
