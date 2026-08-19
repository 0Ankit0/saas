from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.utils.translation import gettext_lazy as _
from django_tenants.utils import get_public_schema_name

from saas.tenants.forms import InvitationForm
from saas.tenants.models import (
    Invitation,
    InvitationStatus,
)
from saas.tenants.services import (
    accept_invitation,
    create_invitation,
    queue_invitation_notification,
)


@login_required
def invite_user(request):
    tenant = request.tenant

    if (
        tenant.schema_name == get_public_schema_name()
        or tenant.owner_id != request.user.id
    ):
        raise Http404

    if request.method == "POST":
        form = InvitationForm(
            request.POST,
            tenant=tenant,
            invited_by=request.user,
        )

        if form.is_valid():
            invitation = form.save()

            try:
                queue_invitation_notification(
                    invitation
                )
            except Exception:
                messages.error(
                    request,
                    _(
                        "The invitation was created "
                        "but could not be queued. "
                        "Please try again."
                    ),
                )
            else:
                messages.success(
                    request,
                    _("Invitation email queued."),
                )

                return redirect(
                    "tenants:invite-user"
                )

    else:
        form = InvitationForm(
            tenant=tenant,
            invited_by=request.user,
        )

    pending_invitations = (
        tenant.invitations
        .filter(
            status=InvitationStatus.PENDING,
        )
        .select_related("user")
    )

    return render(
        request,
        "tenants/invite_user.html",
        {
            "form": form,
            "tenant": tenant,
            "pending_invitations": (
                pending_invitations
            ),
        },
    )


@login_required
def resend_invitation(request, token):
    if request.method != "POST":
        raise Http404

    invitation = get_object_or_404(
        Invitation.objects.select_related(
            "tenant",
            "invited_by",
        ),
        token=token,
    )

    if (
        invitation.tenant.owner_id != request.user.id
        and not request.user.is_superuser
    ):
        raise Http404

    if invitation.status != InvitationStatus.PENDING:
        messages.error(
            request,
            _(
                "Only pending invitations "
                "can be resent."
            ),
        )

        return redirect(
            "tenants:invite-user"
        )

    if invitation.is_expired:
        invitation.status = InvitationStatus.EXPIRED

        invitation.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        messages.error(
            request,
            _("This invitation has expired."),
        )

        return redirect(
            "tenants:invite-user"
        )

    new_invitation = create_invitation(
        tenant=invitation.tenant,
        email=invitation.email,
        invited_by=request.user,
        message=invitation.message,
        expires_at=invitation.expires_at,
    )

    try:
        queue_invitation_notification(
            new_invitation
        )
    except Exception:
        messages.error(
            request,
            _(
                "A new invitation was created "
                "but could not be queued."
            ),
        )
    else:
        messages.success(
            request,
            _("New invitation email queued."),
        )

    return redirect(
        "tenants:invite-user"
    )

def invitation_accept(request, token):
    invitation = get_object_or_404(
        Invitation,
        token=token,
    )

    try:
        invitation, user, created = accept_invitation(
            invitation.pk
        )
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect("account_login")

    login(
        request,
        user,
        backend="tenant_users.permissions.backend.UserBackend",
    )

    if created:
        request.session["invitation_password_setup"] = True
        return redirect("account_set_password")

    return redirect("home")

@login_required
def invitation_cancel(request, token):
    if request.method != "POST":
        raise Http404

    invitation = get_object_or_404(
        Invitation,
        token=token,
    )

    if (
        invitation.tenant.owner_id != request.user.id
        and not request.user.is_superuser
    ):
        raise Http404

    try:
        invitation.cancel()

    except ValidationError as exc:
        messages.error(
            request,
            exc.message,
        )

    else:
        messages.info(
            request,
            _("Invitation canceled."),
        )

    return redirect("users:redirect")