from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Sum
from rest_framework import generics, viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied, ValidationError
from .models import Vendor, Category, Product, Order, OrderItem, InventoryMovement, AuditLog
from .serializers import RegisterSerializer, VendorSerializer, CategorySerializer, ProductSerializer, CreateOrderSerializer, OrderSerializer

class RegisterView(generics.CreateAPIView):
    queryset = User.objects.all()
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]

class CategoryViewSet(viewsets.ModelViewSet):
    queryset = Category.objects.all().order_by('name')
    serializer_class = CategorySerializer
    def get_permissions(self):
        return [AllowAny()] if self.action in ('list', 'retrieve') else [IsAdminUser()]

class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    def get_permissions(self):
        return [AllowAny()] if self.action in ('list', 'retrieve') else [IsAuthenticated()]
    def get_queryset(self):
        qs = Product.objects.select_related('vendor', 'category')
        if self.action in ('list', 'retrieve'):
            qs = qs.filter(is_active=True, vendor__is_approved=True, vendor__is_suspended=False)
        elif self.request.user.is_staff:
            pass
        else:
            vendor = getattr(self.request.user, 'vendor_profile', None)
            qs = qs.filter(vendor=vendor) if vendor and vendor.is_approved and not vendor.is_suspended else qs.none()
        term = self.request.query_params.get('search')
        return qs.filter(name__icontains=term) if term else qs
    def perform_create(self, serializer):
        vendor = getattr(self.request.user, 'vendor_profile', None)
        if not vendor or not vendor.is_approved or vendor.is_suspended:
            raise PermissionDenied('An approved, active vendor account is required.')
        serializer.save(vendor=vendor)
    def perform_update(self, serializer):
        product = self.get_object()
        if not self.request.user.is_staff and product.vendor.owner_id != self.request.user.id:
            raise PermissionDenied('You cannot modify another vendor product.')
        serializer.save(vendor=product.vendor)
    def perform_destroy(self, instance):
        if not self.request.user.is_staff and instance.vendor.owner_id != self.request.user.id:
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
            raise ValidationError('A vendor profile already exists for this account.')
        serializer.save(owner=self.request.user)
    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def approve(self, request, pk=None):
        vendor = self.get_object()
        vendor.is_approved, vendor.is_suspended = True, False
        vendor.save(update_fields=['is_approved', 'is_suspended'])
        AuditLog.objects.create(actor=request.user, action='vendor.approved', object_type='Vendor', object_id=str(vendor.pk))
        return Response({'status': 'approved'})
    @action(detail=True, methods=['post'], permission_classes=[IsAdminUser])
    def suspend(self, request, pk=None):
        vendor = self.get_object()
        vendor.is_suspended = True
        vendor.save(update_fields=['is_suspended'])
        AuditLog.objects.create(actor=request.user, action='vendor.suspended', object_type='Vendor', object_id=str(vendor.pk))
        return Response({'status': 'suspended'})

