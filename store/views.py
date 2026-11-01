from html import escape
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_GET
from .models import Product

PRODUCT_ART = {
    'ELEC-001': '🎧', 'ELEC-002': '🔌', 'ELEC-003': '🔊', 'ELEC-004': '🖱️', 'ELEC-005': '💡',
    'FASH-001': '👔', 'FASH-002': '👗', 'FASH-003': '👕', 'FASH-004': '🎒', 'FASH-005': '👟',
    'GROC-001': '🍚', 'GROC-002': '🫘', 'GROC-003': '🫒', 'GROC-004': '🌾', 'GROC-005': '🥜',
    'HOME-001': '🧴', 'HOME-002': '🍳', 'HOME-003': '🛏️', 'HOME-004': '💡', 'HOME-005': '🫙',
    'BEAU-001': '🧼', 'BEAU-002': '🧴', 'BEAU-003': '🧼', 'BEAU-004': '☀️', 'BEAU-005': '🥥',
}
PALETTES = {
    'Electronics': ('#e8efff', '#dce7ff', '#294d91'),
    'Fashion': ('#f8eaf0', '#f3dce7', '#87415e'),
    'Grocery': ('#edf5e7', '#dcebcf', '#486c36'),
    'Home & Kitchen': ('#f8efe4', '#f0dfc9', '#8b5d32'),
    'Beauty & Personal Care': ('#f8eafa', '#efdafa', '#86518e'),
}

def home(request):
    return render(request, 'index.html')

@require_GET
def product_image(request, sku):
    product = Product.objects.select_related('category').filter(sku=sku, is_active=True).first()
    if not product:
        return HttpResponse(status=404)
    category = product.category.name if product.category_id else 'Marketplace'
    start, end, accent = PALETTES.get(category, ('#eef3ee', '#dce9df', '#315b43'))
    icon = PRODUCT_ART.get(product.sku, '🛍️')
    name = escape(product.name)
    category_label = escape(category)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="900" height="700" viewBox="0 0 900 700">
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="{start}"/><stop offset="1" stop-color="{end}"/></linearGradient><filter id="shadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="18" stdDeviation="20" flood-color="{accent}" flood-opacity=".16"/></filter></defs>
<rect width="900" height="700" fill="url(#bg)"/><circle cx="730" cy="115" r="170" fill="#fff" opacity=".28"/><circle cx="120" cy="610" r="210" fill="#fff" opacity=".22"/>
<rect x="250" y="105" width="400" height="390" rx="48" fill="#fff" opacity=".72" filter="url(#shadow)"/>
<text x="450" y="360" text-anchor="middle" font-family="Arial,'Apple Color Emoji','Segoe UI Emoji',sans-serif" font-size="180">{icon}</text>
<text x="450" y="555" text-anchor="middle" font-family="Arial,sans-serif" font-size="19" font-weight="700" letter-spacing="3" fill="{accent}">{category_label.upper()}</text>
<text x="450" y="602" text-anchor="middle" font-family="Arial,sans-serif" font-size="27" font-weight="700" fill="#1d2b22">{name}</text>
<text x="450" y="648" text-anchor="middle" font-family="Arial,sans-serif" font-size="15" fill="{accent}">MARKETLANE · PRODUCT ART</text></svg>'''
    return HttpResponse(svg, content_type='image/svg+xml; charset=utf-8')

@require_GET
def catalog(request):
    qs = Product.objects.filter(is_active=True, vendor__is_approved=True, vendor__is_suspended=False).select_related('vendor', 'category')
    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(name__icontains=search)
    data = [{'id': p.id, 'name': p.name, 'description': p.description, 'image_url': p.image_url, 'sku': p.sku, 'price': str(p.price), 'stock': p.stock, 'category': p.category.name if p.category_id else None, 'vendor': p.vendor.store_name} for p in qs]
    return JsonResponse({'results': data})

@require_GET
def ondc_catalog(request):
    # Mock catalog mapping only. This endpoint is not a production ONDC/Beckn implementation.
    products = Product.objects.filter(is_active=True, vendor__is_approved=True, vendor__is_suspended=False).select_related('vendor', 'category')
    items = [{'id': str(p.id), 'descriptor': {'name': p.name, 'short_desc': p.description[:300]}, 'price': {'currency': 'INR', 'value': str(p.price)}, 'quantity': {'available': {'count': str(p.stock)}}, 'provider': {'id': str(p.vendor_id), 'descriptor': {'name': p.vendor.store_name}}} for p in products]
    return JsonResponse({'context': {'domain': 'ONDC:RET10', 'action': 'search', 'mode': 'mock'}, 'message': {'catalog': {'bpp/descriptor': {'name': 'Demo Multi-Vendor Marketplace'}, 'bpp/providers': items}}})
