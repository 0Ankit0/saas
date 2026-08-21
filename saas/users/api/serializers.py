from rest_framework import serializers
from django.contrib.auth.models import Group, Permission

from saas.contrib.fields import HashIDField
from saas.users.models import User


class UserSerializer(serializers.ModelSerializer[User]):
    id = HashIDField()
    class Meta:
        model = User
        fields = [ "id", "email", "is_active", "is_staff", "is_superuser"]
