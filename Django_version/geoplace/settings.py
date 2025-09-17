"""
Django settings for GeoPlace project.
"""

from pathlib import Path
import os

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-geoplace-dev-key-change-in-production'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['*']

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'channels',
    'corsheaders',
    'rest_framework',
    'core',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'geoplace.urls'

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
            ],
        },
    },
]

WSGI_APPLICATION = 'geoplace.wsgi.application'
ASGI_APPLICATION = 'geoplace.asgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

# Password validation
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

# Internationalization
LANGUAGE_CODE = 'ja'
TIME_ZONE = 'Asia/Tokyo'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

# Media files
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# CORS settings
CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

# REST Framework settings
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 50
}

# Channels settings
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'channels.layers.InMemoryChannelLayer',
    },
}

# GeoPlace specific settings
GEOPLACE_CONFIG = {
    'TILE_SIZE': 32,
    'CANVAS_WIDTH': 20000,
    'CANVAS_HEIGHT': 20000,
    'TILES_DIR': Path('E:/files/GeoPLace-tmp/images'),
    'ASSETS_DIR': BASE_DIR / 'assets',
    'GLB_DIR': BASE_DIR / 'assets' / 'glb',
    'CACHE_DIR': BASE_DIR / 'cache',
    
    # AI Pipeline settings
    'LM_STUDIO_BASE_URL': 'https://1bbf562c5b2d.ngrok-free.app/v1/chat/completions',
    'LM_STUDIO_MODEL': 'gemma-3-4b-it',
    'LM_STUDIO_TIMEOUT': 30,
    
    'SD_MODEL_ID': 'runwayml/stable-diffusion-v1-5',
    'SD_RESOLUTION': 512,
    'SD_STEPS_LIGHT': 20,
    'SD_STEPS_HIGH': 50,
    
    'TRIPOSR_DIR': Path('E:/GITS/TripoSR-main'),
    'TRIPOSR_PY': 'run.py',
    'TRIPOSR_BAKE_TEXTURE': True,
    
    'MAX_CONCURRENT_WORKERS': 4,
    'PER_TILE_COOLDOWN': 5,
    'ENABLE_REFINER': True,
    'REFINE_DELAY_SEC': 5,
}

# Ensure directories exist
for dir_path in [
    GEOPLACE_CONFIG['TILES_DIR'],
    GEOPLACE_CONFIG['ASSETS_DIR'],
    GEOPLACE_CONFIG['GLB_DIR'],
    GEOPLACE_CONFIG['CACHE_DIR'],
]:
    dir_path.mkdir(parents=True, exist_ok=True)

"""Logging configuration
Removes invalid 'file' handler reference and ensures console logging for key modules.
"""
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'loggers': {
        # Project-level logger
        'geoplace': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': True,
        },
        # App-specific logger for detailed tile diagnostics
        'core.views': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'WARNING',
    },
}
