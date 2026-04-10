import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("organizations", "0005_alter_joinrequest_options_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Post",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(
                    choices=[
                        ("template", "Template"),
                        ("draft", "Draft"),
                        ("scheduled", "Scheduled"),
                        ("publishing", "Publishing"),
                        ("published", "Published"),
                        ("failed", "Failed"),
                    ],
                    db_index=True,
                    default="draft",
                    max_length=20,
                )),
                ("scheduled_at", models.DateTimeField(blank=True, null=True)),
                ("published_at", models.DateTimeField(
                    blank=True,
                    help_text="Set when ALL targets have published successfully.",
                    null=True,
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("organization", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="posts",
                    to="organizations.organization",
                )),
                ("author", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="authored_posts",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "db_table": "posts",
                "ordering": ["-scheduled_at", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="PostTarget",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("platform", models.CharField(
                    choices=[
                        ("facebook", "Facebook"),
                        ("twitter", "Twitter"),
                        ("instagram", "Instagram"),
                        ("linkedin", "LinkedIn"),
                        ("tiktok", "TikTok"),
                        ("youtube", "YouTube"),
                        ("pinterest", "Pinterest"),
                        ("reddit", "Reddit"),
                    ],
                    max_length=20,
                )),
                ("status", models.CharField(
                    choices=[
                        ("draft", "Draft"),
                        ("scheduled", "Scheduled"),
                        ("publishing", "Publishing"),
                        ("published", "Published"),
                        ("failed", "Failed"),
                    ],
                    default="draft",
                    max_length=20,
                )),
                ("remote_post_id", models.CharField(
                    blank=True,
                    help_text="ID returned by the platform API after publish.",
                    max_length=255,
                )),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("error", models.JSONField(
                    blank=True,
                    default=dict,
                    help_text='e.g. {"code": "RATE_LIMITED", "message": "...", "at": "2024-01-01T00:00Z"}',
                )),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("post", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="targets",
                    to="posts.post",
                )),
            ],
            options={
                "db_table": "post_targets",
            },
        ),
        migrations.AddIndex(
            model_name="post",
            index=models.Index(fields=["organization", "status"], name="posts_org_status_idx"),
        ),
        migrations.AddIndex(
            model_name="post",
            index=models.Index(fields=["organization", "scheduled_at", "status"],
                               name="posts_org_scheduled_status_idx"),
        ),
        migrations.AddIndex(
            model_name="post",
            index=models.Index(fields=["author"], name="posts_author_idx"),
        ),
        migrations.AddIndex(
            model_name="post",
            index=models.Index(fields=["scheduled_at"], name="posts_scheduled_at_idx"),
        ),
        migrations.AddIndex(
            model_name="posttarget",
            index=models.Index(fields=["post", "status"], name="post_targets_post_status_idx"),
        ),
        migrations.AddIndex(
            model_name="posttarget",
            index=models.Index(fields=["platform", "status"], name="post_targets_platform_status_idx"),
        ),
    ]
