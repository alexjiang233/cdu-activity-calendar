"""可检索文本与月份索引：写入时算一次，读列表时不再装全部事实。

改动通知的事实、画像、日期或活动标题后，调用 refresh_notice / refresh_activity
（或整体 refresh_all），保证列表搜索与“往年这个月”跟正文一致。
"""
from __future__ import annotations

from . import services
from .models import Activity, Notice


def refresh_notice(notice: Notice, save: bool = True) -> Notice:
    facts = list(notice.facts.all())
    profile = getattr(notice, 'profile', None)
    notice.search_text = services.notice_search_text(notice, facts=facts, profile=profile)
    months = services.seasonal_months_for_notice(notice)
    notice.seasonal_months = services.encode_months(months)
    if save:
        Notice.objects.filter(pk=notice.pk).update(
            search_text=notice.search_text, seasonal_months=notice.seasonal_months)
    return notice


def refresh_activity(activity: Activity, save: bool = True) -> Activity:
    activity.search_text = services.activity_search_text(activity)
    if save:
        Activity.objects.filter(pk=activity.pk).update(search_text=activity.search_text)
    return activity


def refresh_all(batch: int = 200) -> dict:
    notices = 0
    for notice in Notice.objects.prefetch_related('facts').select_related('profile').iterator(chunk_size=batch):
        refresh_notice(notice)
        notices += 1
    activities = 0
    for activity in Activity.objects.select_related('category').iterator(chunk_size=batch):
        refresh_activity(activity)
        activities += 1
    return {'notices': notices, 'activities': activities}
