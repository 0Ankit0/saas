from rest_framework.viewsets import ModelViewSet
from saas.billing.models import Product
from saas.billing.api.serializers import ProductSerializer
from rest_framework.permissions import DjangoModelPermissionsOrAnonReadOnly

class ProductViewSet(ModelViewSet):
    queryset = Product.objects.all()
    serializer_class = ProductSerializer
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