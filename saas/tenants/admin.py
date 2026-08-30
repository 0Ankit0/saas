from django.contrib import admin, messages
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_tenants.admin import TenantAdminMixin
from unfold.admin import ModelAdmin

from saas.tenants.forms import InvitationAdminForm
from saas.tenants.models import (
    Domain,
    Invitation,
    InvitationStatus,
    Tenant,
)
from saas.tenants.services import (
    create_invitation,
    queue_invitation_notification,
)


@admin.register(Tenant)
class TenantAdmin(TenantAdminMixin, ModelAdmin):
    list_display = [
        "name",
        "schema_name",
        "owner",
        "created",
        "modified",
    ]

    search_fields = [
        "name",
        "schema_name",
        "owner__email",
    ]

    fields = (
        "name",
        "schema_name",
        "owner",
    )

    def has_create_permission(self, request):
        if not request.tenant.schema_name == "public" and not request.user.is_superuser and not request.user.is_staff:
            return False
        return request.user.is_superuser or request.user.is_staff

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        if request.tenant.schema_name != "public":
            return qs.filter(pk=request.tenant.pk)

        return qs

    def save_model(
        self,
        request,
        obj,
        form,
        change,
    ):
        super().save_model(
            request,
            obj,
            form,
            change,
        )
        try:
            if not obj.user_set.filter(pk=request.user.pk).exists():
                obj.add_user(
                    request.user,
                    is_superuser=True,
                    is_staff=True,
                )
        except Exception as exc:
            self.message_user(
                request,
                _(
                    "Could not add %(user)s as a superuser "
                    "to %(tenant)s: %(error)s"
                )
                % {
                    "user": request.user,
                    "tenant": obj,
                    "error": exc,
                },
                level=messages.ERROR,
            )
            raise


@admin.register(Domain)
class DomainAdmin(ModelAdmin):
    list_display = [
        "domain",
        "tenant",
        "is_primary",
    ]

    search_fields = [
        "domain",
        "tenant__name",
        "tenant__schema_name",
    ]


    def has_create_permission(self, request):
        if not request.tenant.schema_name == "public" and not request.user.is_superuser and not request.user.is_staff:
            return False
        return request.user.is_superuser or request.user.is_staff

    def get_queryset(self, request):
        qs = super().get_queryset(request)

        if request.tenant.schema_name != "public":
            return qs.filter(tenant=request.tenant)

        return qs


@admin.register(Invitation)
class InvitationAdmin(ModelAdmin):
    form = InvitationAdminForm

    list_display = [
        "tenant",
        "email",
        "invited_by",
        "status",
        "expires_at",
    ]

    list_filter = [
        "status",
        "tenant",
    ]

    search_fields = [
        "tenant__name",
        "email",
        "invited_by__email",
    ]

    readonly_fields = [
        "token",
        "status",
        "invited_by",
        "sent_at",
        "accepted_at",
        "created_at",
        "updated_at",
    ]

    autocomplete_fields = [
        "tenant",
    ]

    actions = [
        "resend_invitations",
    ]

    @admin.action(
        description=_(
            "Resend selected invitations"
        )
    )
    def resend_invitations(
        self,
        request,
        queryset,
    ):
        queued = 0
        skipped = 0

        for invitation in queryset.select_related(
            "tenant",
            "invited_by",
        ):
            if (
                invitation.status
                != InvitationStatus.PENDING
                or invitation.expires_at
                <= timezone.now()
            ):
                skipped += 1
                continue

            try:
                new_invitation = create_invitation(
                    tenant=invitation.tenant,
                    email=invitation.email,
                    invited_by=request.user,
                    message=invitation.message,
                    expires_at=invitation.expires_at,
                )

                queue_invitation_notification(
                    new_invitation
                )

                queued += 1

            except Exception as exc:
                self.message_user(
                    request,
                    _(
                        "Could not resend "
                        "%(invitation)s: %(error)s"
                    )
                    % {
                        "invitation": invitation,
                        "error": exc,
                    },
                    level=messages.ERROR,
                )

        if queued:
            self.message_user(
                request,
                _(
                    "Created and queued "
                    "%(count)d new invitation(s)."
                )
                % {"count": queued},
                level=messages.SUCCESS,
            )

        if skipped:
            self.message_user(
                request,
                _(
                    "Skipped %(count)d non-pending "
                    "or expired invitation(s)."
                )
                % {"count": skipped},
                level=messages.WARNING,
            )

    def save_model(
        self,
        request,
        obj,
        form,
        change,
    ):
        if not change:
            obj.invited_by = request.user

        super().save_model(
            request,
            obj,
            form,
            change,
        )

    def has_add_permission(self, request):
        return (
            request.user.is_superuser
            and super().has_add_permission(request)
        )

    def has_change_permission(
        self,
        request,
        obj=None,
    ):
        return (
            request.user.is_superuser
            and super().has_change_permission(
                request,
                obj,
            )
        )

    def has_delete_permission(
        self,
        request,
        obj=None,
    ):
        return (
            request.user.is_superuser
            and super().has_delete_permission(
                request,
                obj,
            )
        )