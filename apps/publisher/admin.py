"""
Publisher — Admin Configuration
===============================
Registers PublishJob model for the Django admin interface.
"""
from django.contrib import admin

from apps.publisher.models import PublishJob


@admin.register(PublishJob)
class PublishJobAdmin(admin.ModelAdmin):
    """Admin configuration for PublishJob model."""

    list_display = (
        "id",
        "org",
        "target",
        "task_name",
        "status",
        "attempt_number",
        "max_attempts",
        "created_at",
        "completed_at",
    )
    list_filter = ("status", "task_name", "created_at", "completed_at")
    search_fields = (
        "id",
        "celery_task_id",
        "org__name",
        "org__slug",
        "target__id",
        "target__post__id",
    )
    readonly_fields = (
        "id",
        "celery_task_id",
        "created_at",
        "updated_at",
        "started_at",
        "completed_at",
        "duration_display",
    )
    raw_id_fields = ("org", "target")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"

    fieldsets = (
        ("Job Identity", {
            "fields": ("id", "org", "target", "task_name", "celery_task_id")
        }),
        ("Status & Attempts", {
            "fields": ("status", "attempt_number", "max_attempts", "retry_at")
        }),
        ("Result & Error", {
            "fields": ("result", "error"),
            "classes": ("collapse",)
        }),
        ("Timestamps", {
            "fields": ("created_at", "started_at", "completed_at", "updated_at", "duration_display"),
            "classes": ("collapse",)
        }),
    )

    @admin.display(description="Duration (seconds)")
    def duration_display(self, obj):
        duration = obj.duration_seconds
        if duration is not None:
            return f"{duration:.2f}s"
        return "-"

    actions = ["mark_as_failed"]

    @admin.action(description="Mark selected jobs as failed")
    def mark_as_failed(self, request, queryset):
        """Admin action to manually mark jobs as failed."""
        updated = queryset.filter(
            status__in=[PublishJob.Status.PENDING, PublishJob.Status.RUNNING]
        ).update(status=PublishJob.Status.FAILED)
        self.message_user(
            request,
            f"Marked {updated} job(s) as failed.",
        )
