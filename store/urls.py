from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView
from . import views
from .api_views import RegisterView, CategoryViewSet, ProductViewSet, VendorViewSet, OrderCreateView, OrderListView

router = DefaultRouter()
router.register('categories', CategoryViewSet, basename='category')
router.register('products', ProductViewSet, basename='product')
router.register('vendors', VendorViewSet, basename='vendor')

urlpatterns = [
    path('auth/register/', RegisterView.as_view(), name='register'),
    path('token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('orders/create/', OrderCreateView.as_view(), name='order-create'),
    path('orders/', OrderListView.as_view(), name='order-list'),
    path('', include(router.urls)),
    path('catalog/', views.catalog, name='catalog'),
    path('ondc/catalog/', views.ondc_catalog, name='ondc-catalog'),
]
