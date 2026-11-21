from .settings import *

DEBUG = False
SECRET_KEY = '8leQWRGQzVVrg6LU9FbMArMpzUKzRs5A3xTmbLkZgtRJs1W8a8G48E2rHNdt-tVuTMV7yHaGZVR6YQN8'
ALLOWED_HOSTS = ['sachmehfar.ir', 'www.sachmehfar.ir', '95.38.234.89']
CSRF_TRUSTED_ORIGINS = ['https://sachmehfar.ir', 'https://www.sachmehfar.ir']
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'handlers': {'console': {'class': 'logging.StreamHandler'}},
    'loggers': {
        'django.request': {'handlers': ['console'], 'level': 'ERROR', 'propagate': False},
    },
    'root': {'handlers': ['console'], 'level': 'WARNING'},
}
