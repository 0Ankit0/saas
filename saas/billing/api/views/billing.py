from saas.contrib.views import HashIDModelViewSet
from saas.billing.models import BillingCustomer
from saas.billing.api.serializers import BillingCustomerSerializer

class BillingCustomerViewSet(HashIDModelViewSet):
    queryset = BillingCustomer.objects.all()
    serializer_class = BillingCustomerSerializer

    def perform_create(self, serializer):
        serializer.save(
            tenant=self.request.tenant, 
            created_by=self.request.user
        )

    def perform_update(self, serializer):
        serializer.save(
            updated_by=self.request.user
        )