class VendorDashboardView(APIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        vendor = getattr(request.user, 'vendor_profile', None)
        if not vendor:
            raise PermissionDenied('Vendor account required.')
        products = Product.objects.filter(vendor=vendor)
        lines = OrderItem.objects.filter(product__vendor=vendor).exclude(order__status=Order.Status.CANCELLED)
        return Response({
            'store': VendorSerializer(vendor).data,
            'approval_status': 'suspended' if vendor.is_suspended else ('approved' if vendor.is_approved else 'pending'),
            'product_count': products.count(),
            'active_product_count': products.filter(is_active=True).count(),
            'units_in_stock': products.aggregate(total=Sum('stock'))['total'] or 0,
            'order_line_count': lines.count(),
            'units_ordered': lines.aggregate(total=Sum('quantity'))['total'] or 0,
        })

class VendorOrderListView(generics.ListAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        vendor = getattr(self.request.user, 'vendor_profile', None)
        if not vendor:
            raise PermissionDenied('Vendor account required.')
        return Order.objects.filter(items__product__vendor=vendor).distinct().prefetch_related('items').order_by('-created_at')

class OrderCreateView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        serializer = CreateOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        with transaction.atomic():
            existing = Order.objects.filter(idempotency_key=data['idempotency_key']).first()
            if existing:
                if existing.buyer_id != request.user.id:
                    return Response({'detail': 'Idempotency key already used.'}, status=409)
                return Response(OrderSerializer(existing).data, status=200)
            order = Order.objects.create(buyer=request.user, shipping_address=data['shipping_address'], idempotency_key=data['idempotency_key'])
            for line in data['items']:
                try:
                    product = Product.objects.select_for_update().select_related('vendor').get(
                        pk=line['product_id'], is_active=True,
                        vendor__is_approved=True, vendor__is_suspended=False)
                except Product.DoesNotExist:
                    raise ValidationError({'items': f"Product {line['product_id']} is unavailable."})
                if product.stock < line['quantity']:
                    raise ValidationError({'items': f"Insufficient stock for {product.name}."})
                product.stock -= line['quantity']
                product.save(update_fields=['stock', 'updated_at'])
                OrderItem.objects.create(order=order, product=product, product_name=product.name, unit_price=product.price, quantity=line['quantity'])
                InventoryMovement.objects.create(product=product, quantity_delta=-line['quantity'], reason=f'Order {order.id}')
            AuditLog.objects.create(actor=request.user, action='order.placed', object_type='Order', object_id=str(order.pk))
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

class OrderListView(generics.ListAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        qs = Order.objects.prefetch_related('items').order_by('-created_at')
        return qs if self.request.user.is_staff else qs.filter(buyer=self.request.user)

class OrderCancelView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request, pk):
        with transaction.atomic():
            try:
                order = Order.objects.select_for_update().get(pk=pk)
            except Order.DoesNotExist:
                return Response({'detail': 'Order not found.'}, status=404)
            if not request.user.is_staff and order.buyer_id != request.user.id:
                raise PermissionDenied('You cannot cancel this order.')
            if order.status not in (Order.Status.PLACED, Order.Status.CONFIRMED):
                return Response({'detail': 'Only placed or confirmed orders can be cancelled.'}, status=409)
            for item in order.items.select_related('product').all():
                product = Product.objects.select_for_update().get(pk=item.product_id)
                product.stock += item.quantity
                product.save(update_fields=['stock', 'updated_at'])
                InventoryMovement.objects.create(product=product, quantity_delta=item.quantity, reason=f'Cancellation {order.id}')
            order.status = Order.Status.CANCELLED
            order.save(update_fields=['status'])
            AuditLog.objects.create(actor=request.user, action='order.cancelled', object_type='Order', object_id=str(order.pk))
        return Response(OrderSerializer(order).data)

class VendorOrderStatusView(APIView):
    permission_classes = [IsAuthenticated]
    transitions = {
        Order.Status.PLACED: {Order.Status.CONFIRMED, Order.Status.CANCELLED},
        Order.Status.CONFIRMED: {Order.Status.PACKED, Order.Status.CANCELLED},
        Order.Status.PACKED: {Order.Status.SHIPPED},
        Order.Status.SHIPPED: {Order.Status.DELIVERED},
    }
    def patch(self, request, pk):
        vendor = getattr(request.user, 'vendor_profile', None)
        if not request.user.is_staff and not vendor:
            raise PermissionDenied('Vendor account required.')
        new_status = request.data.get('status')
        if new_status not in Order.Status.values:
            raise ValidationError({'status': 'Invalid order status.'})
        with transaction.atomic():
            try:
                order = Order.objects.select_for_update().get(pk=pk)
            except Order.DoesNotExist:
                return Response({'detail': 'Order not found.'}, status=404)
            if not request.user.is_staff and not order.items.filter(product__vendor=vendor).exists():
                raise PermissionDenied('This order does not contain your products.')
            if new_status not in self.transitions.get(order.status, set()):
                return Response({'detail': f'Invalid transition: {order.status} to {new_status}.'}, status=409)
            if not request.user.is_staff and order.items.exclude(product__vendor=vendor).exists():
                return Response({'detail': 'Multi-vendor orders require vendor-specific fulfillment before global status changes.'}, status=409)
            order.status = new_status
            order.save(update_fields=['status'])
            AuditLog.objects.create(actor=request.user, action='order.status_changed', object_type='Order', object_id=str(order.pk), details={'status': new_status})
        return Response(OrderSerializer(order).data)


class AdminDashboardView(APIView):
    permission_classes = [IsAdminUser]
    def get(self, request):
        from django.contrib.auth import get_user_model
        UserModel = get_user_model()
        return Response({
            'users': UserModel.objects.count(),
            'vendors_total': Vendor.objects.count(),
            'vendors_pending': Vendor.objects.filter(is_approved=False, is_suspended=False).count(),
            'vendors_approved': Vendor.objects.filter(is_approved=True, is_suspended=False).count(),
            'vendors_suspended': Vendor.objects.filter(is_suspended=True).count(),
            'products': Product.objects.count(),
            'active_products': Product.objects.filter(is_active=True).count(),
            'orders': Order.objects.count(),
            'orders_open': Order.objects.exclude(status__in=[Order.Status.DELIVERED, Order.Status.CANCELLED]).count(),
            'recent_audit': list(AuditLog.objects.select_related('actor').order_by('-created_at').values('id','actor__username','action','object_type','object_id','created_at')[:12]),
        })

class AdminOrderStatusView(APIView):
    permission_classes = [IsAdminUser]
    allowed = set(Order.Status.values)
    def patch(self, request, pk):
        new_status = request.data.get('status')
        if new_status not in self.allowed:
            raise ValidationError({'status': 'Invalid order status.'})
        with transaction.atomic():
            try:
                order = Order.objects.select_for_update().get(pk=pk)
            except Order.DoesNotExist:
                return Response({'detail': 'Order not found.'}, status=404)
            old_status = order.status
            if old_status == Order.Status.CANCELLED and new_status != Order.Status.CANCELLED:
                return Response({'detail': 'Cancelled orders cannot be reopened.'}, status=409)
            if old_status == Order.Status.DELIVERED and new_status != Order.Status.DELIVERED:
                return Response({'detail': 'Delivered orders cannot be moved backwards.'}, status=409)
            if new_status == Order.Status.CANCELLED and old_status != Order.Status.CANCELLED:
                for item in order.items.all():
                    product = Product.objects.select_for_update().get(pk=item.product_id)
                    product.stock += item.quantity
                    product.save(update_fields=['stock', 'updated_at'])
                    InventoryMovement.objects.create(product=product, quantity_delta=item.quantity, reason=f'Admin cancellation {order.id}')
            order.status = new_status
            order.save(update_fields=['status'])
            AuditLog.objects.create(actor=request.user, action='admin.order_status_changed', object_type='Order', object_id=str(order.pk), details={'from': old_status, 'to': new_status})
        return Response(OrderSerializer(order).data)

class AdminAuditLogView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    def get_queryset(self):
        return AuditLog.objects.select_related('actor').order_by('-created_at')
    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()[:100]
        return Response([{'id':x.id,'actor':x.actor.username if x.actor else None,'action':x.action,'object_type':x.object_type,'object_id':x.object_id,'details':x.details,'created_at':x.created_at} for x in qs])
