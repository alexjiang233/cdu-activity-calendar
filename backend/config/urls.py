from django.conf import settings
from django.contrib import admin
from django.http import FileResponse, Http404, JsonResponse
from django.urls import include, path
from django.views.decorators.cache import never_cache
from django.views.static import serve
from pathlib import Path
from catalog import workbench, maintenance


admin.site.site_header = '成都大学校园活动与指南 · 管理后台'
admin.site.site_title = '校园活动后台'
admin.site.index_title = '内容维护'


@never_cache
def spa_index(request):
    """同源提供前端构建产物；未构建时给出可读提示，而不是 500。"""
    dist = Path(settings.FRONTEND_DIST)
    index = dist / 'index.html'
    if not index.exists():
        return JsonResponse(
            {'detail': '前端尚未构建：请运行 python frontend/build.py', 'dist': str(dist)},
            status=503, json_dumps_params={'ensure_ascii': False},
        )
    return FileResponse(open(index, 'rb'), content_type='text/html; charset=utf-8')


urlpatterns = [
    path('manage/settings/', include((maintenance.urlpatterns, 'maintenance'), namespace='maintenance')),
    path('manage/', include((workbench.urlpatterns, 'workbench'), namespace='workbench')),
    path('assets/<path:path>', serve, {'document_root': Path(settings.FRONTEND_DIST) / 'assets'}),
    path('admin/', maintenance.legacy),
    path('admin/<path:old_path>', maintenance.legacy),
    path('api/v1/', include('catalog.api.urls')),
    path('', spa_index),
]
