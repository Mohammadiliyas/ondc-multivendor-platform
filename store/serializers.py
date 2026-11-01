from django.contrib.auth.models import User
from rest_framework import serializers
from django.contrib.auth.password_validation import validate_password
import re
from .models import Vendor, Category, Product, Order, OrderItem, VendorFulfillment, PaymentRecord

class RegisterSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, validators=[validate_password])
    phone = serializers.CharField(write_only=True, max_length=20)
    username = serializers.CharField(required=False, allow_blank=True)
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'password', 'phone')
    def validate_email(self, value):
        value = value.strip().lower()
        if not value or User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError('A unique email address is required.')
        return value
    def validate_phone(self, value):
        value = ''.join(ch for ch in value if ch.isdigit() or ch == '+')
        if not re.fullmatch(r'\+[1-9][0-9]{8,14}', value):
            raise serializers.ValidationError('Enter a phone number in international format, e.g. +919876543210.')
        from .models import UserVerification
        if UserVerification.objects.filter(phone=value).exists():
            raise serializers.ValidationError('This phone number is already registered.')
        return value
    def create(self, validated_data):
        from .models import UserVerification
        phone = validated_data.pop('phone')
        supplied_username = (validated_data.pop('username', '') or '').strip()
        if not supplied_username:
            base = 'ml_' + ''.join(ch for ch in phone if ch.isdigit())
            supplied_username = base
            suffix = 1
            while User.objects.filter(username=supplied_username).exists():
                supplied_username = f'{base}_{suffix}'
                suffix += 1
        user = User.objects.create_user(username=supplied_username, is_active=False, **validated_data)
        UserVerification.objects.create(user=user, phone=phone)
        return user

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
        fields = ('id', 'vendor', 'vendor_name', 'category', 'name', 'description', 'image_url', 'sku', 'price', 'stock', 'is_active', 'created_at', 'updated_at')
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
