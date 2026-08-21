from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.mixins import ListModelMixin
from rest_framework.mixins import RetrieveModelMixin
from rest_framework.mixins import UpdateModelMixin
from rest_framework.response import Response
from rest_framework.viewsets import GenericViewSet, ModelViewSet
from django.contrib.auth.models import Group, Permission
from werkzeug.exceptions import NotFound
from saas.contrib.views import HashIDModelViewSet

from saas.contrib.utils import decode_hashid
from saas.users.models import User

from .serializers import GroupSerializer, PermissionSerializer, UserSerializer


class UserViewSet(RetrieveModelMixin, ListModelMixin, UpdateModelMixin, GenericViewSet):
    serializer_class = UserSerializer
    queryset = User.objects.all()
    lookup_field = "ukid"

    def get_object(self):
        queryset = self.filter_queryset(self.get_queryset())

        ukid = self.kwargs[
            self.lookup_url_kwarg or self.lookup_field
        ]


        try:
            pk = decode_hashid(ukid)
        except ValueError:
            raise NotFound("Invalid ID.")

        obj = get_object_or_404(queryset, pk=pk)

        self.check_object_permissions(self.request, obj)

        return obj

    def get_queryset(self, *args, **kwargs):
        assert isinstance(self.request.user.id, int)
        return self.queryset.filter(id=self.request.user.id)

    @action(detail=False)
    def me(self, request):
        serializer = UserSerializer(request.user, context={"request": request})
        return Response(status=status.HTTP_200_OK, data=serializer.data)

class GroupViewSet(HashIDModelViewSet):
    queryset = Group.objects.all()
    serializer_class = GroupSerializer

class PermissionViewSet(HashIDModelViewSet):
    queryset = Permission.objects.all()
    serializer_class = PermissionSerializer