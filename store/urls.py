from django.urls import path
from . import views

urlpatterns = [
    path('catalog/', views.catalog, name='catalog'),
    path('ondc/catalog/', views.ondc_catalog, name='ondc-catalog'),
]
