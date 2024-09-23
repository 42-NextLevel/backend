from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'game', views.GameRoomViewSet, basename='game')

urlpatterns = [
    path('', include(router.urls)),
]