from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.contrib.auth.hashers import make_password, check_password
from datetime import timedelta
import secrets, json as json_module
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
from django.conf import settings
from django.utils import timezone
from decimal import Decimal
import hashlib, hmac, json
import razorpay
from django.db import transaction
from django.db.models import Sum
from rest_framework import generics, viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied, ValidationError
from .models import Vendor, Category, Product, Order, OrderItem, InventoryMovement, AuditLog, VendorFulfillment, PaymentRecord, PaymentWebhookEvent, RefundRecord, VendorSettlement, UserVerification, SignupOTP
from .serializers import RegisterSerializer, VendorSerializer, CategorySerializer, ProductSerializer, CreateOrderSerializer, OrderSerializer, VendorFulfillmentSerializer


def _deliver_signup_otp(user, channel, code):
    if channel == 'email':
        if not settings.EMAIL_HOST or not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
            raise RuntimeError('Email OTP is not configured. Set SMTP environment variables.')
        sent = send_mail(
            'Your MarketLane verification code',
            f'Your MarketLane email verification code is {code}. It expires in {settings.OTP_EXPIRY_MINUTES} minutes. Do not share this code.',
            settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False,
        )
        if sent != 1:
            raise RuntimeError('Email OTP delivery failed.')
        return
    if not settings.MSG91_AUTH_KEY or not settings.MSG91_TEMPLATE_ID:
        raise RuntimeError('SMS OTP is not configured. Set MSG91_AUTH_KEY and MSG91_TEMPLATE_ID.')
    phone = user.verification.phone
    payload = json.dumps({
        'template_id': settings.MSG91_TEMPLATE_ID,
        'recipients': [{
            'mobiles': phone.lstrip('+'),
            'var1': code,
        }],
    }).encode('utf-8')
    request = Request(
        'https://control.msg91.com/api/v5/flow/',
        data=payload,
        headers={'Content-Type': 'application/json', 'authkey': settings.MSG91_AUTH_KEY},
        method='POST',
    )
    try:
        with urlopen(request, timeout=12) as response:
            result = json.loads(response.read().decode('utf-8'))
            if response.status >= 300 or str(result.get('type', '')).lower() == 'error':
                raise RuntimeError('SMS provider rejected the OTP request.')
    except (HTTPError, URLError, TimeoutError, ValueError) as exc:
        raise RuntimeError('SMS OTP delivery failed. Check MSG91 configuration.') from exc


def _issue_signup_otps(user, enforce_cooldown=True, channels=None):
    if SignupOTP.objects.filter(user=user, created_at__gte=timezone.now() - timedelta(hours=24)).count() >= 10:
        raise ValidationError({'detail': 'OTP request limit reached. Try again after 24 hours.'})
    latest = {}
    for row in SignupOTP.objects.filter(user=user, verified_at__isnull=True).order_by('channel', '-created_at'):
        latest.setdefault(row.channel, row)
    if enforce_cooldown and latest:
        recent = max(row.created_at for row in latest.values())
        wait = settings.OTP_RESEND_SECONDS - int((timezone.now() - recent).total_seconds())
        if wait > 0:
            raise ValidationError({'detail': f'Wait {wait} seconds before requesting new OTPs.'})
    if channels is None:
        channels = ['sms'] if not user.verification.phone_verified else ['email']
    codes = {channel: f'{secrets.randbelow(1000000):06d}' for channel in channels}
    expires = timezone.now() + timedelta(minutes=settings.OTP_EXPIRY_MINUTES)
    with transaction.atomic():
        for channel, code in codes.items():
            SignupOTP.objects.create(user=user, channel=channel, code_hash=make_password(code), expires_at=expires)
    failures = []
    for channel, code in codes.items():
        try:
            _deliver_signup_otp(user, channel, code)
        except Exception as exc:
            failures.append(f'{channel}: {str(exc)}')
    if failures:
        raise RuntimeError('OTP delivery incomplete. ' + ' '.join(failures))
    return True


