from django.test import TestCase, Client
from django.contrib.auth.models import User
from .models import Vendor, Category, Product

class BasicMarketplaceTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.owner = User.objects.create_user(username='seller1', password='safe-test-password')
        self.vendor = Vendor.objects.create(owner=self.owner, store_name='Demo Store', is_approved=True)
        self.category = Category.objects.create(name='General')
        Product.objects.create(vendor=self.vendor, category=self.category, name='Demo item', sku='DEMO-001', price='12.50', stock=4)

    def test_health_endpoint(self):
        response = self.client.get('/api/health/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')

    def test_public_catalog_contains_approved_vendor_product(self):
        response = self.client.get('/api/catalog/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()['results']), 1)

    def test_mock_ondc_catalog_is_marked_mock(self):
        response = self.client.get('/api/ondc/catalog/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['context']['mode'], 'mock')
