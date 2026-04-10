# This file is intentionally empty.
# Multi-tenancy is handled by django_tenants.middleware.main.TenantMainMiddleware,
# which is the first entry in MIDDLEWARE in socialos/settings/base.py.
# Schema switching in background tasks uses schema_context() from django_tenants.utils.
