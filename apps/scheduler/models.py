import uuid
import zoneinfo
from datetime import datetime as _dt

from croniter import croniter
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.organizations.models import Organization


def validate_cron_expression(value: str) -> None:
    """Reject any expression croniter cannot parse."""
    if not croniter.is_valid(value):
        raise ValidationError(
            f" '{value}' is not a valid cron expression. "
            "Expected 5 fields: minute hour day-of-month month day-of-week. "
            "Example: '0 9 * * 1' (every Monday at 09:00).")


def validate_timezone(value: str) -> None:
    """Reject timezone strings that zoneinfo cannot resolve."""
    try:
        zoneinfo.ZoneInfo(value)
    except (zoneinfo.ZoneInfoNotFoundError, KeyError):
        raise ValidationError(
            f"'{value}' is not a recognised IANA timezone. "
            "Use a name from the IANA timezone database, e.g. 'America/New_York'."
        )


class RecurringSchedule(models.Model):

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Tenant ownership
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="recurring_schedules",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_recurring_schedules",
        help_text=(
            "User who created this schedule. Nullable so the org is not "
            "affected if the user account is deleted."
        ),
    )

    # Identity
    title = models.CharField(
        max_length=255,
        help_text="Human-readable label, e.g. 'Monday morning motivational post'.",
    )
    description = models.TextField(
        blank=True,
        help_text="Optional notes about this schedule's purpose.",
    )

    # Schedule definition
    cron_expression = models.CharField(
        max_length=100,
        validators=[validate_cron_expression],
        help_text=(
            "Standard 5-field cron expression: minute hour day-of-month month day-of-week. "
            "Example: '0 9 * * 1' fires every Monday at 09:00 in the configured timezone."
        ),
    )
    timezone = models.CharField(
        max_length=100,
        default="UTC",
        validators=[validate_timezone],
        help_text="IANA timezone name for interpreting the cron expression, e.g. 'America/New_York'.",
    )

    # ----------------------------------------------------------------------- #
    # Post template reference                                                  #
    # TODO: Uncomment once the Post model is stable and Post.Status.TEMPLATE  #
    #       is queryable. The scheduler task will clone this template post     #
    #       each time the schedule fires.                                      #
    # ----------------------------------------------------------------------- #
    # post_template = models.ForeignKey(
    #     "posts.Post",
    #     on_delete=models.PROTECT,
    #     null=True,
    #     blank=True,
    #     related_name="recurring_schedules",
    #     limit_choices_to={"status": "template"},
    #     help_text="Post template to clone when this schedule fires.",
    # )

    # Execution state
    is_active = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Inactive schedules are skipped by the scheduler task.",
    )
    next_run_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Next UTC datetime when this schedule should fire. Set by refresh_next_run().",
    )
    last_run_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="UTC datetime of the most recent successful run.",
    )
    run_count = models.PositiveIntegerField(
        default=0,
        help_text="Total number of times this schedule has fired successfully.",
    )

    # Optional stop conditions
    end_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="If set, the schedule deactivates itself after this UTC datetime.",
    )
    max_runs = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="If set, the schedule deactivates itself after firing this many times total.",
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "recurring_schedules"
        indexes = [
            # Primary poll query: active schedules due to fire
            models.Index(
                fields=["organization", "is_active", "next_run_at"],
                name="rs_org_active_next_run_idx",
            ),
            # Per-org listing (admin / API)
            models.Index(
                fields=["organization", "created_at"],
                name="rs_org_created_at_idx",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.title} ({self.cron_expression} {self.timezone})"

    # Cron helpers

    def compute_next_run(self, after: _dt | None = None) -> _dt:

        after_utc = after or timezone.now()
        tz = zoneinfo.ZoneInfo(self.timezone)

        # Convert to local time and strip tzinfo — croniter works with
        # naive datetimes to avoid ambiguity around DST transitions.
        after_local_naive = after_utc.astimezone(tz).replace(tzinfo=None)

        cron = croniter(self.cron_expression, after_local_naive)
        next_local_naive: _dt = cron.get_next(_dt)

        # Re-attach the local timezone, then normalise to UTC.
        return next_local_naive.replace(tzinfo=tz).astimezone(zoneinfo.ZoneInfo("UTC"))

    def refresh_next_run(self, after: _dt | None = None) -> None:
        """Advance next_run_at to the next occurrence and persist."""
        self.next_run_at = self.compute_next_run(after=after)
        self.save(update_fields=["next_run_at", "updated_at"])

    # Stop-condition helpers

    @property
    def is_exhausted(self) -> bool:

        if self.end_at and timezone.now() >= self.end_at:
            return True
        if self.max_runs is not None and self.run_count >= self.max_runs:
            return True
        return False

    def deactivate(self) -> None:
        """Mark the schedule inactive and clear next_run_at."""
        self.is_active = False
        self.next_run_at = None
        self.save(update_fields=["is_active", "next_run_at", "updated_at"])
