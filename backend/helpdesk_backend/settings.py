from decouple import config
from datetime import timedelta
import os
import json
from pathlib import Path
from celery.schedules import crontab

BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = config('SECRET_KEY')
DEBUG = config('DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='').split(',')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    
    # Third-party apps
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',
    
    # Local apps
    'users',
    'tickets',
    'callogs',
    'content',
    'newsletter',
    'dashboard',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'helpdesk_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'helpdesk_backend.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME', default='mydb'),
        'USER': config('DB_USER', default='norris'),
        'PASSWORD': config('DB_PASSWORD', default='newpassword'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5434'),
    }
}

# Custom User Model
AUTH_USER_MODEL = 'users.User'

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
        'OPTIONS': {
            'min_length': 8,
        }
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Harare'  # Zimbabwe timezone
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# CORS settings
CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', default='http://localhost:3000').split(',')
CORS_ALLOW_CREDENTIALS = True

# Django REST Framework
REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DATETIME_FORMAT': '%Y-%m-%d %H:%M:%S',
}

# JWT Settings
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(hours=2),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
    
    'ALGORITHM': 'HS256',
    'SIGNING_KEY': SECRET_KEY,
    'VERIFYING_KEY': None,
    'AUDIENCE': None,
    'ISSUER': None,
    
    'AUTH_HEADER_TYPES': ('Bearer',),
    'AUTH_HEADER_NAME': 'HTTP_AUTHORIZATION',
    'USER_ID_FIELD': 'id',
    'USER_ID_CLAIM': 'user_id',
    
    'AUTH_TOKEN_CLASSES': ('rest_framework_simplejwt.tokens.AccessToken',),
    'TOKEN_TYPE_CLAIM': 'token_type',
}

# Email Configuration
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = config('EMAIL_HOST', default='smtp.gmail.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default=EMAIL_HOST_USER)

# reCAPTCHA Settings
RECAPTCHA_SECRET_KEY = config('RECAPTCHA_SECRET_KEY', default='')
RECAPTCHA_SITE_KEY = config('RECAPTCHA_SITE_KEY', default='')

# Celery Configuration (for async tasks)
CELERY_BROKER_URL = config('REDIS_URL', default='redis://localhost:6379/0')
CELERY_RESULT_BACKEND = config('REDIS_URL', default='redis://localhost:6379/0')
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    'process-report-schedules-hourly': {
        'task': 'dashboard.tasks.process_report_schedules',
        'schedule': crontab(minute=0),
    },
}

# Automated assignment settings
AUTO_ASSIGN_REQUESTOR_ROLES = config('AUTO_ASSIGN_REQUESTOR_ROLES', default='accounts').split(',')
AUTO_ASSIGN_MAX_OPEN_JOBS = config('AUTO_ASSIGN_MAX_OPEN_JOBS', default=4, cast=int)
AUTO_ASSIGN_MAX_OPEN_TICKETS = config('AUTO_ASSIGN_MAX_OPEN_TICKETS', default=7, cast=int)
AUTO_ASSIGN_MAX_ACTIVE_LOAD = config('AUTO_ASSIGN_MAX_ACTIVE_LOAD', default=4, cast=int)
AUTO_ASSIGN_ALL_JOBS = config('AUTO_ASSIGN_ALL_JOBS', default=True, cast=bool)
AUTO_ASSIGN_ALL_TICKETS = config('AUTO_ASSIGN_ALL_TICKETS', default=True, cast=bool)
AUTO_ASSIGN_TICKET_STRATEGY = config('AUTO_ASSIGN_TICKET_STRATEGY', default='round_robin')
try:
    AUTO_ASSIGN_TICKET_RULES = json.loads(config('AUTO_ASSIGN_TICKET_RULES', default='{}'))
except json.JSONDecodeError:
    AUTO_ASSIGN_TICKET_RULES = {}
try:
    AUTO_ASSIGN_JOB_RULES = json.loads(config('AUTO_ASSIGN_JOB_RULES', default='{}'))
except json.JSONDecodeError:
    AUTO_ASSIGN_JOB_RULES = {}
OVERLOAD_NOTIFICATION_RECIPIENTS = [
    email.strip() for email in config('OVERLOAD_NOTIFICATION_RECIPIENTS', default='').split(',') if email.strip()
]
SLA_HOURS_BY_PRIORITY = {
    'low': config('SLA_HOURS_LOW', default=72, cast=int),
    'medium': config('SLA_HOURS_MEDIUM', default=24, cast=int),
    'high': config('SLA_HOURS_HIGH', default=8, cast=int),
    'urgent': config('SLA_HOURS_URGENT', default=4, cast=int),
}

# Report/notification recipients
REPORT_MR_DANIEL_EMAIL = config('REPORT_MR_DANIEL_EMAIL', default='')
REPORT_MR_TAPIWA_EMAIL = config('REPORT_MR_TAPIWA_EMAIL', default='')
REPORT_STATIC_RECIPIENTS = [
    email.strip() for email in config('REPORT_STATIC_RECIPIENTS', default='').split(',') if email.strip()
]
ACCOUNTS_NOTIFICATION_RECIPIENTS = [
    email.strip() for email in config('ACCOUNTS_NOTIFICATION_RECIPIENTS', default='').split(',') if email.strip()
]
JOB_STATUS_NOTIFY_EVENTS = [
    status.strip().lower()
    for status in config('JOB_STATUS_NOTIFY_EVENTS', default='complete').split(',')
    if status.strip()
]
REPORT_ESTIMATED_COST_RATE = config('REPORT_ESTIMATED_COST_RATE', default=0.0, cast=float)
REPORT_SECURE_LINK_MAX_AGE_SECONDS = config('REPORT_SECURE_LINK_MAX_AGE_SECONDS', default=86400, cast=int)

# File Upload Settings
FILE_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB

# Security Settings (for production)
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_BROWSER_XSS_FILTER = True
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    # CORS Configuration
CORS_ALLOWED_ORIGINS = [
    'http://localhost:3000',
    'http://127.0.0.1:3000',
]
CORS_ALLOW_CREDENTIALS = True
