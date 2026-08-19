from __future__ import annotations
from typing import TYPE_CHECKING

from django.db import models, transaction
from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django_tenants.models import DomainMixin
from tenant_users.tenants.models import ExistsError, TenantBase
from django.utils import timezone
from datetime import timedelta
from django.core.exceptions import ValidationError
import uuid

from saas.tenants.services import accept_invitation
if TYPE_CHECKING:
    from django.contrib.auth import get_user_model
    from django_tenants.utils import get_tenant_model

    User = get_user_model()
    Tenant = get_tenant_model()

def default_invitation_expiry():
    return timezone.now() + timedelta(days=7)


class Tenant(TenantBase):
    """Project tenant metadata stored in the public schema."""

    name = models.CharField(_("Tenant Name"), max_length=255, unique=True, help_text=_("The human-readable name of the tenant."))

    class Meta:
        verbose_name = _("Tenant")
        verbose_name_plural = _("Tenants")

    def __str__(self) -> str:
        return self.name


class Domain(DomainMixin):
    """Tenant domain mapping for host-based tenant routing."""

    class Meta:
        verbose_name = _("Domain")
        verbose_name_plural = _("Domains")

class InvitationStatus(models.TextChoices):
    PENDING = "pending", _("Pending")
    ACCEPTED = "accepted", _("Accepted")
    EXPIRED = "expired", _("Expired")
    CANCELED = "canceled", _("Canceled")

class Invitation(models.Model):
    """A pending request for a user to join a tenant."""

    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField(_("Email"))
    invited_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="sent_invitations")
    token = models.UUIDField(unique=True, editable=False, default=uuid.uuid4)
    status = models.CharField(max_length=20, choices=InvitationStatus.choices, default=InvitationStatus.PENDING)
    message = models.TextField( blank=True, null=True)
    sent_at = models.DateTimeField(blank=True, null=True)
    expires_at = models.DateTimeField(default=default_invitation_expiry,db_index=True)
    accepted_at = models.DateTimeField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = _("Tenant Invitation")
        verbose_name_plural = _("Tenant Invitations")
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "email"],
                condition=models.Q(status=InvitationStatus.PENDING),
                name="unique_pending_invitation"
            )
        ]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["email", "status"]),
        ]

    def __str__(self) -> str:
        if not self.email or not self.tenant_id:
            return "New invitation"

        return f"{self.email} → {self.tenant.name} ({self.get_status_display()})"

    def is_valid(self) -> bool:
        """Check if the invitation is still valid (not expired or canceled)."""
        return self.status == InvitationStatus.PENDING and self.expires_at > timezone.now()

    @property
    def is_expired(self) -> bool:
        """Check if the invitation has expired."""
        return self.expires_at <= timezone.now() and self.status == InvitationStatus.PENDING

    def clean(self) -> None:
        super().clean()

        if (
            self.invited_by_id
            and not self.invited_by.is_superuser
            and self.tenant.owner_id != self.invited_by_id
        ):
            raise ValidationError(
                {
                    "invited_by": _(
                        "Only the tenant owner or a superuser can create invitations."
                    )
                }
            )

        if self.email:
            self.email = self.email.strip().lower()

        if self.tenant_id and self.email:
            # Don't allow inviting an email that already belongs to
            # a member of this tenant.
            if self.tenant.user_set.filter(
                email__iexact=self.email,
            ).exists():
                raise ValidationError(
                    {
                        "email": _(
                            "This email address already belongs to a member "
                            "of this organization."
                        )
                    }
                )

    @transaction.atomic
    def accept(self) -> tuple["Invitation", "User", bool]:
        return accept_invitation(invitation_id=self.id)
        
    @transaction.atomic
    def cancel(self) -> None:
        if self.status == InvitationStatus.CANCELED:
            return
        if self.status != InvitationStatus.PENDING:
            raise ValidationError(_("This invitation is no longer available."))
        self.status = InvitationStatus.CANCELED
        self.save(update_fields=["status", "updated_at"])
