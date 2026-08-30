from saas.contrib.admin_sidebar import get_navigation

from .base import *  # noqa: F403
from .base import INSTALLED_APPS
from .base import MIDDLEWARE
from .base import env
from urllib.parse import urlparse

# GENERAL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#debug
DEBUG = True
# https://docs.djangoproject.com/en/dev/ref/settings/#secret-key
SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    default="kpUkWWn8LMtTjRFronfAQl4VbvOblRCo7kxs2RvrzXwMBuNjMQyDGm1aYf2hGh11",
)
# https://docs.djangoproject.com/en/dev/ref/settings/#allowed-hosts
ALLOWED_HOSTS = ["localhost", "0.0.0.0", "127.0.0.1", ".localhost", "django", ".django"]  # noqa: S104

# CACHES
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#caches
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "",
    },
}

# EMAIL
# ------------------------------------------------------------------------------
# https://docs.djangoproject.com/en/dev/ref/settings/#email-host
EMAIL_HOST = env("EMAIL_HOST", default="mailpit")
# https://docs.djangoproject.com/en/dev/ref/settings/#email-port
EMAIL_PORT = 1025

# WhiteNoise
# ------------------------------------------------------------------------------
# http://whitenoise.evans.io/en/latest/django.html#using-whitenoise-in-development
INSTALLED_APPS = ["whitenoise.runserver_nostatic", *INSTALLED_APPS]


# django-debug-toolbar
# ------------------------------------------------------------------------------
# https://django-debug-toolbar.readthedocs.io/en/latest/installation.html#prerequisites
INSTALLED_APPS += ["debug_toolbar"]
# https://django-debug-toolbar.readthedocs.io/en/latest/installation.html#middleware
MIDDLEWARE += ["debug_toolbar.middleware.DebugToolbarMiddleware"]
# https://django-debug-toolbar.readthedocs.io/en/latest/configuration.html#debug-toolbar-config
DEBUG_TOOLBAR_CONFIG = {
    "DISABLE_PANELS": [
        # "debug_toolbar.panels.redirects.RedirectsPanel",
        "debug_toolbar.panels.profiling.HistoryPanel",
        # Disable profiling panel due to an issue with Python 3.12+:
        # https://github.com/jazzband/django-debug-toolbar/issues/1875
        "debug_toolbar.panels.profiling.ProfilingPanel",
    ],
    "SHOW_TEMPLATE_CONTEXT": True,
}
# https://django-debug-toolbar.readthedocs.io/en/latest/installation.html#internal-ips
INTERNAL_IPS = ["127.0.0.1", "10.0.2.2"]
if env("USE_DOCKER") == "yes":
    import socket

    hostname, _, ips = socket.gethostbyname_ex(socket.gethostname())
    INTERNAL_IPS += [".".join([*ip.split(".")[:-1], "1"]) for ip in ips]

# django-extensions
# ------------------------------------------------------------------------------
# https://django-extensions.readthedocs.io/en/latest/installation_instructions.html#configuration
INSTALLED_APPS += ["django_extensions"]

