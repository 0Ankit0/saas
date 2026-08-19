from django.contrib.auth import logout
from django.urls import reverse
from allauth.account.adapter import DefaultAccountAdapter


class AccountAdapter(DefaultAccountAdapter):

    def get_password_change_redirect_url(self, request):
        if request.session.pop(
            "invitation_password_setup",
            False,
        ):
            logout(request)
            return reverse("account_login")

        return super().get_password_change_redirect_url(request)