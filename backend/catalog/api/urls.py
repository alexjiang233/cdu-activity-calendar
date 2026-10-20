from django.urls import path

from . import public


def safe(view):
    """把参数错误统一转成 400 JSON，而不是 500。"""
    def wrapper(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except public.BadRequest as exc:
            return public.error(str(exc), status=400)
    wrapper.__name__ = view.__name__
    return wrapper


urlpatterns = [
    path('meta/', safe(public.meta)),
    path('home/', safe(public.home)),
    path('taxonomies/', safe(public.taxonomies)),
    path('activities/', safe(public.activity_list)),
    path('activities/<str:activity_id>/', safe(public.activity_detail)),
    path('activities/<str:activity_id>/notices/<str:notice_id>/', safe(public.notice_detail)),
    path('calendar/', safe(public.calendar)),
    path('guides/', safe(public.guides)),
    path('guides/<str:guide_id>/', safe(public.guide_detail)),
    path('services/', safe(public.services_list)),
]