# Django Control Room
# ------------------------------------------------------------------------------
DJ_CONTROL_ROOM_SETTINGS = {
    **DJ_CONTROL_ROOM_SETTINGS,
    "REGISTER_PANELS_IN_ADMIN": env.bool("CR_REGISTER_PANELS", default=True),
    "PANEL_ADMIN_REGISTRATION": {
        "dj_redis_panel": env.bool("CR_REGISTER_REDIS_PANEL", default=True),
        "dj_cache_panel": env.bool("CR_REGISTER_CACHE_PANEL", default=True),
        "dj_urls_panel": env.bool("CR_REGISTER_URLS_PANEL", default=True),
        "dj_signals_panel": env.bool("CR_REGISTER_SIGNALS_PANEL", default=True),
        "dj_celery_panel": env.bool("CR_REGISTER_CELERY_PANEL", default=True),
    },
}
REDIS_URL = env.str("REDIS_URL", default="redis://redis:6379/0") 
redis_url = urlparse(url=REDIS_URL) 
DJ_REDIS_PANEL_SETTINGS = {
     "ALLOW_KEY_DELETE": False, 
     "ALLOW_KEY_EDIT": False, 
     "ALLOW_TTL_UPDATE": False, 
     "CURSOR_PAGINATED_SCAN": False, 
     "CURSOR_PAGINATED_COLLECTIONS": False, 
     "socket_timeout": 5.0, 
     "socket_connect_timeout": 5.0, 
     "INSTANCES": { 
         "local_redis": { 
             "description": "Local Redis Instance", 
             "host": redis_url.hostname or "redis", 
             "port": redis_url.port or 6379, 
             "features": { 
                 "ALLOW_KEY_DELETE": True, 
                 "ALLOW_KEY_EDIT": True, 
                 "ALLOW_TTL_UPDATE": True, 
                 "CURSOR_PAGINATED_SCAN": True, 
                 "CURSOR_PAGINATED_COLLECTIONS": True, 
            }, 
        }, 
    }, 
}

# Celery
# ------------------------------------------------------------------------------

# https://docs.celeryq.dev/en/stable/userguide/configuration.html#task-eager-propagates
CELERY_TASK_EAGER_PROPAGATES = True

# Adding local file storage for development
# STORAGES = {
#     "default": {
#         "BACKEND": "django.core.files.storage.FileSystemStorage",
#     },
#     "staticfiles": {
#         "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage",
#     },
# }

# logging
# ------------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,

    "formatters": {
        "verbose": {
            "format": (
                "{asctime} {levelname} "
                "{name} {message}"
            ),
            "style": "{",
        },
    },

    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },

    "loggers": {
        "saas.billing": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
        "tenant_users": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
        "django.request": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}

# AWS
# ------------------------------------------------------------------------------
AWS_ACCESS_KEY_ID = env.str("DJANGO_AWS_ACCESS_KEY_ID", default="test")
AWS_SECRET_ACCESS_KEY = env.str("DJANGO_AWS_SECRET_ACCESS_KEY", default="test")
AWS_SESSION_TOKEN = env.str("AWS_SESSION_TOKEN", default="")
AWS_REGION = env.str("DJANGO_AWS_S3_REGION_NAME", default="us-east-1")
AWS_ENDPOINT_URL = env.str("AWS_ENDPOINT_URL", default="http://floci:4566")
AWS_STORAGE_BUCKET_NAME = env.str("DJANGO_AWS_STORAGE_BUCKET_NAME", default="django-template-media")
AWS_S3_REGION_NAME = AWS_REGION
AWS_QUERYSTRING_AUTH = False
AWS_S3_MAX_MEMORY_SIZE = env.int("DJANGO_AWS_S3_MAX_MEMORY_SIZE", default=100_000_000)
AWS_S3_CUSTOM_DOMAIN = env.str("DJANGO_AWS_S3_CUSTOM_DOMAIN", default="")
AWS_S3_ADDRESSING_STYLE = "path"
AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "max-age=604800, s-maxage=604800, must-revalidate"}
AWS_S3_LOCATION = env.str("DJANGO_AWS_S3_LOCATION", default="media")
AWS_AVATAR_LAMBDA_FUNCTION_NAME = env.str("AWS_AVATAR_LAMBDA_FUNCTION_NAME", default="django-template-avatar-processor")

STORAGES = {
    "default": {
        "BACKEND": "storages.backends.s3.S3Storage",
        "OPTIONS": {
            "location": AWS_S3_LOCATION,
            "file_overwrite": False,
            "endpoint_url": AWS_ENDPOINT_URL,
            "bucket_name": AWS_STORAGE_BUCKET_NAME,
            "region_name": AWS_REGION,
            "addressing_style": AWS_S3_ADDRESSING_STYLE,
        },
    },
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}
UNFOLD = {
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": False,
        "navigation": get_navigation,
    },
}