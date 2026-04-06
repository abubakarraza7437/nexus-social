# Celery app is NOT imported here to avoid a nested django.setup() race:
# socialos/__init__.py is imported during Django's Settings() constructor
# (to resolve the socialos.settings.development package path), so any
# django.setup() call inside celery.py would fire before _wrapped is set,
# and the outer Settings() would then replace it — wiping out dynamically-set
# defaults (e.g. django-axes).  Instead, wsgi.py / asgi.py import celery
# explicitly after get_wsgi/asgi_application() finishes Django setup.
