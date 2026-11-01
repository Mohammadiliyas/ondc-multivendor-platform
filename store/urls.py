from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from . import views
from .api_views import RegisterView, CategoryViewSet, ProductViewSet, VendorViewSet, VendorDashboardView, VendorOrderListView, OrderCreateView, OrderListView, OrderCancelView, VendorOrderStatusView, AdminDashboardView, AdminOrderStatusView, AdminAuditLogView, VendorFulfillmentListView, VendorFulfillmentStatusView, RazorpayCreateOrderView, RazorpayVerifyPaymentView, RazorpayWebhookView, AdminCreateRefundView, VendorSettlementListView, AdminMarkSettlementPaidView, AdminCreateRefundView, VendorSettlementListView, AdminMarkSettlementPaidView

router = DefaultRouter()
router.register('categories', CategoryViewSet, basename='category')
router.register('products', ProductViewSet, basename='product')
router.register('vendors', VendorViewSet, basename='vendor')

urlpatterns = [
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('dashboard/vendor/', VendorDashboardView.as_view(), name='vendor-dashboard'),
    path('admin/dashboard/', AdminDashboardView.as_view(), name='admin-dashboard'),
    path('admin/audit-logs/', AdminAuditLogView.as_view(), name='admin-audit-logs'),
    path('admin/orders/<int:pk>/status/', AdminOrderStatusView.as_view(), name='admin-order-status'),
    path('vendor/orders/', VendorOrderListView.as_view(), name='vendor-orders'),
    path('vendor/fulfillments/', VendorFulfillmentListView.as_view(), name='vendor-fulfillments'),
    path('vendor/fulfillments/<int:pk>/status/', VendorFulfillmentStatusView.as_view(), name='vendor-fulfillment-status'),
    path('vendor/orders/<int:pk>/status/', VendorOrderStatusView.as_view(), name='vendor-order-status'),
    path('orders/create/', OrderCreateView.as_view(), name='order-create'),
    path('orders/<int:pk>/payments/razorpay/', RazorpayCreateOrderView.as_view(), name='razorpay-create-order'),
    path('payments/razorpay/verify/', RazorpayVerifyPaymentView.as_view(), name='razorpay-verify'),
    path('payments/razorpay/webhook/', RazorpayWebhookView.as_view(), name='razorpay-webhook'),
    path('admin/payments/<int:payment_id>/refund/', AdminCreateRefundView.as_view(), name='admin-payment-refund'),
    path('vendor/settlements/', VendorSettlementListView.as_view(), name='vendor-settlements'),
    path('admin/settlements/<int:pk>/mark-paid/', AdminMarkSettlementPaidView.as_view(), name='admin-settlement-mark-paid'),
    path('admin/payments/<int:payment_id>/refund/', AdminCreateRefundView.as_view(), name='admin-payment-refund'),
    path('vendor/settlements/', VendorSettlementListView.as_view(), name='vendor-settlements'),
    path('admin/settlements/<int:pk>/mark-paid/', AdminMarkSettlementPaidView.as_view(), name='admin-settlement-mark-paid'),
    path('orders/', OrderListView.as_view(), name='order-list'),
    path('orders/<int:pk>/cancel/', OrderCancelView.as_view(), name='order-cancel'),
    path('', include(router.urls)),
    path('catalog/', views.catalog, name='catalog'),
    path('ondc/catalog/', views.ondc_catalog, name='ondc-catalog'),
]
