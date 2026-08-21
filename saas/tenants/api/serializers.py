from __future__ import annotations

from django.utils.text import slugify
from rest_framework import serializers

from saas.tenants.models import Invitation, Tenant, Domain
from saas.tenants.services import create_invitation, queue_invitation_notification
from saas.contrib.fields import HashIDField


class DomainSerializer(serializers.ModelSerializer[Domain]):
    id = HashIDField()
    class Meta:
        model = Domain
        fields = ["id", "domain", "is_primary"]
        read_only_fields = ["id"]

    # def create(self, validated_data):
    #     tenant = self.context["request"].tenant

    #     return Domain.objects.create(
    #         tenant=tenant,
    #         **validated_data,
    #     )

class TenantCreateSerializer(serializers.ModelSerializer[Tenant]):
    id = HashIDField()
    subdomain = serializers.CharField(
        source="schema_name",
    )

    class Meta:
        model = Tenant
        fields = [
            "id",
            "name",
            "subdomain",
        ]
        read_only_fields = [
            "id",
        ]

class TenantSerializer(serializers.ModelSerializer[Tenant]):
    id = HashIDField()
    domains = DomainSerializer(
            many=True,
            read_only=True,
        )
        
    class Meta:
        model = Tenant
        fields = [
            "id",
            "name",
            "domains",
        ]
        read_only_fields = [
            "id",
        ]
        
        

class InvitationSerializer(serializers.ModelSerializer[Invitation]):
    id = HashIDField()

    class Meta:
        model = Invitation
        fields = [
            "id",
            "email",
            "message",
            "status",
            "invited_by",
            "sent_at",
            "accepted_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "invited_by",
            "sent_at",
            "accepted_at",
            "created_at",
            "updated_at",
        ]

    def create(self, validated_data):
        request = self.context["request"]

        invitation = create_invitation(
            tenant=request.tenant,
            email=validated_data["email"],
            invited_by=request.user,
            message=validated_data.get("message"),
        )

        queue_invitation_notification(invitation)

        return invitation