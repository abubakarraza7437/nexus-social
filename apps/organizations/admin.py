from django.contrib import admin

from .models import Organization, OrganizationMember


class OrganizationMemberInline(admin.TabularInline):
    model = OrganizationMember
    extra = 0
    readonly_fields = ("id", "created_at")
    fields = ("user", "role", "is_active", "invited_by", "created_at")


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "plan", "is_active", "created_at")
    list_filter = ("plan", "is_active")
    search_fields = ("name", "slug", "billing_customer_id")
    readonly_fields = ("id", "created_at", "updated_at")
    inlines = [OrganizationMemberInline]


@admin.register(OrganizationMember)
class OrganizationMemberAdmin(admin.ModelAdmin):
    list_display = ("user", "organization", "role", "is_active", "created_at")
    list_filter = ("role", "is_active")
    search_fields = ("user__email", "organization__name")
    readonly_fields = ("id", "created_at")
