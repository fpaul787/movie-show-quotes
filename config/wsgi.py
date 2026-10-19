import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
os.environ.setdefault("APP_ENV", "prod")

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()