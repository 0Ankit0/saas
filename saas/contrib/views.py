
from rest_framework.viewsets import ModelViewSet

from saas.contrib.mixins import HashIDLookupMixin
from saas.contrib.fields import HashIDField


class HashIDModelViewSet(HashIDLookupMixin, ModelViewSet):
    id = HashIDField()

