from django.contrib import admin

from .models import JoinRequest, Organization, OrganizationMember


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


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "plan", "is_active", "created_at")
    list_filter = ("plan", "is_active")
    search_fields = ("name", "slug", "billing_customer_id")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = [OrganizationMemberInline, JoinRequestInline]


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