class RegisterView(generics.GenericAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny]
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        try:
            _issue_signup_otps(user, enforce_cooldown=False)
        except Exception as exc:
            return Response({
                'detail': 'Your account is pending verification, but OTP delivery was not completed. Check server email/SMS configuration and request OTPs again.',
                'delivery_error': str(exc),
                'username': user.username,
            }, status=503)
        return Response({
            'detail': 'Mobile verification code sent. Verify your mobile number first; email verification comes next.',
            'username': user.username,
            'expires_in_seconds': settings.OTP_EXPIRY_MINUTES * 60,
        }, status=status.HTTP_201_CREATED)


class ResendSignupOTPView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        username = str(request.data.get('username', '')).strip()
        user = User.objects.filter(username=username, is_active=False).first()
        if not user:
            return Response({'detail': 'Pending signup account not found.'}, status=404)
        if not hasattr(user, 'verification') or user.verification.is_verified:
            return Response({'detail': 'This account does not require verification.'}, status=400)
        try:
            _issue_signup_otps(user)
        except ValidationError:
            raise
        except Exception as exc:
            return Response({'detail': 'OTP delivery failed. Check email/SMS provider configuration.', 'delivery_error': str(exc)}, status=503)
        return Response({'detail': 'A new verification OTP has been sent to the next required channel.', 'expires_in_seconds': settings.OTP_EXPIRY_MINUTES * 60})


