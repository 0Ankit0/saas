from celery import shared_task
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.utils import timezone

from .email import InvitationEmailAdapter
from .models import Invitation, InvitationStatus
from .services import invitation_url


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
    acks_late=True,
)
def send_invitation_email(
    self,
    invitation_id: int,
) -> bool:
    """Render and deliver one invitation email."""
    try:
        invitation = (
            Invitation.objects
            .select_related(
                "tenant",
                "invited_by",
            )
            .get(pk=invitation_id)
        )
    except ObjectDoesNotExist:
        return False

    if invitation.sent_at is not None:
        return True

    if invitation.status != InvitationStatus.PENDING:
        return False

    if invitation.expires_at <= timezone.now():
        invitation.status = InvitationStatus.EXPIRED

        invitation.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        return False

    url = invitation_url(invitation)

    context = {
        "invitation": invitation,
        "tenant": invitation.tenant,
        "email": invitation.email,
        "invited_by": invitation.invited_by,
        "invitation_url": url,
        "expires_at": invitation.expires_at,
        "message": invitation.message,
    }

    delivered = InvitationEmailAdapter().send_mail(
        invitation.email,
        context,
    )

    if delivered != 1:
        raise RuntimeError(
            f"Invitation email backend returned {delivered}"
        )

    with transaction.atomic():
        updated = (
            Invitation.objects
            .filter(
                pk=invitation.pk,
                sent_at__isnull=True,
                status=InvitationStatus.PENDING,
            )
            .update(
                sent_at=timezone.now(),
                updated_at=timezone.now(),
            )
        )

    return bool(updated)