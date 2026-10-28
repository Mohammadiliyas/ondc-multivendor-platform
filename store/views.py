from django.http import JsonResponse
from django.views.decorators.http import require_GET
from .models import Product

@require_GET
def catalog(request):
    qs = Product.objects.filter(is_active=True, vendor__is_approved=True).select_related('vendor', 'category')
    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(name__icontains=search)
    data = [{'id': p.id, 'name': p.name, 'description': p.description, 'sku': p.sku, 'price': str(p.price), 'stock': p.stock, 'category': p.category.name if p.category_id else None, 'vendor': p.vendor.store_name} for p in qs]
    return JsonResponse({'results': data})

@require_GET
def ondc_catalog(request):
    # Mock catalog mapping only. This endpoint is not a production ONDC/Beckn implementation.
    products = Product.objects.filter(is_active=True, vendor__is_approved=True).select_related('vendor', 'category')
    items = [{'id': str(p.id), 'descriptor': {'name': p.name, 'short_desc': p.description[:300]}, 'price': {'currency': 'INR', 'value': str(p.price)}, 'quantity': {'available': {'count': str(p.stock)}}, 'provider': {'id': str(p.vendor_id), 'descriptor': {'name': p.vendor.store_name}}} for p in products]
    return JsonResponse({'context': {'domain': 'ONDC:RET10', 'action': 'search', 'mode': 'mock'}, 'message': {'catalog': {'bpp/descriptor': {'name': 'Demo Multi-Vendor Marketplace'}, 'bpp/providers': items}}})
