from rest_framework.permissions import BasePermission

DOMAIN_PERMISSIONS = {
    "create": "tenants.add_domain",
    "update": "tenants.change_domain",
    "partial_update": "tenants.change_domain",
    "destroy": "tenants.delete_domain",
}


class TenantDomainPermission(BasePermission):
    def has_permission(self, request, view) -> bool:
        if not request.user.is_authenticated:
            return False

        tenant = request.tenant

        # Tenant owner has full access.
        if tenant.owner_id == request.user.id:
            return True

        permission = DOMAIN_PERMISSIONS.get(view.action)

        if permission is None:
            return False

        return request.user.has_perm(permission, tenant)