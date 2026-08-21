from rest_framework import serializers
from django.contrib.auth.models import Group, Permission

from saas.contrib.fields import HashIDField
from saas.users.models import User


class UserSerializer(serializers.ModelSerializer[User]):
    id = HashIDField()
    class Meta:
        model = User
        fields = [ "id", "email", "is_active", "is_staff", "is_superuser"]
        read_only_fields = ["id", "email", "is_active", "is_staff", "is_superuser"]

class PermissionSerializer(serializers.ModelSerializer[Permission]):
    id = HashIDField()
    class Meta:
        model = Permission
        fields = ["id", "name", "content_type", "codename"]
        read_only_fields = ["id"]

class GroupSerializer(serializers.ModelSerializer[Group]):
    id = HashIDField()
    permissions = PermissionSerializer(many=True)
    class Meta:
        model = Group
        fields = ["id", "name", "permissions"]
        read_only_fields = ["id", "permissions"]
