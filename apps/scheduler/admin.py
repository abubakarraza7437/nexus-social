"""
Scheduler — Admin Configuration
===============================
Registers RecurringSchedule model for the Django admin interface.
"""
from django.contrib import admin

from apps.scheduler.models import RecurringSchedule


@admin.register(RecurringSchedule)
class RecurringScheduleAdmin(admin.ModelAdmin):
    """Admin configuration for RecurringSchedule model."""

    list_display = (
        "title",
        "organization",
        "cron_expression",
        "timezone",
        "is_active",
        "next_run_at",
        "last_run_at",
        "run_count",
        "created_at",
    )
    list_filter = ("is_active", "timezone", "created_at", "organization")
    search_fields = (
        "title",
        "description",
        "organization__name",
        "organization__slug",
        "created_by__email",
        "cron_expression",
    )
    readonly_fields = (
        "id",
        "run_count",
        "last_run_at",
        "next_run_at",
        "created_at",
        "updated_at",
        "is_exhausted_display",
    )
    raw_id_fields = ("organization", "created_by")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"

    fieldsets = (
        ("Identity", {
            "fields": ("id", "organization", "created_by", "title", "description")
        }),
        ("Schedule Definition", {
            "fields": ("cron_expression", "timezone")
        }),
        ("Execution State", {
            "fields": ("is_active", "next_run_at", "last_run_at", "run_count", "is_exhausted_display")
        }),
        ("Stop Conditions", {
            "fields": ("end_at", "max_runs"),
            "classes": ("collapse",)
        }),
        ("Timestamps", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )

    @admin.display(boolean=True, description="Exhausted")
    def is_exhausted_display(self, obj):
        return obj.is_exhausted

    actions = ["activate_schedules", "deactivate_schedules", "refresh_next_run"]

    @admin.action(description="Activate selected schedules")
    def activate_schedules(self, request, queryset):
        """Admin action to activate schedules."""
        updated = queryset.filter(is_active=False).update(is_active=True)
        # Refresh next_run_at for newly activated schedules
        for schedule in queryset.filter(is_active=True, next_run_at__isnull=True):
            schedule.refresh_next_run()
        self.message_user(
            request,
            f"Activated {updated} schedule(s).",
        )

    @admin.action(description="Deactivate selected schedules")
    def deactivate_schedules(self, request, queryset):
        """Admin action to deactivate schedules."""
        count = 0
        for schedule in queryset.filter(is_active=True):
            schedule.deactivate()
            count += 1
        self.message_user(
            request,
            f"Deactivated {count} schedule(s).",
        )

    @admin.action(description="Refresh next run time")
    def refresh_next_run(self, request, queryset):
        """Admin action to refresh next_run_at for selected schedules."""
        count = 0
        for schedule in queryset.filter(is_active=True):
            schedule.refresh_next_run()
            count += 1
        self.message_user(
            request,
            f"Refreshed next run time for {count} schedule(s).",
        )
