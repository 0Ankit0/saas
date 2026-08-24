from rest_framework import serializers
from saas.billing.models import Price
from saas.contrib.fields import HashIDField
from .product import ProductSerializer

class PriceCreateUpdateSerializer(serializers.ModelSerializer):
    id = HashIDField()
    product = HashIDField()

    class Meta:
        model = Price
        fields = (
            'id',
            'product',
            'name',
            'amount',
            'currency',
            'interval',
            'interval_count',
            'active',
            'metadata',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

class PriceSerializer(serializers.ModelSerializer):
    id = HashIDField()
    product = ProductSerializer(read_only=True)

    class Meta:
        model = Price
        fields = (
            'id',
            'product',
            'name',
            'amount',
            'currency',
            'amount_display',
            'interval',
            'interval_count',
            'active',
            'metadata',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id','slug','amount_display', 'created_at', 'updated_at')