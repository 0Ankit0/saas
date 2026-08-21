from datetime import timezone

from django.db.models import Prefetch
from rest_framework import response
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, BasePermission, IsAdminUser, IsAuthenticated
from rest_framework.viewsets import GenericViewSet, ModelViewSet
from rest_framework.mixins import CreateModelMixin, DestroyModelMixin, ListModelMixin, RetrieveModelMixin, UpdateModelMixin
from slugify import slugify
from tenant_users.tenants.tasks import provision_tenant
from werkzeug.exceptions import MethodNotAllowed
from saas.tenants.models import InvitationStatus, Tenant, Domain, Invitation
from saas.tenants.api.serializers import TenantCreateSerializer, TenantSerializer, DomainSerializer, InvitationSerializer
from saas.tenants.api.permissions import TenantDomainPermission
from saas.tenants.services import create_invitation, queue_invitation_notification
from rest_framework.response import Response
from saas.contrib.views import HashIDModelViewSet

class TenantViewSet(HashIDModelViewSet):
    queryset = Tenant.objects.all()
    serializer_class = TenantSerializer
    lookup_field = "ukid"

    def get_serializer_class(self):
        if self.action == "create":
            return TenantCreateSerializer

        return TenantSerializer

    def get_queryset(self):
        return Tenant.objects.prefetch_related(
            Prefetch(
                "domains"
            )
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        name = serializer.validated_data["name"]
        subdomain = serializer.validated_data["subdomain"]

        tenant, domain = provision_tenant(
            tenant_name=name,
            tenant_slug=slugify(subdomain),
            owner=request.user,
        )

        output_serializer = self.get_serializer(tenant)

        return response.Response(
            output_serializer.data,
            status=status.HTTP_201_CREATED,
        )


class DomainViewSet(HashIDModelViewSet):
    queryset = Domain.objects.all()
    serializer_class = DomainSerializer
    permission_classes = [TenantDomainPermission]


    def create(self, request, *args, **kwargs):
        raise MethodNotAllowed("POST")

class InvitationViewSet(HashIDModelViewSet):
    def get_queryset(self):
        tenant = self.request.tenant
        return Invitation.objects.filter(tenant=tenant)
    
    queryset = Invitation.objects.all()
    serializer_class = InvitationSerializer

    def get_permissions(self) -> list[BasePermission]:
        if self.action == "resend":
            permission_classes = [IsAdminUser]
        elif self.action == "accept":
            permission_classes = [AllowAny]
        else:
            permission_classes = [IsAuthenticated]

        return [
            permission()
            for permission in permission_classes
        ]

    def perform_create(self, serializer):
        invitation = serializer.save(
            tenant=self.request.tenant,
            invited_by=self.request.user,
        )

        queue_invitation_notification(invitation)

    @action(detail=True, methods=["post"])
    def resend(self, request, pk=None):
        invitation = self.get_object()

        if invitation.status != InvitationStatus.PENDING:
            return Response(
                {"detail": "Only pending invitations can be resent."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if invitation.expires_at <= timezone.now():
            return Response(
                {"detail": "Expired invitations cannot be resent."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        new_invitation = create_invitation(
            tenant=invitation.tenant,
            email=invitation.email,
            invited_by=request.user,
            message=invitation.message,
            expires_at=invitation.expires_at,
        )

        queue_invitation_notification(new_invitation)

        return Response(
            InvitationSerializer(new_invitation).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        invitation = self.get_object()

        if invitation.status != InvitationStatus.PENDING:
            return Response(
                {"detail": "Only pending invitations can be canceled."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        invitation.status = InvitationStatus.CANCELED
        invitation.save(update_fields=["status", "updated_at"])

        return Response(
            {"detail": "Invitation canceled successfully."},
            status=status.HTTP_200_OK,
        )