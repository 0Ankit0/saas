from django.urls import path

from . import views

app_name = "tenants"

urlpatterns = [
    path("organization/invite/", views.invite_user, name="invite-user"),
    path("organization/invite/<uuid:token>/resend/", views.resend_invitation, name="invitation-resend"),
    path("invitations/<uuid:token>/", views.invitation_accept, name="invitation-accept"),
    path("invitations/<uuid:token>/cancel/", views.invitation_cancel, name="invitation-cancel"),
]