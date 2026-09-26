from .base import *

DEBUG = True

# SQLite Fallback for initial local testing if PostgreSQL is not active
if os.environ.get('USE_SQLITE', 'False') == 'True':
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.sqlite3',
            'NAME': BASE_DIR / 'db.sqlite3',
        }
    }

# Automatically allow all hosts and ngrok tunnels in local development
ALLOWED_HOSTS = ['*']

CSRF_TRUSTED_ORIGINS += [
    'https://*.ngrok-free.app',
    'https://*.ngrok-free.dev',
    'https://*.ngrok.io',
]
