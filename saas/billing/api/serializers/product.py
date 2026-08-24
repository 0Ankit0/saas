from rest_framework import serializers
from saas.billing.models import Product
from saas.contrib.fields import HashIDField

class ProductSerializer(serializers.ModelSerializer):
    id = HashIDField()

    class Meta:
        model = Product
        fields = (
            'id',
            'name',
            'description',
            'metadata',
            'created_at',
            'updated_at',
        )
        read_only_fields = ('id','slug', 'created_at', 'updated_at')

        
