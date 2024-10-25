from django.urls import path
from .views import UserManager



urlpatterns = [
    path('user', UserManager.as_view({
        'get': 'get_client_info',
        'delete': 'logout'
    }), name='user_manager'),
]