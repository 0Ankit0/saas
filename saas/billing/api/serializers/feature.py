from rest_framework import serializers
from saas.billing.api.serializers.product import ProductSerializer
from saas.billing.models import Feature, ProductFeature
from saas.contrib.fields import HashIDField

class FeatureSerializer(serializers.ModelSerializer):
    id = HashIDField()

    class Meta:
        model = Feature
        fields = (
            'id',
            'name',
            'description',
            'active',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

class ProductFeatureCreateUpdateSerializer(serializers.ModelSerializer):
    id = HashIDField()
    product = HashIDField()
    feature = HashIDField()

    class Meta:
        model = ProductFeature
        fields = (
            'id',
            'product',
            'feature',
            'enabled',
            'limit',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')

class ProductFeatureSerializer(serializers.ModelSerializer):
    id = HashIDField()
    feature = FeatureSerializer(read_only=True)
    product = ProductSerializer(read_only=True)

    class Meta:
        model = ProductFeature
        fields = (
            'id',
            'product',
            'feature',
            'enabled',
            'limit',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id', 'created_at', 'updated_at')