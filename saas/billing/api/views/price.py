from rest_framework.viewsets import ModelViewSet
from saas.billing.models import Price
from saas.billing.api.serializers import PriceSerializer
from rest_framework.permissions import DjangoModelPermissionsOrAnonReadOnly

class PriceViewSet(ModelViewSet):
    queryset = Price.objects.all()
    serializer_class = PriceSerializer
    permission_classes = [DjangoModelPermissionsOrAnonReadOnly]

    def perform_create(self, serializer):
        serializer.save(
            created_by=self.request.user,
            updated_by=self.request.user
        )

    def perform_update(self, serializer):
        serializer.save(
            updated_by=self.request.user
        )
