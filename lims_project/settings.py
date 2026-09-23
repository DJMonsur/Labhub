"""
PSHS-CARC Biology Laboratory LIMS
Django settings — Asirit, Espallardo & Garcia (2025)

CHANGES vs v1:
  - SECRET_KEY, DEBUG, ALLOWED_HOSTS, and all DATABASES credentials are now
    read from environment variables via python-decouple, instead of being
    hardcoded. This lets the repo be shared publicly without leaking the
    MySQL password or Django secret key.

  - Each developer copies `.env.example` to `.env` (gitignored) and fills
    in their own local values. Sensible defaults are provided for everything
    except DB_PASSWORD, so a fresh clone mostly "just works" after that.
"""

from pathlib import Path
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent

# ─── SECURITY ────────────────────────────────────────────────────────────────
# Falls back to an obviously-insecure dev key if .env is missing, so the
# server still boots for a quick look — but every real deployment should
# set DJANGO_SECRET_KEY in .env.
SECRET_KEY = config(
    'DJANGO_SECRET_KEY',
    default='django-insecure-pshs-carc-lims-change-before-production',
)
DEBUG = config('DJANGO_DEBUG', default=False, cast=bool)
ALLOWED_HOSTS = config('DJANGO_ALLOWED_HOSTS', default='*', cast=Csv())

# ─── APPLICATIONS ────────────────────────────────────────────────────────────
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',
    'inventory',
    'django.contrib.sites',
    'allauth',
    'allauth.account',
    'allauth.socialaccount',
    'allauth.socialaccount.providers.google',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    # WhiteNoise serves /static/ directly from the app process. Without it,
    # DEBUG=False means Django stops serving static files and the site loads
    # with no CSS at all — the single most common "it worked locally" bug.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'allauth.account.middleware.AccountMiddleware',
]

ROOT_URLCONF = 'lims_project.urls'
SITE_ID = 1
TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'inventory.context_processors.auth_flags',
            ],
        },
    },
]
WSGI_APPLICATION = 'lims_project.wsgi.application'

# ─── DATABASE ────────────────────────────────────────────────────────────────
# Two modes, chosen by DB_ENGINE in .env:
#
#   sqlite  (default) — zero setup. Django creates db.sqlite3 in this folder.
#                       Best for running the project locally or demoing it.
#   mysql             — the original setup. Requires MySQL installed and the
#                       biology_lab_lims.sql file imported first.
#
# SQLite is the default purely so a fresh clone runs with no install steps.
# Nothing about the app changes; the models and queries are identical.
DB_ENGINE = config('DB_ENGINE', default='sqlite').lower()

if DB_ENGINE in ('mysql', 'django.db.backends.mysql'):
    DATABASES = {
        'default': {
            'ENGINE':   'django.db.backends.mysql',
            'NAME':     config('DB_NAME',     default='lims_db'),
            'USER':     config('DB_USER',     default='root'),
            'PASSWORD': config('DB_PASSWORD', default=''),
            'HOST':     config('DB_HOST',     default='127.0.0.1'),
            'PORT':     config('DB_PORT',     default='3306'),
            'OPTIONS': {
                'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
                'charset': 'utf8mb4',
            },
        }
    }
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME':   BASE_DIR / 'db.sqlite3',
        }
    }

# ─── CORS ────────────────────────────────────────────────────────────────────
# The frontend is served by this same Django app, so it does not need CORS at
# all in production. Default follows DEBUG: open locally, closed live.
CORS_ALLOW_ALL_ORIGINS = config('CORS_ALLOW_ALL_ORIGINS', default=DEBUG, cast=bool)

# ─── STATIC FILES ────────────────────────────────────────────────────────────
STATIC_URL = '/static/'
STATICFILES_DIRS = [BASE_DIR / 'static']

# `collectstatic` gathers every static file into this folder for the web
# server to serve. Run it on every deploy; it is gitignored.
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Let WhiteNoise read straight from STATICFILES_DIRS in development, so the
# app serves CSS correctly WITHOUT anyone having to run collectstatic first.
WHITENOISE_USE_FINDERS = DEBUG
WHITENOISE_AUTOREFRESH = DEBUG   # pick up CSS edits without a restart

STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    'staticfiles': {
        # IMPORTANT: the hashed-manifest storage is production-only.
        # It needs a staticfiles.json manifest that only exists after
        # collectstatic has run. Leaving it switched on in development means
        # every stylesheet silently fails to resolve and the whole site loads
        # with no CSS at all — which is exactly what it looks like: raw
        # unstyled HTML with giant SVGs.
        'BACKEND': (
            'whitenoise.storage.CompressedManifestStaticFilesStorage'
            if not DEBUG else
            'django.contrib.staticfiles.storage.StaticFilesStorage'
        ),
    },
}

# ─── PRODUCTION HARDENING ────────────────────────────────────────────────────
# Everything below only switches on when DJANGO_DEBUG=False, so local
# development is unaffected.

# Hosts that may submit forms. Set this to your real domain in .env, e.g.
#   CSRF_TRUSTED_ORIGINS=https://labhub.example.com
CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='', cast=Csv())

if not DEBUG:
    # Trust the proxy's protocol header so Django knows requests are HTTPS.
    SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
    SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)

    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE    = True
    SESSION_COOKIE_HTTPONLY = True

    # HSTS: tell browsers to only ever reach this domain over HTTPS.
    # Start at a low value while testing, then raise to 31536000 (1 year).
    SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=3600, cast=int)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True

    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = 'DENY'

# ─── MISC ─────────────────────────────────────────────────────────────────────
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Asia/Manila'
USE_I18N = True
USE_TZ = True

#——— ALLAUTH ———————————————————————————————————————————————————————————————————
AUTHENTICATION_BACKENDS = [
    'django.contrib.auth.backends.ModelBackend',
    'allauth.account.auth_backends.AuthenticationBackend',
]

# Google sign-in is OPTIONAL. Leave these blank and the app falls back to
# ordinary username/password login, so you can run the project without
# creating a Google Cloud project first. Fill them in and the Google button
# appears automatically on the sign-in page.
GOOGLE_CLIENT_ID     = config('GOOGLE_CLIENT_ID',     default='')
GOOGLE_CLIENT_SECRET = config('GOOGLE_CLIENT_SECRET', default='')
GOOGLE_LOGIN_ENABLED = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)

if GOOGLE_LOGIN_ENABLED:
    SOCIALACCOUNT_PROVIDERS = {
        'google': {
            'APP': {
                'client_id': GOOGLE_CLIENT_ID,
                'secret':    GOOGLE_CLIENT_SECRET,
                'key':       '',
            },
            'SCOPE': ['email', 'profile'],
            'AUTH_PARAMS': {
                'access_type': 'online',
                'prompt': 'select_account',
            },
        }
    }
else:
    SOCIALACCOUNT_PROVIDERS = {}

# When Google sign-in is on, only school accounts are accepted. Set this to an
# empty string to allow any Google account (useful while testing).
ALLOWED_EMAIL_DOMAIN = config('ALLOWED_EMAIL_DOMAIN', default='carc.pshs.edu.ph')

# Username/password login settings (used when Google is off)
ACCOUNT_LOGIN_METHODS = {'username'}
ACCOUNT_SIGNUP_FIELDS = ['username*', 'password1*', 'password2*']

# Where to send users after login/logout
LOGIN_REDIRECT_URL  = '/'
LOGOUT_REDIRECT_URL = '/'

# Don't require email verification since Google already verified it
SOCIALACCOUNT_EMAIL_VERIFICATION = 'none'
ACCOUNT_EMAIL_VERIFICATION       = 'none'
