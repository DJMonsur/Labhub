from django.contrib import admin
from django.urls import path, include
from inventory import views
from django.views.generic import TemplateView
from inventory.views import index, dashboard

urlpatterns = [
    path('admin/',     admin.site.urls),
    path('',           index,     name='home'),
    path('dashboard/', dashboard, name='dashboard'),
    path('accounts/',  include('allauth.urls')),
    path('api/',       include('inventory.urls')),
]

