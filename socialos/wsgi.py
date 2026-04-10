import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "socialos.settings.production")

application = get_wsgi_application()

# Import the Celery app after Django is fully set up so that @shared_task tasks
# can be dispatched from Django views with the correct broker configuration.
import socialos.celery  # noqa: F401, E402
