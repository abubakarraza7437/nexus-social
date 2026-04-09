from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import EmailVerificationToken, PasswordResetToken, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("email", "name", "is_active", "is_staff", "mfa_enabled", "date_joined")
    list_filter = ("is_active", "is_staff", "is_verified", "mfa_enabled")
    search_fields = ("email", "name")
    ordering = ("-date_joined",)
    readonly_fields = ("id", "date_joined", "last_login_at")

    fieldsets = (
        (None, {"fields": ("id", "email", "password")}),
        (_("Personal info"), {"fields": ("name", "avatar_url", "timezone", "locale")}),
        (_("Status"), {"fields": ("is_active", "is_staff", "is_superuser", "is_verified")}),
        (_("MFA"), {"fields": ("mfa_enabled", "mfa_secret")}),
        (_("Permissions"), {"fields": ("groups", "user_permissions")}),
        (_("Timestamps"), {"fields": ("date_joined", "last_login_at")}),
    )

    add_fieldsets = (
        (None, {
            "classes": ("wide",),
            "fields": ("email", "name", "password1", "password2"),
        }),
    )


@admin.register(EmailVerificationToken)
class EmailVerificationTokenAdmin(admin.ModelAdmin):
    """Admin configuration for EmailVerificationToken model."""

    list_display = ("id", "user", "is_used", "created_at", "expires_at", "is_valid_display")
    list_filter = ("is_used", "created_at", "expires_at")
    search_fields = ("user__email", "token")
    readonly_fields = ("id", "token", "created_at")
    ordering = ("-created_at",)
    raw_id_fields = ("user",)
    date_hierarchy = "created_at"

    fieldsets = (
        (_("Token Information"), {
            "fields": ("id", "user", "token")
        }),
        (_("Status"), {
            "fields": ("is_used", "expires_at")
        }),
        (_("Timestamps"), {
            "fields": ("created_at",),
            "classes": ("collapse",)
        }),
    )

    @admin.display(boolean=True, description="Valid")
    def is_valid_display(self, obj):
        return obj.is_valid


@admin.register(PasswordResetToken)
class PasswordResetTokenAdmin(admin.ModelAdmin):
    """Admin configuration for PasswordResetToken model."""

    list_display = ("id", "user", "is_used", "created_at", "expires_at", "is_valid_display")
    list_filter = ("is_used", "created_at", "expires_at")
    search_fields = ("user__email", "token")
    readonly_fields = ("id", "token", "created_at")
    ordering = ("-created_at",)
    raw_id_fields = ("user",)
    date_hierarchy = "created_at"

    fieldsets = (
        (_("Token Information"), {
            "fields": ("id", "user", "token")
        }),
        (_("Status"), {
            "fields": ("is_used", "expires_at")
        }),
        (_("Timestamps"), {
            "fields": ("created_at",),
            "classes": ("collapse",)
        }),
    )

    @admin.display(boolean=True, description="Valid")
    def is_valid_display(self, obj):
        return obj.is_valid
