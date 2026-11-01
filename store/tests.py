from django.test import TestCase, override_settings
from unittest.mock import patch
import hashlib, hmac, json
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from .models import Vendor, Category, Product, Order, OrderItem, InventoryMovement, VendorFulfillment, PaymentRecord, PaymentWebhookEvent

class MarketplaceAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.buyer = User.objects.create_user(username='buyer1', password='StrongPass123!')
        self.seller = User.objects.create_user(username='seller1', password='StrongPass123!')
        self.vendor = Vendor.objects.create(owner=self.seller, store_name='Seller Store', is_approved=True)
        self.category = Category.objects.create(name='General')
        self.product = Product.objects.create(vendor=self.vendor, category=self.category, name='Demo item', sku='DEMO-001', price='12.50', stock=5)
        self.admin = User.objects.create_superuser(username='admin1', email='admin@example.com', password='StrongPass123!')
    def auth(self, user):
        self.client.force_authenticate(user=user)
    def test_health_and_public_catalog(self):
        self.assertEqual(self.client.get('/api/health/').status_code, 200)
        self.assertEqual(len(self.client.get('/api/catalog/').json()['results']), 1)
    def test_registration_does_not_allow_privilege_escalation(self):
        response = self.client.post('/api/auth/register/', {'username':'newuser','password':'StrongPass123!','is_staff':True,'is_superuser':True}, format='json')
        self.assertEqual(response.status_code, 201)
        user = User.objects.get(username='newuser')
        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
    def test_vendor_cannot_create_product_before_approval(self):
        pending = User.objects.create_user(username='pending', password='StrongPass123!')
        Vendor.objects.create(owner=pending, store_name='Pending Store')
        self.auth(pending)
        response = self.client.post('/api/products/', {'name':'X','sku':'X-1','price':'1.00','stock':1}, format='json')
        self.assertEqual(response.status_code, 403)
    def test_vendor_product_isolation(self):
        other = User.objects.create_user(username='seller2', password='StrongPass123!')
        Vendor.objects.create(owner=other, store_name='Other Store', is_approved=True)
        self.auth(other)
        # Approved products are public; cross-vendor writes must still be blocked.
        self.assertEqual(len(self.client.get('/api/products/').json()), 1)
        response = self.client.patch(f'/api/products/{self.product.pk}/', {'price':'1.00'}, format='json')
        self.assertEqual(response.status_code, 404)
    def test_buyer_checkout_decrements_stock_and_snapshots_price(self):
        self.auth(self.buyer)
        response = self.client.post('/api/orders/create/', {'shipping_address':'12 Main Road, Hyderabad','idempotency_key':'order-test-1','items':[{'product_id':self.product.pk,'quantity':2}]}, format='json')
        self.assertEqual(response.status_code, 201)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 3)
        item = OrderItem.objects.get(order_id=response.json()['id'])
        self.assertEqual(str(item.unit_price), '12.50')
    def test_idempotent_checkout_does_not_decrement_twice(self):
        self.auth(self.buyer)
        payload={'shipping_address':'12 Main Road, Hyderabad','idempotency_key':'order-idem-1','items':[{'product_id':self.product.pk,'quantity':2}]}
        self.assertEqual(self.client.post('/api/orders/create/', payload, format='json').status_code, 201)
        self.assertEqual(self.client.post('/api/orders/create/', payload, format='json').status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 3)
    def test_buyer_cannot_view_another_buyers_orders(self):
        self.auth(self.buyer)
        Order.objects.create(buyer=self.seller, shipping_address='Another address', idempotency_key='other-order')
        self.assertEqual(len(self.client.get('/api/orders/').data), 0)
    def test_cancel_restores_inventory(self):
        self.auth(self.buyer)
        response=self.client.post('/api/orders/create/', {'shipping_address':'12 Main Road, Hyderabad','idempotency_key':'cancel-test','items':[{'product_id':self.product.pk,'quantity':2}]}, format='json')
        order_id=response.json()['id']
        self.assertEqual(self.client.post(f'/api/orders/{order_id}/cancel/').status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)
        self.assertEqual(InventoryMovement.objects.count(), 2)
    def test_vendor_dashboard_and_order_list_are_scoped(self):
        self.auth(self.buyer)
        self.assertEqual(self.client.get('/api/dashboard/vendor/').status_code, 403)
        self.auth(self.seller)
        self.assertEqual(self.client.get('/api/dashboard/vendor/').status_code, 200)
        self.assertEqual(self.client.get('/api/vendor/orders/').status_code, 200)
    def test_admin_can_approve_vendor(self):
        pending=User.objects.create_user(username='pending2', password='StrongPass123!')
        vendor=Vendor.objects.create(owner=pending, store_name='Pending')
        self.auth(self.admin)
        response=self.client.post(f'/api/vendors/{vendor.pk}/approve/')
        self.assertEqual(response.status_code, 200)
        vendor.refresh_from_db()
        self.assertTrue(vendor.is_approved)

    def test_admin_dashboard_is_staff_only(self):
        self.auth(self.buyer)
        self.assertEqual(self.client.get('/api/admin/dashboard/').status_code, 403)
        self.auth(self.admin)
        response = self.client.get('/api/admin/dashboard/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['vendors_total'], 1)
        self.assertEqual(response.data['products'], 1)

    def test_admin_can_manage_categories_and_read_audit_logs(self):
        self.auth(self.buyer)
        self.assertEqual(self.client.post('/api/categories/', {'name':'Blocked'}, format='json').status_code, 403)
        self.auth(self.admin)
        created = self.client.post('/api/categories/', {'name':'Electronics'}, format='json')
        self.assertEqual(created.status_code, 201)
        self.assertTrue(Category.objects.filter(name='Electronics').exists())
        self.assertEqual(self.client.get('/api/admin/audit-logs/').status_code, 200)

    def test_admin_can_cancel_order_and_restore_stock_once(self):
        self.auth(self.buyer)
        response = self.client.post('/api/orders/create/', {'shipping_address':'12 Main Road, Hyderabad','idempotency_key':'admin-cancel-test','items':[{'product_id':self.product.pk,'quantity':2}]}, format='json')
        order_id = response.data['id']
        self.auth(self.admin)
        changed = self.client.patch(f'/api/admin/orders/{order_id}/status/', {'status':'CANCELLED'}, format='json')
        self.assertEqual(changed.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)
        again = self.client.patch(f'/api/admin/orders/{order_id}/status/', {'status':'CANCELLED'}, format='json')
        self.assertEqual(again.status_code, 200)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 5)


    def test_multi_vendor_checkout_creates_isolated_fulfillments(self):
        seller_two = User.objects.create_user(username='seller_two', password='StrongPass123!')
        vendor_two = Vendor.objects.create(owner=seller_two, store_name='Second Store', is_approved=True)
        product_two = Product.objects.create(vendor=vendor_two, category=self.category, name='Second item', sku='DEMO-002', price='5.00', stock=4)
        self.auth(self.buyer)
        response = self.client.post('/api/orders/create/', {
            'shipping_address':'12 Main Road, Hyderabad',
            'idempotency_key':'multi-vendor-order-1',
            'items':[{'product_id':self.product.pk,'quantity':1},{'product_id':product_two.pk,'quantity':2}]
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(VendorFulfillment.objects.filter(order_id=response.data['id']).count(), 2)
        self.auth(self.seller)
        own = self.client.get('/api/vendor/fulfillments/')
        self.assertEqual(own.status_code, 200)
        self.assertEqual(len(own.data), 1)
        self.assertEqual(len(own.data[0]['items']), 1)
        self.assertEqual(own.data[0]['items'][0]['product'], self.product.pk)
        self.assertIn('shipping_address', own.data[0])
        self.assertNotIn('Second item', str(own.data[0]['items']))

    def test_vendor_cannot_read_or_update_another_vendors_fulfillment(self):
        seller_two = User.objects.create_user(username='seller_three', password='StrongPass123!')
        vendor_two = Vendor.objects.create(owner=seller_two, store_name='Third Store', is_approved=True)
        product_two = Product.objects.create(vendor=vendor_two, category=self.category, name='Third item', sku='DEMO-003', price='7.00', stock=3)
        self.auth(self.buyer)
        response = self.client.post('/api/orders/create/', {
            'shipping_address':'12 Main Road, Hyderabad',
            'idempotency_key':'multi-vendor-order-2',
            'items':[{'product_id':self.product.pk,'quantity':1},{'product_id':product_two.pk,'quantity':1}]
        }, format='json')
        self.assertEqual(response.status_code, 201)
        foreign = VendorFulfillment.objects.get(order_id=response.data['id'], vendor=vendor_two)
        self.auth(self.seller)
        denied = self.client.patch(f'/api/vendor/fulfillments/{foreign.pk}/status/', {'status':'CONFIRMED'}, format='json')
        self.assertEqual(denied.status_code, 404)

    def test_vendor_fulfillment_status_updates_parent_only_when_all_vendors_progress(self):
        self.auth(self.buyer)
        response = self.client.post('/api/orders/create/', {
            'shipping_address':'12 Main Road, Hyderabad',
            'idempotency_key':'single-vendor-fulfillment',
            'items':[{'product_id':self.product.pk,'quantity':1}]
        }, format='json')
        order_id = response.data['id']
        fulfillment = VendorFulfillment.objects.get(order_id=order_id, vendor=self.vendor)
        self.auth(self.seller)
        updated = self.client.patch(f'/api/vendor/fulfillments/{fulfillment.pk}/status/', {'status':'CONFIRMED'}, format='json')
        self.assertEqual(updated.status_code, 200)
        order = Order.objects.get(pk=order_id)
        self.assertEqual(order.status, Order.Status.CONFIRMED)


    def test_buyer_cannot_cancel_after_vendor_has_started_packing(self):
        self.auth(self.buyer)
        response = self.client.post('/api/orders/create/', {
            'shipping_address':'12 Main Road, Hyderabad',
            'idempotency_key':'no-cancel-after-pack',
            'items':[{'product_id':self.product.pk,'quantity':1}]
        }, format='json')
        fulfillment = VendorFulfillment.objects.get(order_id=response.data['id'], vendor=self.vendor)
        fulfillment.status = VendorFulfillment.Status.PACKED
        fulfillment.save(update_fields=['status'])
        denied = self.client.post(f'/api/orders/{response.data["id"]}/cancel/')
        self.assertEqual(denied.status_code, 409)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 4)

    def test_admin_cannot_cancel_after_vendor_has_started_shipping(self):
        self.auth(self.buyer)
        response = self.client.post('/api/orders/create/', {
            'shipping_address':'12 Main Road, Hyderabad',
            'idempotency_key':'admin-no-cancel-after-ship',
            'items':[{'product_id':self.product.pk,'quantity':1}]
        }, format='json')
        fulfillment = VendorFulfillment.objects.get(order_id=response.data['id'], vendor=self.vendor)
        fulfillment.status = VendorFulfillment.Status.SHIPPED
        fulfillment.save(update_fields=['status'])
        self.auth(self.admin)
        denied = self.client.patch(f'/api/admin/orders/{response.data["id"]}/status/', {'status':'CANCELLED'}, format='json')
        self.assertEqual(denied.status_code, 409)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock, 4)


    def _create_order_for_payment(self, key='payment-test-order'):
        self.auth(self.buyer)
        return self.client.post('/api/orders/create/', {
            'shipping_address':'12 Main Road, Hyderabad',
            'idempotency_key':key,
            'items':[{'product_id':self.product.pk,'quantity':2}]
        }, format='json')

    @override_settings(RAZORPAY_KEY_ID='', RAZORPAY_KEY_SECRET='')
    def test_razorpay_checkout_requires_server_credentials(self):
        order = self._create_order_for_payment()
        response = self.client.post(f'/api/orders/{order.data["id"]}/payments/razorpay/')
        self.assertEqual(response.status_code, 503)

    @override_settings(RAZORPAY_KEY_ID='rzp_test_demo', RAZORPAY_KEY_SECRET='test_secret')
    @patch('store.api_views.razorpay.Client')
    def test_razorpay_order_uses_server_calculated_amount(self, client_class):
        order = self._create_order_for_payment('payment-amount-test')
        client_class.return_value.order.create.return_value = {'id':'order_test_123'}
        response = self.client.post(f'/api/orders/{order.data["id"]}/payments/razorpay/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['amount'], 2500)
        self.assertEqual(response.data['currency'], 'INR')
        payment = PaymentRecord.objects.get(order_id=order.data['id'])
        self.assertEqual(payment.razorpay_order_id, 'order_test_123')
        self.assertEqual(str(payment.amount), '25.00')
        client_class.return_value.order.create.assert_called_once()

    @override_settings(RAZORPAY_KEY_ID='rzp_test_demo', RAZORPAY_KEY_SECRET='test_secret')
    def test_razorpay_verification_rejects_invalid_signature(self):
        order = self._create_order_for_payment('payment-bad-signature')
        PaymentRecord.objects.create(order_id=order.data['id'], amount='25.00', razorpay_order_id='order_bad_sig')
        response = self.client.post('/api/payments/razorpay/verify/', {
            'razorpay_order_id':'order_bad_sig',
            'razorpay_payment_id':'pay_fake',
            'razorpay_signature':'not-a-valid-signature'
        }, format='json')
        self.assertEqual(response.status_code, 400)

    @override_settings(RAZORPAY_WEBHOOK_SECRET='webhook_test_secret')
    def test_razorpay_webhook_requires_valid_signature(self):
        response = self.client.generic(
            'POST', '/api/payments/razorpay/webhook/', data=b'{"event":"payment.captured"}',
            content_type='application/json',
            HTTP_X_RAZORPAY_SIGNATURE='bad-signature',
            HTTP_X_RAZORPAY_EVENT_ID='evt_bad'
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(PaymentWebhookEvent.objects.count(), 0)

    @override_settings(RAZORPAY_WEBHOOK_SECRET='webhook_test_secret')
    def test_razorpay_captured_webhook_is_signed_and_idempotent(self):
        order = self._create_order_for_payment('payment-webhook-captured')
        payment = PaymentRecord.objects.create(order_id=order.data['id'], amount='25.00', razorpay_order_id='order_webhook')
        body = json.dumps({'event':'payment.captured','payload':{'payment':{'entity':{'id':'pay_captured','order_id':'order_webhook'}}}}).encode()
        signature = hmac.new(b'webhook_test_secret', body, hashlib.sha256).hexdigest()
        headers = {'content_type':'application/json','HTTP_X_RAZORPAY_SIGNATURE':signature,'HTTP_X_RAZORPAY_EVENT_ID':'evt_capture_1'}
        first = self.client.generic('POST','/api/payments/razorpay/webhook/',data=body,**headers)
        self.assertEqual(first.status_code, 200)
        payment.refresh_from_db()
        self.assertEqual(payment.status, PaymentRecord.Status.PAID)
        self.assertEqual(payment.razorpay_payment_id, 'pay_captured')
        self.assertEqual(Order.objects.get(pk=order.data['id']).status, Order.Status.CONFIRMED)
        second = self.client.generic('POST','/api/payments/razorpay/webhook/',data=body,**headers)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(PaymentWebhookEvent.objects.count(), 1)
