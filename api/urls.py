from django.urls import path, include
from . import views
from rest_framework.routers import DefaultRouter

app_name = 'api'

urlpatterns = [
	path('auth/42-code', views.AuthView.as_view(), name='auth'),
]