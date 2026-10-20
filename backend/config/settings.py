"""Django settings：本地 SQLite 开发，生产 PostgreSQL + 环境变量。"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent          # backend/
PROJECT_DIR = BASE_DIR.parent                              # 校园机会试点/
FRONTEND_DIST = Path(os.getenv('FRONTEND_DIST', PROJECT_DIR / 'frontend' / 'dist'))

DEBUG = os.getenv('DEBUG', '1') == '1'
SECRET_KEY = os.getenv('DJANGO_SECRET_KEY', '')
if not SECRET_KEY:
    if not DEBUG:
        raise RuntimeError('生产环境必须设置 DJANGO_SECRET_KEY')
    SECRET_KEY = 'local-development-only-campus-catalog'

ALLOWED_HOSTS = os.getenv('ALLOWED_HOSTS', 'localhost,127.0.0.1,testserver').split(',')
CSRF_TRUSTED_ORIGINS = [
    origin for origin in os.getenv(
        'CSRF_TRUSTED_ORIGINS', 'http://localhost:8790,http://127.0.0.1:8790'
    ).split(',') if origin
]

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'rest_framework',
    'catalog',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # 生产静态文件由应用自己给（WhiteNoise），Caddy 只做反向代理
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'

TEMPLATES = [{
    'BACKEND': 'django.template.backends.django.DjangoTemplates',
    'DIRS': [BASE_DIR / 'templates'],
    'APP_DIRS': True,
    'OPTIONS': {'context_processors': [
        'django.template.context_processors.request',
        'django.contrib.auth.context_processors.auth',
        'django.contrib.messages.context_processors.messages',
    ]},
}]

if os.getenv('POSTGRES_DB'):
    DATABASES = {'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.environ['POSTGRES_DB'],
        'USER': os.getenv('POSTGRES_USER', 'campus'),
        'PASSWORD': os.getenv('POSTGRES_PASSWORD', ''),
        'HOST': os.getenv('POSTGRES_HOST', '127.0.0.1'),
        'PORT': os.getenv('POSTGRES_PORT', '5432'),
        'CONN_MAX_AGE': 60,
    }}
else:
    if not DEBUG:
        # 生产环境缺数据库配置时直接拒绝启动，不能悄悄建一个空 SQLite
        raise RuntimeError('生产环境必须配置 PostgreSQL：POSTGRES_DB / POSTGRES_USER / '
                           'POSTGRES_PASSWORD / POSTGRES_HOST / POSTGRES_PORT')
    DATABASES = {'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': Path(os.getenv('DJANGO_DB', BASE_DIR / 'db.sqlite3')),
        'OPTIONS': {'timeout': 20},
    }}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
     'OPTIONS': {'min_length': 10}},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'zh-hans'
TIME_ZONE = 'Asia/Shanghai'

# 登录后回后台首页，而不是 Django 默认的 /accounts/profile/
LOGIN_URL = '/admin/login/'
LOGIN_REDIRECT_URL = '/admin/'
LOGOUT_REDIRECT_URL = '/admin/login/'
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = ([FRONTEND_DIST / 'assets'] if (FRONTEND_DIST / 'assets').exists() else [])
# 生产：压缩 + 带哈希清单，由 WhiteNoise 直接发送；开发仍用 runserver 的静态供给
if not DEBUG:
    STORAGES = {
        'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
        'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
    }
WHITENOISE_MAX_AGE = 60 * 60 * 24 * 30 if not DEBUG else 0
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': ['rest_framework.authentication.SessionAuthentication'],
    'DEFAULT_PERMISSION_CLASSES': ['rest_framework.permissions.AllowAny'],
    'DEFAULT_RENDERER_CLASSES': ['rest_framework.renderers.JSONRenderer'],
    'DEFAULT_PAGINATION_CLASS': None,
    'UNICODE_JSON': False,
    'COMPACT_JSON': True,
}

# 公开接口分页
PUBLIC_PAGE_SIZE = int(os.getenv('PUBLIC_PAGE_SIZE', '12'))
PUBLIC_MAX_PAGE_SIZE = int(os.getenv('PUBLIC_MAX_PAGE_SIZE', '48'))

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
# 本机验证生产链路时可以关掉跳转（SECURE_SSL_REDIRECT=0）
SECURE_SSL_REDIRECT = (not DEBUG) and os.getenv('SECURE_SSL_REDIRECT', '1') == '1'
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
X_FRAME_OPTIONS = 'DENY'
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024

# 日志：保留排查信息，不输出密钥与数据库配置
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {'plain': {'format': '%(asctime)s %(levelname)s %(name)s %(message)s'}},
    'handlers': {'console': {'class': 'logging.StreamHandler', 'formatter': 'plain'}},
    'root': {'handlers': ['console'], 'level': os.getenv('LOG_LEVEL', 'INFO')},
    'loggers': {'django.db.backends': {'level': 'WARNING'}},
}

# 旧库与前端产物路径（迁移命令默认值，均可被命令行覆盖）
LEGACY_DB = Path(os.getenv('LEGACY_DB', PROJECT_DIR / 'data' / 'campus.sqlite3'))
LEGACY_PUBLIC_PAGE = Path(os.getenv(
    'LEGACY_PUBLIC_PAGE',
    PROJECT_DIR / 'work' / 'backend-migration-2026-10-20' / 'public-page-snapshot.html',
))
LEGACY_GUIDE_DATA = Path(os.getenv('LEGACY_GUIDE_DATA', PROJECT_DIR / 'work' / 'campus-life-v1' / 'src' / 'life-data.json'))
