from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import F
from rest_framework import generics, viewsets, status
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from .models import Vendor, Category, Product, Order, OrderItem, InventoryMovement
from .serializers import RegisterSerializer, VendorSerializer, CategorySerializer, ProductSerializer, CreateOrderSerializer, OrderSerializer

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Category.objects.all().order_by('name')
    serializer_class = CategorySerializer
    permission_classes = [AllowAny]

class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [AllowAny()]
        return [IsAuthenticated()]
    def get_queryset(self):
        qs = Product.objects.select_related('vendor', 'category')
        if self.action in ('list', 'retrieve'):
            qs = qs.filter(is_active=True, vendor__is_approved=True, vendor__is_suspended=False)
        elif self.request.user.is_staff:
            pass
        else:
            vendor = getattr(self.request.user, 'vendor_profile', None)
            qs = qs.filter(vendor=vendor) if vendor else qs.none()
        term = self.request.query_params.get('search')
        if term:
            qs = qs.filter(name__icontains=term)
        return qs
    def perform_create(self, serializer):
        vendor = getattr(self.request.user, 'vendor_profile', None)
        if not vendor or not vendor.is_approved or vendor.is_suspended:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('An approved, active vendor account is required.')
        serializer.save(vendor=vendor)
    def perform_update(self, serializer):
        product = self.get_object()
        if not self.request.user.is_staff and product.vendor.owner_id != self.request.user.id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('You cannot modify another vendor product.')
        serializer.save(vendor=product.vendor)
    def perform_destroy(self, instance):
        if not self.request.user.is_staff and instance.vendor.owner_id != self.request.user.id:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('You cannot delete another vendor product.')
        instance.delete()

class VendorViewSet(viewsets.ModelViewSet):
    serializer_class = VendorSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    def get_queryset(self):
        if self.request.user.is_staff:
            return Vendor.objects.select_related('owner').all()
        return Vendor.objects.filter(owner=self.request.user)
    def perform_create(self, serializer):
        if hasattr(self.request.user, 'vendor_profile'):
            from rest_framework.exceptions import ValidationError
            raise ValidationError('A vendor profile already exists for this account.')
        serializer.save(owner=self.request.user)
    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def approve(self, request, pk=None):
        vendor = self.get_object(); vendor.is_approved = True; vendor.is_suspended = False; vendor.save(update_fields=['is_approved','is_suspended'])
        return Response({'status':'approved'})
    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def suspend(self, request, pk=None):
        vendor = self.get_object(); vendor.is_suspended = True; vendor.save(update_fields=['is_suspended'])
        return Response({'status':'suspended'})

class OrderCreateView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        serializer = CreateOrderSerializer(data=request.data); serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        existing = Order.objects.filter(idempotency_key=data['idempotency_key']).first()
        if existing:
            if existing.buyer_id != request.user.id:
                return Response({'detail':'Idempotency key already used.'}, status=409)
            return Response(OrderSerializer(existing).data, status=200)
        with transaction.atomic():
            order = Order.objects.create(buyer=request.user, shipping_address=data['shipping_address'], idempotency_key=data['idempotency_key'])
            for line in data['items']:
                try:
                    product = Product.objects.select_for_update().select_related('vendor').get(pk=line['product_id'], is_active=True, vendor__is_approved=True, vendor__is_suspended=False)
                except Product.DoesNotExist:
                    from rest_framework.exceptions import ValidationError
                    raise ValidationError({'items': f"Product {line['product_id']} is unavailable."})
                if product.stock < line['quantity']:
                    from rest_framework.exceptions import ValidationError
                    raise ValidationError({'items': f"Insufficient stock for {product.name}."})
                product.stock -= line['quantity']; product.save(update_fields=['stock','updated_at'])
                OrderItem.objects.create(order=order, product=product, product_name=product.name, unit_price=product.price, quantity=line['quantity'])
                InventoryMovement.objects.create(product=product, quantity_delta=-line['quantity'], reason=f'Order {order.id}')
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

class OrderListView(generics.ListAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        if self.request.user.is_staff: return Order.objects.prefetch_related('items').all().order_by('-created_at')
        return Order.objects.filter(buyer=self.request.user).prefetch_related('items').order_by('-created_at')

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def register_vendor(request):
    return Response({'detail':'Use POST /api/vendors/ with store_name and description.'}, status=200)
