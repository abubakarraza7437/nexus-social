from django.contrib import admin
from apps.posts.models import Post, PostTarget


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("id", "organization", "author", "status", "scheduled_at", "published_at", "created_at")
    list_filter = ("status", "organization", "created_at", "scheduled_at")
    search_fields = ("id", "organization__name", "author__email")
    readonly_fields = ("id", "created_at", "updated_at")
    ordering = ("-created_at",)
    fieldsets = (
        ("Core Information", {
            "fields": ("id", "organization", "author", "status")
        }),
        ("Scheduling & Publication", {
            "fields": ("scheduled_at", "published_at")
        }),
        ("Metadata", {
            "fields": ("created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )


@admin.register(PostTarget)
class PostTargetAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "platform", "status", "published_at", "created_at")
    list_filter = ("status", "platform")
    search_fields = ("id", "post__id", "remote_post_id")
    readonly_fields = ("id", "created_at", "updated_at")
    ordering = ("-created_at",)
    fieldsets = (
        ("Core Information", {
            "fields": ("id", "post", "platform", "status")
        }),
        ("Delivery", {
            "fields": ("remote_post_id", "published_at")
        }),
        ("Error & Metadata", {
            "fields": ("error", "created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )
