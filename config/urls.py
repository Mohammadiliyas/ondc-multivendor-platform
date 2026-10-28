from django.contrib import admin
from django.urls import path, include
from django.http import JsonResponse

def health(request):
    return JsonResponse({'status': 'ok', 'service': 'ondc-multivendor-platform', 'ondc_mode': 'mock'})

urlpatterns = [path('admin/', admin.site.urls), path('api/health/', health), path('api/', include('store.urls'))]
