"""
Publisher — Models
==================
Handles the creation, scheduling, and lifecycle of social media posts.
These models reside in the tenant schema.
"""
import uuid
from django.db import models
from django.conf import settings
from apps.organizations.models import Organization


class Post(models.Model):
    """
    Represents a single social media post (or thread) intended for one or
    more social accounts.
    """

    class Status(models.TextChoices):
        TEMP = "template", "Template"
        DRAFT = "draft", "Draft"
        SCHEDULED = "scheduled", "Scheduled"
        PUBLISHING = "publishing", "Publishing"
        PUBLISHED = "published", "Published"
        FAILED = "failed", "Failed"

    class Posted_on(models.TextChoices):
        FACEBOOK = "facebook", "Facebook"
        TWITTER = "twitter", "Twitter"
        INSTAGRAM = "instagram", "Instagram"
        LINKEDIN = "linkedin", "LinkedIn"
        TIKTOK = "tiktok", "TikTok"
        YOUTUBE = "youtube", "YouTube"
        PINTEREST = "pinterest", "Pinterest"
        REDDIT = "reddit", "Reddit"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="posts",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="authored_posts",
    )

    # Content
    content = models.TextField(blank=True)
    media_attachments = models.JSONField(default=list, help_text="List of S3 URLs or IDs")

    # Scheduling
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )

    posted_on = models.CharField(
        max_length=20,
        choices=Posted_on.choices,
        default=Posted_on.FACEBOOK,
    )
    scheduled_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)

    # Metadata
    platform_ids = models.JSONField(
        default=dict,
        help_text="Mapping of account_id -> remote_post_id after publication",
    )
    error_log = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "posts"
        ordering = ["-scheduled_at", "-created_at"]
        indexes = [
            models.Index(fields=["organization", "status"]),
            models.Index(fields=["scheduled_at"]),
        ]

    def __str__(self) -> str:
        return f"Post {self.id} ({self.status})"