class VerifySignupOTPView(APIView):
    permission_classes = [AllowAny]
    def post(self, request):
        username = str(request.data.get('username', '')).strip()
        email_code = str(request.data.get('email_otp', '')).strip()
        sms_code = str(request.data.get('sms_otp', '')).strip()
        if not username:
            raise ValidationError({'detail': 'Username is required.'})
        user = User.objects.filter(username=username, is_active=False).first()
        if not user:
            return Response({'detail': 'Pending signup account not found.'}, status=404)
        verification = getattr(user, 'verification', None)
        if not verification:
            return Response({'detail': 'Signup verification record not found.'}, status=400)
        errors = {}
        with transaction.atomic():
            required_channel = 'sms' if not verification.phone_verified else 'email'
            for channel, supplied in ((required_channel, (sms_code or email_code)),):
                if (channel == 'email' and verification.email_verified) or (channel == 'sms' and verification.phone_verified):
                    continue
                if not supplied:
                    errors[channel] = 'OTP is required.'
                    continue
                challenge = SignupOTP.objects.select_for_update().filter(
                    user=user, channel=channel, verified_at__isnull=True
                ).order_by('-created_at').first()
                if not challenge:
                    errors[channel] = 'Request a new OTP.'
                elif challenge.expires_at <= timezone.now():
                    errors[channel] = 'OTP expired. Request a new one.'
                elif challenge.attempts >= settings.OTP_MAX_ATTEMPTS:
                    errors[channel] = 'Maximum attempts reached. Request a new OTP.'
                elif not check_password(supplied, challenge.code_hash):
                    challenge.attempts += 1
                    challenge.save(update_fields=['attempts'])
                    errors[channel] = 'Incorrect OTP.'
                else:
                    challenge.verified_at = timezone.now()
                    challenge.save(update_fields=['verified_at'])
                    if channel == 'email':
                        verification.email_verified = True
                    else:
                        verification.phone_verified = True
            verification.save(update_fields=['email_verified', 'phone_verified'])
            if errors:
                return Response({'detail': 'One or both OTPs could not be verified.', 'errors': errors}, status=400)
            if verification.phone_verified and not verification.email_verified:
                next_channel = 'email'
            else:
                next_channel = None
            if verification.is_verified:
                user.is_active = True
                user.save(update_fields=['is_active'])
        if next_channel == 'email':
            try:
                _issue_signup_otps(user, enforce_cooldown=False, channels=['email'])
            except Exception:
                return Response({'detail': 'Mobile verified, but email OTP delivery failed. Use resend to retry email verification.'}, status=503)
            return Response({'detail': 'Mobile verified. We have now sent an OTP to your email address. Verify your email to activate the account.'})
        return Response({'detail': 'Mobile and email verified. Your account is active. Sign in using your mobile number and password.'})



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
    serializer_class = VendorFulfillmentSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        vendor = getattr(self.request.user, 'vendor_profile', None)
        if not vendor or vendor.is_suspended or not vendor.is_approved:
            raise PermissionDenied('An approved, active vendor account is required.')
        return VendorFulfillment.objects.filter(vendor=vendor, order__payments__provider='razorpay', order__payments__status=PaymentRecord.Status.PAID).select_related('order','order__buyer','vendor').prefetch_related('order__items').distinct().order_by('-created_at')

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
            vendor_ids = order.items.values_list('product__vendor_id', flat=True).distinct()
            for vendor_id in vendor_ids:
                VendorFulfillment.objects.create(order=order, vendor_id=vendor_id)
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
            if order.payments.filter(status__in=[PaymentRecord.Status.PAID, PaymentRecord.Status.AUTHORIZED]).exists():
                return Response({'detail':'This order has an authorized or captured payment. A refund must be processed before cancellation.'}, status=409)
            if order.vendor_fulfillments.exclude(status__in=[VendorFulfillment.Status.PENDING, VendorFulfillment.Status.CONFIRMED]).exists():
                return Response({'detail': 'Cancellation is blocked because at least one vendor has started packing or shipping.'}, status=409)
            for item in order.items.select_related('product').all():
                product = Product.objects.select_for_update().get(pk=item.product_id)
                product.stock += item.quantity
                product.save(update_fields=['stock', 'updated_at'])
                InventoryMovement.objects.create(product=product, quantity_delta=item.quantity, reason=f'Cancellation {order.id}')
            order.status = Order.Status.CANCELLED
            order.save(update_fields=['status'])
            order.vendor_fulfillments.update(status=VendorFulfillment.Status.CANCELLED)
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
            status_map = {Order.Status.PLACED: VendorFulfillment.Status.PENDING, Order.Status.CONFIRMED: VendorFulfillment.Status.CONFIRMED, Order.Status.PACKED: VendorFulfillment.Status.PACKED, Order.Status.SHIPPED: VendorFulfillment.Status.SHIPPED, Order.Status.DELIVERED: VendorFulfillment.Status.DELIVERED, Order.Status.CANCELLED: VendorFulfillment.Status.CANCELLED}
            order.vendor_fulfillments.update(status=status_map[new_status])
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
            'payments_captured_inr': str(PaymentRecord.objects.filter(status__in=[PaymentRecord.Status.PAID, PaymentRecord.Status.REFUNDED]).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')),
            'refunds_processed_inr': str(RefundRecord.objects.filter(status=RefundRecord.Status.PROCESSED).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')),
            'settlements_ready_count': VendorSettlement.objects.filter(status=VendorSettlement.Status.READY).count(),
            'settlements_held_count': VendorSettlement.objects.filter(status=VendorSettlement.Status.HELD).count(),
            'settlements_paid_inr': str(VendorSettlement.objects.filter(status=VendorSettlement.Status.PAID).aggregate(total=Sum('net_amount'))['total'] or Decimal('0.00')),
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
                if order.payments.filter(status__in=[PaymentRecord.Status.PAID, PaymentRecord.Status.AUTHORIZED]).exists():
                    return Response({'detail':'A payment refund or reversal is required before cancelling this order.'}, status=409)
                if order.vendor_fulfillments.exclude(status__in=[VendorFulfillment.Status.PENDING, VendorFulfillment.Status.CONFIRMED]).exists():
                    return Response({'detail': 'Cancellation is blocked because a vendor has started packing or shipping.'}, status=409)
                for item in order.items.all():
                    product = Product.objects.select_for_update().get(pk=item.product_id)
                    product.stock += item.quantity
                    product.save(update_fields=['stock', 'updated_at'])
                    InventoryMovement.objects.create(product=product, quantity_delta=item.quantity, reason=f'Admin cancellation {order.id}')
            order.status = new_status
            order.save(update_fields=['status'])
            if new_status == Order.Status.CANCELLED:
                order.vendor_fulfillments.update(status=VendorFulfillment.Status.CANCELLED)
            AuditLog.objects.create(actor=request.user, action='admin.order_status_changed', object_type='Order', object_id=str(order.pk), details={'from': old_status, 'to': new_status})
        return Response(OrderSerializer(order).data)

class AdminAuditLogView(generics.ListAPIView):
    permission_classes = [IsAdminUser]
    def get_queryset(self):
        return AuditLog.objects.select_related('actor').order_by('-created_at')
    def list(self, request, *args, **kwargs):
        qs = self.get_queryset()[:100]
        return Response([{'id':x.id,'actor':x.actor.username if x.actor else None,'action':x.action,'object_type':x.object_type,'object_id':x.object_id,'details':x.details,'created_at':x.created_at} for x in qs])


class VendorFulfillmentListView(generics.ListAPIView):
    serializer_class = VendorFulfillmentSerializer
    permission_classes = [IsAuthenticated]
    def get_queryset(self):
        vendor = getattr(self.request.user, 'vendor_profile', None)
        if not vendor or vendor.is_suspended or not vendor.is_approved:
            raise PermissionDenied('An approved, active vendor account is required.')
        return VendorFulfillment.objects.filter(vendor=vendor).select_related('order','order__buyer','vendor').prefetch_related('order__items').order_by('-created_at')

class VendorFulfillmentStatusView(APIView):
    permission_classes = [IsAuthenticated]
    transitions = {
        VendorFulfillment.Status.PENDING: {VendorFulfillment.Status.CONFIRMED, VendorFulfillment.Status.CANCELLED},
        VendorFulfillment.Status.CONFIRMED: {VendorFulfillment.Status.PACKED, VendorFulfillment.Status.CANCELLED},
        VendorFulfillment.Status.PACKED: {VendorFulfillment.Status.SHIPPED},
        VendorFulfillment.Status.SHIPPED: {VendorFulfillment.Status.DELIVERED},
    }
    def patch(self, request, pk):
        vendor = getattr(request.user, 'vendor_profile', None)
        if not vendor or vendor.is_suspended or not vendor.is_approved:
            raise PermissionDenied('An approved, active vendor account is required.')
        new_status = request.data.get('status')
        if new_status not in VendorFulfillment.Status.values:
            raise ValidationError({'status': 'Invalid fulfillment status.'})
        with transaction.atomic():
            try:
                fulfillment = VendorFulfillment.objects.select_for_update().select_related('order','vendor').get(pk=pk, vendor=vendor)
            except VendorFulfillment.DoesNotExist:
                return Response({'detail': 'Fulfillment not found.'}, status=404)
            if new_status not in self.transitions.get(fulfillment.status, set()):
                return Response({'detail': f'Invalid transition: {fulfillment.status} to {new_status}.'}, status=409)
            if not fulfillment.order.payments.filter(provider='razorpay', status=PaymentRecord.Status.PAID).exists():
                return Response({'detail':'Vendor fulfilment is locked until the buyer payment is captured and verified.'}, status=409)
            if new_status == VendorFulfillment.Status.CANCELLED:
                return Response({'detail': 'Contact platform support to cancel an individual vendor shipment. Buyer cancellation is handled at order level.'}, status=409)
            fulfillment.status = new_status
            if 'tracking_reference' in request.data:
                fulfillment.tracking_reference = str(request.data['tracking_reference'])[:180]
            fulfillment.save(update_fields=['status','tracking_reference','updated_at'])
            if new_status == VendorFulfillment.Status.DELIVERED:
                vendor_gross = sum((item.unit_price * item.quantity for item in fulfillment.order.items.filter(product__vendor=vendor)), start=Decimal('0.00')).quantize(Decimal('0.01'))
                fee_rate = Decimal(str(getattr(settings, 'PLATFORM_COMMISSION_PERCENT', 10)))
                if fee_rate < Decimal('0') or fee_rate > Decimal('100'):
                    raise ValidationError({'commission':'PLATFORM_COMMISSION_PERCENT must be between 0 and 100.'})
                fee = (vendor_gross * fee_rate / Decimal('100')).quantize(Decimal('0.01'))
                has_refund = fulfillment.order.payments.filter(refunds__status=RefundRecord.Status.PROCESSED).exists()
                VendorSettlement.objects.get_or_create(
                    order=fulfillment.order, vendor=vendor,
                    defaults={
                        'gross_amount':vendor_gross, 'platform_fee':fee,
                        'net_amount':vendor_gross-fee,
                        'status':VendorSettlement.Status.HELD if has_refund else VendorSettlement.Status.READY
                    }
                )
            rows = list(fulfillment.order.vendor_fulfillments.values_list('status', flat=True))
            if rows and all(value == VendorFulfillment.Status.DELIVERED for value in rows):
                fulfillment.order.status = Order.Status.DELIVERED
            elif rows and all(value in [VendorFulfillment.Status.SHIPPED, VendorFulfillment.Status.DELIVERED] for value in rows):
                fulfillment.order.status = Order.Status.SHIPPED
            elif rows and all(value in [VendorFulfillment.Status.PACKED, VendorFulfillment.Status.SHIPPED, VendorFulfillment.Status.DELIVERED] for value in rows):
                fulfillment.order.status = Order.Status.PACKED
            elif rows and all(value in [VendorFulfillment.Status.CONFIRMED, VendorFulfillment.Status.PACKED, VendorFulfillment.Status.SHIPPED, VendorFulfillment.Status.DELIVERED] for value in rows):
                fulfillment.order.status = Order.Status.CONFIRMED
            fulfillment.order.save(update_fields=['status'])
            AuditLog.objects.create(actor=request.user, action='vendor.fulfillment_status_changed', object_type='VendorFulfillment', object_id=str(fulfillment.pk), details={'status':new_status,'order_id':fulfillment.order_id})
        return Response(VendorFulfillmentSerializer(fulfillment).data)


class RazorpayCreateOrderView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request, pk):
        if settings.RAZORPAY_MODE == 'test' and not settings.RAZORPAY_KEY_ID.startswith('rzp_test_'):
            return Response({'detail':'Razorpay is locked to test mode. Configure an rzp_test_ Key ID and matching test Key Secret.'}, status=503)
        if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
            return Response({'detail':'Razorpay is not configured. Add test credentials to the server environment.'}, status=503)
        try:
            order = Order.objects.prefetch_related('items').get(pk=pk, buyer=request.user)
        except Order.DoesNotExist:
            return Response({'detail':'Order not found.'}, status=404)
        if order.status == Order.Status.CANCELLED:
            return Response({'detail':'Cancelled orders cannot be paid.'}, status=409)
        amount = sum((item.unit_price * item.quantity for item in order.items.all()), start=Decimal('0.00')).quantize(Decimal('0.01'))
        if amount <= 0:
            return Response({'detail':'Order amount must be greater than zero.'}, status=400)
        payment = PaymentRecord.objects.filter(order=order, provider='razorpay').first()
        if payment and payment.status == PaymentRecord.Status.PAID:
            return Response({'detail':'This order is already paid.'}, status=409)
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        if payment and payment.razorpay_order_id:
            rp_order_id = payment.razorpay_order_id
        else:
            try:
                rp_order = client.order.create(data={
                    'amount': int(amount * 100), 'currency': settings.RAZORPAY_CURRENCY,
                    'receipt': f'market-{order.pk}', 'notes': {'marketplace_order_id': str(order.pk)}
                })
            except Exception:
                return Response({'detail':'Unable to create Razorpay order. Check server credentials and gateway configuration.'}, status=502)
            rp_order_id = rp_order['id']
            if payment is None:
                payment = PaymentRecord.objects.create(order=order, provider='razorpay', amount=amount, currency=settings.RAZORPAY_CURRENCY, razorpay_order_id=rp_order_id)
            else:
                payment.amount=amount
                payment.currency=settings.RAZORPAY_CURRENCY
                payment.razorpay_order_id=rp_order_id
                payment.status=PaymentRecord.Status.PENDING
                payment.save(update_fields=['amount','currency','razorpay_order_id','status','updated_at'])
        return Response({
            'key_id': settings.RAZORPAY_KEY_ID, 'razorpay_order_id': rp_order_id,
            'amount': int(amount * 100), 'currency': settings.RAZORPAY_CURRENCY,
            'payment_record_id': payment.pk, 'order_id': order.pk,
            'name': 'MarketLane Marketplace', 'description': f'Payment for order #{order.pk}'
        }, status=200)


class RazorpayVerifyPaymentView(APIView):
    permission_classes = [IsAuthenticated]
    def post(self, request):
        order_id = request.data.get('razorpay_order_id')
        payment_id = request.data.get('razorpay_payment_id')
        signature = request.data.get('razorpay_signature')
        if not all([order_id, payment_id, signature]):
            raise ValidationError({'detail':'Missing Razorpay payment verification fields.'})
        try:
            payment = PaymentRecord.objects.select_related('order').get(razorpay_order_id=order_id, order__buyer=request.user)
        except PaymentRecord.DoesNotExist:
            return Response({'detail':'Payment record not found.'}, status=404)
        if not settings.RAZORPAY_KEY_SECRET:
            return Response({'detail':'Razorpay is not configured.'}, status=503)
        expected = hmac.new(settings.RAZORPAY_KEY_SECRET.encode(), f'{order_id}|{payment_id}'.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, str(signature)):
            return Response({'detail':'Invalid Razorpay payment signature.'}, status=400)
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        try:
            gateway_payment = client.payment.fetch(payment_id)
        except Exception:
            return Response({'detail':'Could not verify payment status with Razorpay. The webhook will reconcile the final state.'}, status=502)
        if gateway_payment.get('order_id') != order_id:
            return Response({'detail':'Payment does not belong to this Razorpay order.'}, status=400)
        if int(gateway_payment.get('amount', -1)) != int(payment.amount * 100) or gateway_payment.get('currency') != payment.currency:
            return Response({'detail':'Payment amount or currency mismatch.'}, status=400)
        gateway_status = gateway_payment.get('status')
        if gateway_status not in ('authorized','captured'):
            return Response({'detail':f'Payment is not successful (gateway status: {gateway_status}).'}, status=409)
        with transaction.atomic():
            payment = PaymentRecord.objects.select_for_update().get(pk=payment.pk)
            payment.razorpay_payment_id = payment_id
            payment.signature_verified = True
            payment.status = PaymentRecord.Status.PAID if gateway_status == 'captured' else PaymentRecord.Status.AUTHORIZED
            if gateway_status == 'captured':
                payment.paid_at = timezone.now()
            payment.save(update_fields=['razorpay_payment_id','signature_verified','status','paid_at','updated_at'])
            if payment.status == PaymentRecord.Status.PAID and payment.order.status == Order.Status.PLACED:
                payment.order.status = Order.Status.CONFIRMED
                payment.order.save(update_fields=['status'])
            AuditLog.objects.create(actor=request.user, action='payment.verified', object_type='PaymentRecord', object_id=str(payment.pk), details={'gateway_status':gateway_status})
        return Response({'status':payment.status,'order_id':payment.order_id})


class RazorpayWebhookView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    def post(self, request):
        secret = settings.RAZORPAY_WEBHOOK_SECRET
        signature = request.headers.get('X-Razorpay-Signature', '')
        event_id = request.headers.get('X-Razorpay-Event-Id', '')
        if not secret:
            return Response({'detail':'Webhook secret is not configured.'}, status=503)
        expected = hmac.new(secret.encode(), request.body, hashlib.sha256).hexdigest()
        if not signature or not hmac.compare_digest(expected, signature):
            return Response({'detail':'Invalid webhook signature.'}, status=400)
        if not event_id:
            return Response({'detail':'Missing Razorpay event ID.'}, status=400)
        try:
            payload = json.loads(request.body.decode('utf-8'))
            event_type = payload.get('event','')
            payment_entity = payload.get('payload',{}).get('payment',{}).get('entity',{})
            refund_entity = payload.get('payload',{}).get('refund',{}).get('entity',{})
            entity = payment_entity or refund_entity
            rp_order_id = entity.get('order_id')
            rp_payment_id = entity.get('id')
        except (ValueError, AttributeError):
            return Response({'detail':'Invalid webhook payload.'}, status=400)
        with transaction.atomic():
            event, created = PaymentWebhookEvent.objects.get_or_create(
                provider_event_id=event_id, defaults={'event_type':event_type}
            )
            if not created and event.processed:
                return Response({'status':'duplicate_ignored'})
            payment = PaymentRecord.objects.select_for_update().filter(razorpay_order_id=rp_order_id).first() if rp_order_id else None
            if payment:
                if event_type in ('payment.captured','order.paid'):
                    if int(entity.get('amount', -1)) != int(payment.amount * 100) or entity.get('currency') != payment.currency:
                        return Response({'detail':'Webhook payment amount or currency does not match the marketplace order.'}, status=400)
                    payment.status=PaymentRecord.Status.PAID
                    payment.razorpay_payment_id=rp_payment_id or payment.razorpay_payment_id
                    payment.signature_verified=True
                    payment.paid_at=timezone.now()
                    payment.save(update_fields=['status','razorpay_payment_id','signature_verified','paid_at','updated_at'])
                    if payment.order.status == Order.Status.PLACED:
                        payment.order.status=Order.Status.CONFIRMED
                        payment.order.save(update_fields=['status'])
                elif event_type == 'payment.failed' and payment.status not in (PaymentRecord.Status.PAID, PaymentRecord.Status.REFUNDED):
                    payment.status=PaymentRecord.Status.FAILED
                    payment.failure_reason=str(entity.get('error_description') or 'Payment failed')[:255]
                    payment.save(update_fields=['status','failure_reason','updated_at'])
                event.payment=payment
            if event_type in ('refund.processed','refund.failed'):
                refund_id = refund_entity.get('id')
                refund = RefundRecord.objects.select_for_update().filter(razorpay_refund_id=refund_id).first() if refund_id else None
                if refund:
                    if event_type == 'refund.processed' and int(refund_entity.get('amount', -1)) != int(refund.amount * 100):
                        return Response({'detail':'Refund webhook amount does not match the marketplace refund record.'}, status=400)
                    refund.status = RefundRecord.Status.PROCESSED if event_type == 'refund.processed' else RefundRecord.Status.FAILED
                    refund.save(update_fields=['status','updated_at'])
                    payment = refund.payment
                    if event_type == 'refund.processed':
                        total_refunded = payment.refunds.filter(status=RefundRecord.Status.PROCESSED).aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
                        if total_refunded >= payment.amount:
                            payment.status = PaymentRecord.Status.REFUNDED
                            payment.save(update_fields=['status','updated_at'])
                        payment.order.vendor_settlements.exclude(status=VendorSettlement.Status.PAID).update(status=VendorSettlement.Status.HELD)
                    elif not payment.refunds.exclude(status=RefundRecord.Status.FAILED).exists():
                        payment.order.vendor_settlements.filter(status=VendorSettlement.Status.HELD).update(status=VendorSettlement.Status.READY)
                    event.payment = payment
            event.processed=True
            event.save(update_fields=['processed','payment'])
        return Response({'status':'processed'})


class AdminCreateRefundView(APIView):
    permission_classes = [IsAdminUser]
    def post(self, request, payment_id):
        if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
            return Response({'detail':'Razorpay is not configured.'}, status=503)
        try:
            payment = PaymentRecord.objects.select_related('order').get(pk=payment_id)
        except PaymentRecord.DoesNotExist:
            return Response({'detail':'Payment not found.'}, status=404)
        if payment.status != PaymentRecord.Status.PAID or not payment.razorpay_payment_id:
            return Response({'detail':'Only captured payments can be refunded.'}, status=409)
        if payment.order.vendor_settlements.filter(status=VendorSettlement.Status.PAID).exists():
            return Response({'detail':'A vendor settlement has already been paid. Reconcile vendor recovery before issuing this refund.'}, status=409)
        existing = payment.refunds.exclude(status=RefundRecord.Status.FAILED).first()
        if existing:
            return Response({'id':existing.pk,'status':existing.status,'amount':str(existing.amount),'razorpay_refund_id':existing.razorpay_refund_id}, status=200)
        amount = payment.amount
        reason = str(request.data.get('reason','Customer refund'))[:255]
        with transaction.atomic():
            payment = PaymentRecord.objects.select_for_update().get(pk=payment.pk)
            existing = payment.refunds.exclude(status=RefundRecord.Status.FAILED).first()
            if existing:
                return Response({'id':existing.pk,'status':existing.status,'amount':str(existing.amount),'razorpay_refund_id':existing.razorpay_refund_id}, status=200)
            refund = RefundRecord.objects.create(payment=payment, amount=amount, status=RefundRecord.Status.PENDING, reason=reason)
            payment.order.vendor_settlements.exclude(status=VendorSettlement.Status.PAID).update(status=VendorSettlement.Status.HELD)
        client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
        try:
            gateway_refund = client.payment.refund(payment.razorpay_payment_id, {'amount':int(amount*100),'notes':{'marketplace_order_id':str(payment.order_id),'reason':reason}})
            refund.razorpay_refund_id = gateway_refund.get('id')
            refund.save(update_fields=['razorpay_refund_id','updated_at'])
        except Exception:
            refund.status = RefundRecord.Status.FAILED
            refund.save(update_fields=['status','updated_at'])
            payment.order.vendor_settlements.filter(status=VendorSettlement.Status.HELD).update(status=VendorSettlement.Status.READY)
            return Response({'detail':'Razorpay did not accept the refund request. Verify payment capture and gateway response.'}, status=502)
        AuditLog.objects.create(actor=request.user, action='payment.refund_requested', object_type='RefundRecord', object_id=str(refund.pk), details={'payment_id':payment.pk,'amount':str(amount)})
        return Response({'id':refund.pk,'status':refund.status,'amount':str(refund.amount),'razorpay_refund_id':refund.razorpay_refund_id}, status=201)


class VendorSettlementListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        vendor = getattr(request.user, 'vendor_profile', None)
        if not request.user.is_staff and not vendor:
            raise PermissionDenied('Vendor account required.')
        queryset = VendorSettlement.objects.select_related('order','vendor')
        if not request.user.is_staff:
            queryset = queryset.filter(vendor=vendor)
        data = [{
            'id':row.pk,'order_id':row.order_id,'vendor_id':row.vendor_id,
            'gross_amount':str(row.gross_amount),'platform_fee':str(row.platform_fee),
            'net_amount':str(row.net_amount),'status':row.status,
            'payout_reference':row.payout_reference,'paid_at':row.paid_at
        } for row in queryset.order_by('-created_at')]
        return Response(data)


class AdminMarkSettlementPaidView(APIView):
    permission_classes = [IsAdminUser]
    def post(self, request, pk):
        reference = str(request.data.get('payout_reference','')).strip()[:180]
        if not reference:
            raise ValidationError({'payout_reference':'A bank/UPI transfer reference is required.'})
        with transaction.atomic():
            try:
                row = VendorSettlement.objects.select_for_update().get(pk=pk)
            except VendorSettlement.DoesNotExist:
                return Response({'detail':'Settlement not found.'}, status=404)
            if row.status != VendorSettlement.Status.READY:
                return Response({'detail':'Only ready settlements can be marked paid.'}, status=409)
            row.status=VendorSettlement.Status.PAID
            row.payout_reference=reference
            row.paid_at=timezone.now()
            row.save(update_fields=['status','payout_reference','paid_at','updated_at'])
            AuditLog.objects.create(actor=request.user, action='vendor.settlement_marked_paid', object_type='VendorSettlement', object_id=str(row.pk), details={'reference':reference,'net_amount':str(row.net_amount)})
        return Response({'id':row.pk,'status':row.status,'payout_reference':row.payout_reference,'net_amount':str(row.net_amount)})
