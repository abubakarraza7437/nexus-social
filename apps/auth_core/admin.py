from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "email",
        "full_name",
        "is_active",
        "is_staff",
        "mfa_enabled",
        "date_joined",
    )
    list_filter = ("is_active", "is_staff", "is_email_verified", "mfa_enabled")
    search_fields = ("email", "full_name")
    ordering = ("-date_joined",)
    readonly_fields = ("id", "date_joined", "last_login_at")

    fieldsets = (
        (None, {"fields": ("id", "email", "password")}),
        (
            _("Personal info"),
            {"fields": ("full_name", "avatar_url", "timezone", "locale")},
        ),
        (
            _("Status"),
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "is_email_verified",
                )
            },
        ),
        (_("MFA"), {"fields": ("mfa_enabled", "mfa_secret")}),
        (_("Permissions"), {"fields": ("groups", "user_permissions")}),
        (_("Timestamps"), {"fields": ("date_joined", "last_login_at")}),
    )

    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "full_name", "password1", "password2"),
            },
        ),
    )
