from django.shortcuts import get_object_or_404
from rest_framework.exceptions import NotFound
from rest_framework.viewsets import ModelViewSet

from saas.contrib.utils import decode_hashid


class HashIDModelViewSet(ModelViewSet):
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

