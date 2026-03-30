from django.apps import AppConfig


class AuthCoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.auth_core"
    label = "auth_core"
    verbose_name = "Authentication & Authorization"

    def ready(self) -> None:
        # Register signal handlers
        import apps.auth_core.signals  # noqa: F401
