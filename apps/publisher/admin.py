"""
Publisher — Admin Configuration
===============================
Registers Post and Schedule models for the Django admin interface.
"""
from django.contrib import admin
from apps.publisher.models import Post


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("id", "organization", "author", "status", "posted_on", "scheduled_at", "published_at", "created_at")
    list_filter = ("status", "organization", "created_at", "scheduled_at")
    search_fields = ("id", "content", "organization__name", "author__email")
    readonly_fields = ("id", "created_at", "updated_at", "platform_ids")
    ordering = ("-created_at",)
    fieldsets = (
        ("Core Information", {
            "fields": ("id", "organization", "author", "status")
        }),
        ("Content", {
            "fields": ("content", "media_attachments")
        }),
        ("Scheduling & Publication", {
            "fields": ("scheduled_at", "published_at")
        }),
        ("Metadata & Logs", {
            "fields": ("platform_ids", "error_log", "created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
