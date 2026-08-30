# admin_sidebar.py

from django.urls import reverse
from django.utils.translation import gettext_lazy as _

def admin_url(app_label, model_name):
    return reverse(
        f"admin:{app_label}_{model_name}_changelist"
    )


# =============================================================================
# PUBLIC ADMIN
# =============================================================================

def get_public_navigation(request):
    return [
        {
            "title": _("Tenants"),
            "icon": "business",
            "collapsible": True,
            "separator": True,
            "items": [
                {
                    "title": _("All Tenants"),
                    "icon": "domain",
                    "link": admin_url("tenants", "tenant"),
                },
                {
                    "title": _("Domains"),
                    "icon": "language",
                    "link": admin_url("tenants", "domain"),
                },
            ],
        },
        {
            "title": _("Users"),
            "icon": "people",
            "collapsible": True,
            "separator": True,
            "items": [
                {
                    "title": _("All Users"),
                    "icon": "person",
                    "link": admin_url("users", "user"),
                },
                {
                    "title": _("Groups"),
                    "icon": "groups",
                    "link": reverse(
                        "admin:auth_group_changelist"
                    ),
                },
            ],
        },
        {
            "title": _("Billing"),
            "icon": "payments",
            "collapsible": True,
            "separator": True,
            "items": [
                {
                    "title": _("Prices"),
                    "icon": "card_membership",
                    "link": admin_url("billing", "price"),
                },
                {
                    "title": _("Subscriptions"),
                    "icon": "receipt_long",
                    "link": admin_url("billing", "subscription"),
                },
            ],
        },
    ]


# =============================================================================
# TENANT ADMIN
# =============================================================================

def get_tenant_navigation(request):
    return [
        {
            "title": _("Organization"),
            "icon": "business",
            "collapsible": True,
            "separator": True,
            "items": [
                {
                    "title": _("Users"),
                    "icon": "person",
                    "badge": "users.utils.total_users_count()",
                    "link": admin_url("users", "user"),
                },
            ],
        },
    ]


# =============================================================================
# SELECT SIDEBAR
# =============================================================================

def get_navigation(request):
    if request.tenant.schema_name == "public":
        return get_public_navigation(request)

    return get_tenant_navigation(request)