from django import forms
from django.contrib.auth import get_user_model
from django.utils.translation import gettext_lazy as _

from saas.tenants.models import Invitation
from saas.tenants.services import create_invitation


User = get_user_model()


class InvitationAdminForm(forms.ModelForm):
    class Meta:
        model = Invitation
        fields = [
            "tenant",
            "email",
            "message",
        ]

    def clean(self):
        cleaned = super().clean()

        tenant = cleaned.get("tenant")
        email = cleaned.get("email")

        if (
            tenant
            and email
            and tenant.user_set.filter(
                email__iexact=email
            ).exists()
        ):
            self.add_error(
                "email",
                _(
                    "This user is already a member "
                    "of the tenant."
                ),
            )

        return cleaned


class InvitationForm(forms.ModelForm):
    class Meta:
        model = Invitation
        fields = [
            "email",
            "message",
            "expires_at",
        ]

        widgets = {
            "message": forms.Textarea(
                attrs={"rows": 4}
            ),
        }

    def __init__(
        self,
        *args,
        tenant=None,
        invited_by=None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        self.tenant = tenant
        self.invited_by = invited_by

    def clean_email(self):
        email = self.cleaned_data["email"].strip().lower()

        if self.tenant.user_set.filter(
            email__iexact=email
        ).exists():
            raise forms.ValidationError(
                _(
                    "This user is already a member "
                    "of the organization."
                )
            )

        return email

    def save(self, commit=True):
        if not commit:
            return super().save(commit=False)

        return create_invitation(
            tenant=self.tenant,
            email=self.cleaned_data["email"],
            invited_by=self.invited_by,
            message=self.cleaned_data.get(
                "message",
                "",
            ),
            expires_at=self.cleaned_data.get(
                "expires_at",
            ),
        )