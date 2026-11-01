from django.contrib.auth.models import User
from rest_framework import serializers
from .models import Vendor, Category, Product, Order, OrderItem, VendorFulfillment, PaymentRecord

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
    payment_status = serializers.SerializerMethodField()
    class Meta:
        model = Order
        fields = ('id', 'buyer', 'status', 'shipping_address', 'items', 'total', 'payment_status', 'created_at')
        read_only_fields = fields
    def get_total(self, obj):
        return str(sum((item.unit_price * item.quantity for item in obj.items.all()), start=0))
    def get_payment_status(self, obj):
        payment = obj.payments.filter(provider='razorpay').order_by('-created_at').first()
        return payment.status if payment else 'UNPAID'


class VendorFulfillmentSerializer(serializers.ModelSerializer):
    order_id = serializers.IntegerField(source='order.id', read_only=True)
    shipping_address = serializers.CharField(source='order.shipping_address', read_only=True)
    buyer_username = serializers.CharField(source='order.buyer.username', read_only=True)
    items = serializers.SerializerMethodField()
    subtotal = serializers.SerializerMethodField()
    class Meta:
        model = VendorFulfillment
        fields = ('id', 'order_id', 'status', 'tracking_reference', 'shipping_address', 'buyer_username', 'items', 'subtotal', 'created_at', 'updated_at')
        read_only_fields = fields
    def get_items(self, obj):
        items = obj.order.items.filter(product__vendor=obj.vendor).select_related('product')
        return OrderItemSerializer(items, many=True).data
    def get_subtotal(self, obj):
        items = obj.order.items.filter(product__vendor=obj.vendor)
        return str(sum((item.unit_price * item.quantity for item in items), start=0))
