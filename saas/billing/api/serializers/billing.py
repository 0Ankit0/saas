from rest_framework import serializers
from saas.billing.models import BillingCustomer
from saas.contrib.fields import HashIDField
from saas.tenants.api.serializers import TenantSerializer

class BillingCustomerSerializer(serializers.ModelSerializer):
    id = HashIDField()
    tenant = HashIDField()

    class Meta:
        model = BillingCustomer
        fields = (
            'id',
            'tenant',
            'provider',
            'provider_customer_id',
            'email',
            'name',
            'created_at',
            'created_by',
            'updated_at',
        )
        read_only_fields = ('id', 'tenant', 'provider_customer_id', 'created_at', 'created_by', 'updated_at')
