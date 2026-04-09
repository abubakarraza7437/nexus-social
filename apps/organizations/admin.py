from django.contrib import admin

from .models import Domain, JoinRequest, Organization, OrganizationInvitation, OrganizationMember


class OrganizationMemberInline(admin.TabularInline):
    model = OrganizationMember
    extra = 0
    readonly_fields = ("id", "created_at")
    fields = ("user", "role", "is_active", "invited_by", "created_at")


class JoinRequestInline(admin.TabularInline):
    model = JoinRequest
    extra = 0
    readonly_fields = ("id", "user", "status", "created_at", "reviewed_by", "reviewed_at")
    fields = ("user", "status", "message", "reviewed_by", "reviewed_at", "created_at")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class OrganizationInvitationInlineForOrg(admin.TabularInline):
    """Inline for viewing invitations within Organization admin."""
    model = OrganizationInvitation
    extra = 0
    readonly_fields = ("id", "token", "created_at", "expires_at", "is_used")
    fields = ("email", "role", "invited_by", "is_used", "expires_at", "created_at")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "plan", "is_active", "created_at")
    list_filter = ("plan", "is_active")
    search_fields = ("name", "slug", "billing_customer_id")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = [OrganizationMemberInline, JoinRequestInline, OrganizationInvitationInlineForOrg]


@admin.register(OrganizationMember)
class OrganizationMemberAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "is_active", "created_at")
    list_filter = ("role", "is_active")
    search_fields = ("user__email", "organization__name")
    readonly_fields = ("id", "created_at")


@admin.register(JoinRequest)
class JoinRequestAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "organization",
        "status",
        "created_at",
        "reviewed_by",
        "reviewed_at",
    )
    list_filter = ("status", "created_at")
    search_fields = ("user__email", "organization__name")
    readonly_fields = (
        "id",
        "user",
        "organization",
        "created_at",
        "updated_at",
        "expires_at",
    )
    raw_id_fields = ("user", "organization", "reviewed_by")
    date_hierarchy = "created_at"

    fieldsets = (
        (None, {
            "fields": ("id", "user", "organization", "status")
        }),
        ("Request Details", {
            "fields": ("message", "created_at", "expires_at")
        }),
        ("Review", {
            "fields": ("reviewed_by", "reviewed_at", "rejection_reason")
        }),
    )

    actions = ["approve_requests", "reject_requests"]

    @admin.action(description="Approve selected join requests")
    def approve_requests(self, request, queryset):
        from .services import approve_join_request

        approved_count = 0
        for join_request in queryset.filter(status=JoinRequest.Status.PENDING):
            try:
                approve_join_request(
                    join_request=join_request,
                    reviewer=request.user,
                )
                approved_count += 1
            except ValueError:
                pass

        self.message_user(
            request,
            f"Successfully approved {approved_count} join request(s).",
        )

    @admin.action(description="Reject selected join requests")
    def reject_requests(self, request, queryset):
        from .services import reject_join_request

        rejected_count = 0
        for join_request in queryset.filter(status=JoinRequest.Status.PENDING):
            try:
                reject_join_request(
                    join_request=join_request,
                    reviewer=request.user,
                    reason="Rejected via admin action",
                )
                rejected_count += 1
            except ValueError:
                pass

        self.message_user(
            request,
            f"Successfully rejected {rejected_count} join request(s).",
        )


@admin.register(Domain)
class DomainAdmin(admin.ModelAdmin):
    """Admin configuration for Domain model (django-tenants)."""

    list_display = ("domain", "tenant", "is_primary")
    list_filter = ("is_primary",)
    search_fields = ("domain", "tenant__name", "tenant__slug")
    raw_id_fields = ("tenant",)
    ordering = ("domain",)

    fieldsets = (
        (None, {
            "fields": ("domain", "tenant", "is_primary")
        }),
    )


@admin.register(OrganizationInvitation)
class OrganizationInvitationAdmin(admin.ModelAdmin):
    """Admin configuration for OrganizationInvitation model."""

    list_display = (
        "email",
        "organization",
        "role",
        "is_used",
        "invited_by",
        "created_at",
        "expires_at",
        "is_valid_display",
    )
    list_filter = ("role", "is_used", "created_at", "expires_at")
    search_fields = ("email", "organization__name", "organization__slug", "invited_by__email")
    readonly_fields = ("id", "token", "created_at")
    raw_id_fields = ("organization", "invited_by")
    ordering = ("-created_at",)
    date_hierarchy = "created_at"

    fieldsets = (
        (None, {
            "fields": ("id", "organization", "email", "role")
        }),
        ("Invitation Details", {
            "fields": ("token", "invited_by")
        }),
        ("Status", {
            "fields": ("is_used", "expires_at")
        }),
        ("Timestamps", {
            "fields": ("created_at",),
            "classes": ("collapse",)
        }),
    )

    @admin.display(boolean=True, description="Valid")
    def is_valid_display(self, obj):
        return obj.is_valid
