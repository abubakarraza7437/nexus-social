"""
Posts · Models
==============
Handles the creation, scheduling, and lifecycle of social media posts.
These models reside in the tenant schema.

Key design decisions
--------------------
* Post is a scheduling unit only — all content lives in the content app.
* A Post links to a Content object (FK); content is shared across posts.
* Multi-platform delivery is handled by PostTarget, one row per platform.
* Per-platform content overrides are stored on PostTarget (optional).
* Post.status reflects the aggregate state; each PostTarget carries its own.
"""

import uuid
from django.db import models
from django.conf import settings
from django.utils import timezone
from apps.organizations.models import Organization
from apps.posts.schemas import PostTargetErrorPayload


# TODO: Uncomment once the Content model is implemented in apps/content/models.py
# from apps.content.models import Content


class Post(models.Model):
    """
    A scheduling wrapper around a piece of Content.

    One Post → one Content (shared).
    One Post → many PostTargets (one per platform/account).
    """

    class Status(models.TextChoices):
        TEMPLATE = "template", "Template"
        DRAFT = "draft", "Draft"
        SCHEDULED = "scheduled", "Scheduled"
        PUBLISHING = "publishing", "Publishing"
        PUBLISHED = "published", "Published"
        FAILED = "failed", "Failed"

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
        blank=True,
        related_name="authored_posts",
    )

    # ------------------------------------------------------------------ #
    # Content reference                                                   #
    # TODO: Uncomment this FK once apps/content/models.py has a Content  #
    #       model defined. Content holds the actual text + media.        #
    # ------------------------------------------------------------------ #
    # content = models.ForeignKey(
    #     Content,
    #     on_delete=models.PROTECT,
    #     related_name="posts",
    #     help_text="Shared content block (text + media). One content can back many posts.",
    # )

    # ------------------------------------------------------------------ #
    # Scheduling                                                          #
    # ------------------------------------------------------------------ #
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        db_index=True,
    )
    scheduled_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Set when ALL targets have published successfully.",
    )

    # ------------------------------------------------------------------ #
    # Metadata                                                            #
    # ------------------------------------------------------------------ #
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "posts"
        ordering = ["-scheduled_at", "-created_at"]
        indexes = [
            models.Index(fields=["organization", "status"], name="posts_org_status_idx"),
            models.Index(fields=["organization", "scheduled_at", "status"], name="posts_org_scheduled_status_idx"),
            models.Index(fields=["author"], name="posts_author_idx"),
            models.Index(fields=["scheduled_at"], name="posts_scheduled_at_idx"),
        ]

    def __str__(self) -> str:
        return f"Post {self.id} [{self.status}]"

    # ------------------------------------------------------------------ #
    # Helpers                                                             #
    # ------------------------------------------------------------------ #
    def sync_status(self) -> None:
        """
        Recompute and save Post.status from its PostTargets.

        Call this after any PostTarget status change.

        Rules (in priority order):
          1. Any target still publishing  → PUBLISHING
          2. All targets published        → PUBLISHED  (sets published_at)
          3. Any target failed            → FAILED
          4. Any target scheduled         → SCHEDULED
          5. Fallback                     → DRAFT
        """
        targets = list(self.targets.values_list("status", flat=True))
        if not targets:
            return

        s = PostTarget.Status
        if s.PUBLISHING in targets:
            self.status = self.Status.PUBLISHING
        elif all(t == s.PUBLISHED for t in targets):
            self.status = self.Status.PUBLISHED
            if not self.published_at:
                self.published_at = timezone.now()
        elif s.FAILED in targets:
            self.status = self.Status.FAILED
        elif s.SCHEDULED in targets:
            self.status = self.Status.SCHEDULED
        else:
            self.status = self.Status.DRAFT

        self.save(update_fields=["status", "published_at", "updated_at"])


class PostTarget(models.Model):
    """
    One delivery slot: a Post going out on a specific platform/account.

    Status and error tracking live here so each platform can succeed or
    fail independently.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SCHEDULED = "scheduled", "Scheduled"
        PUBLISHING = "publishing", "Publishing"
        PUBLISHED = "published", "Published"
        FAILED = "failed", "Failed"

    class Platform(models.TextChoices):
        FACEBOOK = "facebook", "Facebook"
        TWITTER = "twitter", "Twitter"
        INSTAGRAM = "instagram", "Instagram"
        LINKEDIN = "linkedin", "LinkedIn"
        TIKTOK = "tiktok", "TikTok"
        YOUTUBE = "youtube", "YouTube"
        PINTEREST = "pinterest", "Pinterest"
        REDDIT = "reddit", "Reddit"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="targets",
    )

    # ------------------------------------------------------------------ #
    # Platform identity                                                   #
    # ------------------------------------------------------------------ #
    platform = models.CharField(max_length=20, choices=Platform.choices)

    # TODO: Replace with a FK to SocialAccount once that model exists.   #
    #       A bare CharField has no referential integrity — you can       #
    #       target a deleted or non-existent account without any error.  #
    # account_id = models.CharField(
    #     max_length=255,
    #     help_text="Internal ID of the connected social account to publish from.",
    # )

    # ------------------------------------------------------------------ #
    # Per-platform content override (optional)                           #
    # TODO: Uncomment once Content model is available in                 #
    #       apps/content/models.py. Falls back to post.content when null.#
    # ------------------------------------------------------------------ #
    # content_override = models.ForeignKey(
    #     Content,
    #     on_delete=models.SET_NULL,
    #     null=True,
    #     blank=True,
    #     related_name="post_target_overrides",
    #     help_text="Platform-specific content. If blank, post.content is used.",
    # )

    # ------------------------------------------------------------------ #
    # Delivery state                                                      #
    # ------------------------------------------------------------------ #
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
    )
    remote_post_id = models.CharField(
        max_length=255,
        blank=True,
        help_text="ID returned by the platform API after publish.",
    )
    published_at = models.DateTimeField(null=True, blank=True)

    # Structured error — queryable, not a plain text blob
    error = models.JSONField(
        default=dict,
        blank=True,
        help_text='e.g. {"code": "RATE_LIMITED", "message": "...", "at": "2024-01-01T00:00Z"}',
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "post_targets"
        # TODO: Restore unique_together once account_id FK is uncommented.
        # unique_together = [("post", "account_id")]
        indexes = [
            models.Index(fields=["post", "status"], name="post_targets_post_status_idx"),
            models.Index(fields=["platform", "status"], name="pt_platform_status_idx"),
        ]

    def __str__(self) -> str:
        return f"PostTarget {self.id} — {self.platform} [{self.status}]"

    def mark_published(self, remote_post_id: str) -> None:
        """Convenience: mark this target published and propagate to Post."""
        self.status = self.Status.PUBLISHED
        self.remote_post_id = remote_post_id
        self.published_at = timezone.now()
        self.error = {}
        self.save(update_fields=["status", "remote_post_id", "published_at", "error", "updated_at"])
        self.post.sync_status()

    def mark_failed(self, code: str, message: str) -> None:
        """Convenience: record a structured error and propagate to Post."""
        self.status = self.Status.FAILED
        self.error = PostTargetErrorPayload(
            code=code,
            message=message,
            at=timezone.now(),
        ).model_dump(mode="json")
        self.save(update_fields=["status", "error", "updated_at"])
        self.post.sync_status()
