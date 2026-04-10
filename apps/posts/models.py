import uuid
from django.db import models, transaction
from django.conf import settings
from django.utils import timezone
from apps.organizations.models import Organization
from apps.posts.schemas import PostTargetErrorPayload


class Post(models.Model):

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

    def sync_status(self) -> None:
        """
        Recompute and persist Post.status from its targets' statuses.

        Uses select_for_update() on the Post row to prevent concurrent
        mark_published()/mark_failed() calls from producing a stale read
        and overwriting each other's result.
        """
        with transaction.atomic():
            # Lock this Post row for the duration of the status computation.
            post = Post.objects.select_for_update().get(pk=self.pk)
            targets = list(post.targets.values_list("status", flat=True))
            if not targets:
                return

            s = PostTarget.Status
            if s.PUBLISHING in targets:
                new_status = self.Status.PUBLISHING
                new_published_at = post.published_at
            elif all(t == s.PUBLISHED for t in targets):
                new_status = self.Status.PUBLISHED
                new_published_at = post.published_at or timezone.now()
            elif s.FAILED in targets:
                new_status = self.Status.FAILED
                new_published_at = post.published_at
            elif s.SCHEDULED in targets:
                new_status = self.Status.SCHEDULED
                new_published_at = post.published_at
            else:
                new_status = self.Status.DRAFT
                new_published_at = post.published_at

            post.status = new_status
            post.published_at = new_published_at
            post.save(update_fields=["status", "published_at", "updated_at"])

        # Reflect the persisted values onto self so callers see the updated state.
        self.status = post.status
        self.published_at = post.published_at


class PostTarget(models.Model):

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
