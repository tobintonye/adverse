from pathlib import Path
import os 
import environ
from datetime import timedelta
from celery.schedules import crontab
env = environ.Env(
    DEBUG=(bool, False)
)

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

environ.Env.read_env(os.path.join(BASE_DIR, '.env'))

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env('SECRET_KEY')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env.bool('DEBUG')

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS')

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
    'django_recaptcha',
    'security',
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist', # Allows revoking refresh tokens
    'adverse',
    'admanager',
    'advertiser',
    'device',
    'common',
    'scheduling',
    'axes',
    'core',
    'payments',
    'admin_panel',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'advertiser.middleware.CampaignStatusSyncMiddleware',
    "allauth.account.middleware.AccountMiddleware",
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'axes.middleware.AxesMiddleware',
]

SITE_ID = 1
AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesStandaloneBackend',
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

ROOT_URLCONF = 'adverseproject.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]


GOOGLE_CLIENT_ID = env('GOOGLE_CLIENT_ID')
GOOGLE_CLIENT_SECRET = env('GOOGLE_CLIENT_SECRET')

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'APP': {
            'client_id': os.environ['GOOGLE_CLIENT_ID'],
            'secret': os.environ['GOOGLE_CLIENT_SECRET'],
            'key': ''
        },
        'SCOPE': ['profile', 'email'],
        'AUTH_PARAMS': {'access_type': 'online'},
    }
}

#ACCOUNT_USER_MODEL_USERNAME_FIELD = None
#ACCOUNT_EMAIL_REQUIRED = True

ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*", "password2*"]
ACCOUNT_UNIQUE_EMAIL = True
ACCOUNT_LOGIN_METHODS = {'email'}
LOGIN_URL = 'security:login'
LOGIN_REDIRECT_URL = 'security:post_login'
ACCOUNT_LOGOUT_REDIRECT_URL = 'security:login'
ACCOUNT_EMAIL_VERIFICATION = "none"
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_LOGIN_ON_GET = True
SOCIALACCOUNT_QUERY_EMAIL = True
SOCIALACCOUNT_USERNAME_REQUIRED = False

# Automatically connect social accounts to existing users with the same email
SOCIALACCOUNT_ADAPTER = "security.adapters.MySocialAccountAdapter"

ACCOUNT_ADAPTER = "allauth.account.adapter.DefaultAccountAdapter"

# custom user
AUTH_USER_MODEL = "security.CustomUser"

WSGI_APPLICATION = 'adverseproject.wsgi.application'


# Database
DATABASES = {
    'default': env.db(),
}


# Password validation
# https://docs.djangoproject.com/en/6.0/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

REST_FRAMEWORK = {

     "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",   # for the simulator.py
        "rest_framework.parsers.FormParser",
        "rest_framework.parsers.MultiPartParser",
    ],

    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
         "device.api.authentication.DeviceTokenAuthentication", 
    ),
    
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    
    "DEFAULT_THROTTLE_RATES": {
        "anon": "20/hour",
        "user": "100/hour",
        # Custom scope for sensitive endpoints
        "auth_register": "10/hour",
        "auth_login": "10/hour",
        "auth_password_reset": "5/hour",
        "auth_resend_verification": "5/hour",
    },
     'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=5),    
    "REFRESH_TOKEN_LIFETIME": timedelta(days=1),     
    "ROTATE_REFRESH_TOKENS": True,              
    "BLACKLIST_AFTER_ROTATION": True,              
    "UPDATE_LAST_LOGIN": True,                     
    
    "ALGORITHM": "HS256",
   #  "SIGNING_KEY": env('JWT_SIGNING_KEY'),                # Use a separate key in production
    "AUTH_HEADER_TYPES": ("Bearer",),                
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# Internationalization
# https://docs.djangoproject.com/en/6.0/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/6.0/howto/static-files/

STATIC_URL = 'static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_DIRS = [os.path.join(BASE_DIR, 'static')]

MEDIA_URL = '/media/'
MEDIA_ROOT = os.path.join(BASE_DIR, 'media')


# PASSWORD_RESET_TIMEOUT = 86400
# Rate limit
RATELIMIT_ENABLE = env.bool('RATELIMIT_ENABLE')
EMAIL_BACKEND = env('EMAIL_BACKEND', default="django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env('EMAIL_HOST')
EMAIL_PORT = env.int('EMAIL_PORT', default=587)
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=True)
EMAIL_HOST_USER = env('EMAIL_HOST_USER')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD')
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default=EMAIL_HOST_USER)
ADMIN_BASE_URL = env('ADMIN_BASE_URL')
RECAPTCHA_PUBLIC_KEY = env('RECAPTCHA_SITE_KEY')
RECAPTCHA_PRIVATE_KEY = env('RECAPTCHA_SECRET_KEY')


CELERY_BROKER_URL = "redis://localhost:6379/0"
CELERY_RESULT_BACKEND = "redis://localhost:6379/0"

# Merge them into one:
CELERY_BEAT_SCHEDULE = {
    "activate-due-campaigns": {
        "task": "scheduling.tasks.activate_due_campaigns",
        "schedule": crontab(hour=0, minute=5), # 12:05am
    },
    "expire-old-campaigns": {
        "task": "scheduling.tasks.expire_old_campaigns",
        "schedule": crontab(hour=0, minute=10), # 12:10am
    },
    "expire-stale-payments": {
        "task": "payments.tasks.expire_stale_campaign_payments",
        "schedule": crontab(hour=0, minute=15),  # 12:15am 
    },
    "flag-suspicious-payouts": {
        "task": "payments.tasks.flag_suspicious_payouts",
        "schedule": crontab(hour="*/6"), # every 6 hours
    },
    "reconciliation-alert": {
        "task": "payments.tasks.send_reconciliation_alert",
        "schedule": crontab(hour=8, minute=0), # 8:00am
    },
    "sync-subaccounts": {
        "task": "payments.tasks.sync_all_subaccounts",
        "schedule": crontab(hour=2, minute=0), # 2:00am
    },

    "expire-unconfirmed-approvals": {
    "task": "scheduling.tasks.expire_unconfirmed_approvals",
    "schedule": crontab(hour=0, minute=20),  # daily, staggered from your other midnight tasks
    },
}

# CACHE CONFIGURATION 
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/1",  # Database 1 for general app caching
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        }
    },
    "axes": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/2",  # Database 2 exclusively for tracking logins
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        }
    }
}

# Tell django-axes to look at the 'axes' cache block defined above
AXES_CACHE = "axes"

# AXES CONFIGURATION 
AXES_FAILURE_LIMIT = 5  # Lockout after 5 failed attempts
AXES_COOLOFF_TIME = 1  # Lockout lasts for 1 hour
AXES_LOCK_OUT_BY_COMBINATION_USER_AND_IP = True  # Lock by IP AND username together

AXES_HANDLER = 'axes.handlers.cache.AxesCacheHandler' # Uses Redis cache so it's super fast

PAYSTACK_SECRET_KEY=env('PAYSTACK_SECRET_KEY').strip().strip("'").strip('"')
PAYSTACK_PUBLIC_KEY=env('PAYSTACK_PUBLIC_KEY').strip()

# settings.py
SITE_BASE_URL = env("SITE_BASE_URL", default="http://127.0.0.1:8000")

CSRF_TRUSTED_ORIGINS = os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")

# Needed so Django trusts ngrok's forwarded HTTPS — otherwise Django thinks
# the request came in over plain HTTP (ngrok terminates TLS and forwards
# to your local server as HTTP internally)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")