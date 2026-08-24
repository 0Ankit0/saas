from __future__ import annotations
from typing import TYPE_CHECKING

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

if TYPE_CHECKING:
    from saas.tenants.models import Invitation, InvitationStatus


User = get_user_model()


def invitation_url(invitation: Invitation) -> str:
    """
    Build the public invitation URL.

    TENANT_USERS_DOMAIN should contain the scheme, for example:

        http://localhost:8000

    or:

        https://app.example.com
    """
    path = reverse(
        "tenants:invitation-accept",
        kwargs={"token": invitation.token},
    )

    base = settings.TENANT_USERS_DOMAIN.rstrip("/")

    if "://" not in base:
        raise ValueError(
            "TENANT_USERS_DOMAIN must include a scheme, "
            "for example 'http://localhost:8000'."
        )

    return f"{base}{path}"


def queue_invitation_notification(
    invitation: Invitation,
) -> None:
    """
    Queue the invitation email after the current
    database transaction successfully commits.
    """
    from .tasks import send_invitation_email

    transaction.on_commit(
        lambda: send_invitation_email.delay(invitation.pk)
    )


@transaction.atomic
def create_invitation(
    *,
    tenant,
    email,
    invited_by,
    message="",
    expires_at=None,
) -> Invitation:
    """
    Create a new invitation.

    Any older pending invitation for the same
    tenant/email is canceled.
    """
    from .models import Invitation, InvitationStatus

    email = email.strip().lower()

    Invitation.objects.filter(
        tenant=tenant,
        email__iexact=email,
        status=InvitationStatus.PENDING,
    ).update(
        status=InvitationStatus.CANCELED,
        updated_at=timezone.now(),
    )

    invitation = Invitation(
        tenant=tenant,
        email=email,
        invited_by=invited_by,
        message=message,
    )

    if expires_at is not None:
        invitation.expires_at = expires_at

    invitation.save()

    return invitation


def get_or_create_user_for_invitation(
    invitation: Invitation,
) -> tuple[User, bool]:
    """
    Get the user associated with the invitation email.

    Returns:
        (user, created)
    """
    email = invitation.email.strip().lower()

    user = User.objects.filter(
        email__iexact=email,
    ).first()

    if user is not None:
        return user, False

    user = User(
        email=email,
        is_active=True,
    )

    user.set_unusable_password()
    user.save()

    return user, True


@transaction.atomic
def accept_invitation(
    invitation_id: int,
) -> tuple[Invitation, User, bool]:
    """
    Accept an invitation.

    Creates the user if necessary and adds the user
    to the tenant.

    Returns:
        (invitation, user, user_created)
    """
    from .models import Invitation, InvitationStatus
    
    invitation = (
        Invitation.objects
        .select_for_update()
        .select_related("tenant")
        .get(pk=invitation_id)
    )

    if invitation.status == InvitationStatus.ACCEPTED:
        user = User.objects.get(
            email__iexact=invitation.email,
        )

        return invitation, user, False

    if invitation.status != InvitationStatus.PENDING:
        raise ValueError(
            "This invitation is no longer available."
        )

    if invitation.is_expired:
        invitation.status = InvitationStatus.EXPIRED

        invitation.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        raise ValueError(
            "This invitation has expired."
        )

    user, created = get_or_create_user_for_invitation(
        invitation
    )
    if created:
        tenant = invitation.tenant
        tenant.add_user(user)

    if not user.is_active:
        raise ValueError(
            "Your user account is inactive."
        )

    try:
        invitation.tenant.add_user(user)
    except Exception as exc:
        raise ValueError(
            "You are already a member of this organization."
        ) from exc

    invitation.status = InvitationStatus.ACCEPTED
    invitation.accepted_at = timezone.now()

    invitation.save(
        update_fields=[
            "status",
            "accepted_at",
            "updated_at",
        ]
    )

    return invitation, user, created