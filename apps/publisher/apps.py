from django.apps import AppConfig


class PublisherConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.publisher"
    label = "publisher"
    verbose_name = "Publisher"
