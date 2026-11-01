from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APIClient
from .models import Vendor, Category, Product, Order, OrderItem, InventoryMovement

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
