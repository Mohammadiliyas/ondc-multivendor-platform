from django.contrib.auth.models import User
from rest_framework import serializers
from .models import Vendor, Category, Product, Order, OrderItem

class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=8)
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'password')
    def create(self, validated_data):
        return User.objects.create_user(**validated_data)

class VendorSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source='owner.username', read_only=True)
    class Meta:
        model = Vendor
        fields = ('id', 'owner', 'owner_username', 'store_name', 'description', 'is_approved', 'is_suspended', 'created_at')
        read_only_fields = ('owner', 'is_approved', 'is_suspended', 'created_at')

class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ('id', 'name')

class ProductSerializer(serializers.ModelSerializer):
    vendor_name = serializers.CharField(source='vendor.store_name', read_only=True)
    class Meta:
        model = Product
        fields = ('id', 'vendor', 'vendor_name', 'category', 'name', 'description', 'sku', 'price', 'stock', 'is_active', 'created_at', 'updated_at')
        read_only_fields = ('vendor', 'created_at', 'updated_at')

class OrderItemInputSerializer(serializers.Serializer):
    product_id = serializers.IntegerField(min_value=1)
    quantity = serializers.IntegerField(min_value=1, max_value=100)

class CreateOrderSerializer(serializers.Serializer):
    shipping_address = serializers.CharField(min_length=10)
    idempotency_key = serializers.CharField(max_length=100)
    items = OrderItemInputSerializer(many=True, allow_empty=False)

class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ('id', 'product', 'product_name', 'unit_price', 'quantity')

class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    total = serializers.SerializerMethodField()
    class Meta:
        model = Order
        fields = ('id', 'buyer', 'status', 'shipping_address', 'items', 'total', 'created_at')
        read_only_fields = fields
    def get_total(self, obj):
        return str(sum((item.unit_price * item.quantity for item in obj.items.all()), start=0))
