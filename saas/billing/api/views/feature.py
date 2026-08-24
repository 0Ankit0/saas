from rest_framework.viewsets import ModelViewSet
from saas.billing.api.serializers.feature import ProductFeatureCreateUpdateSerializer
from saas.billing.models import ProductFeature, Feature
from saas.billing.api.serializers import ProductFeatureSerializer, FeatureSerializer
from rest_framework.permissions import DjangoModelPermissionsOrAnonReadOnly

class FeatureViewSet(ModelViewSet):
    queryset = Feature.objects.all()
    serializer_class = FeatureSerializer
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

class ProductFeatureViewSet(ModelViewSet):
    queryset = ProductFeature.objects.all()
    serializer_class = ProductFeatureSerializer
    permission_classes = [DjangoModelPermissionsOrAnonReadOnly]

    def get_serializer_class(self):
        if self.action in ['create', 'update', 'partial_update']:
            return ProductFeatureCreateUpdateSerializer
        return ProductFeatureSerializer

    def perform_create(self, serializer):
        serializer.save(
            created_by=self.request.user,
            updated_by=self.request.user
        )

    def perform_update(self, serializer):
        serializer.save(
            updated_by=self.request.user
        )
