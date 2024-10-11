from django.urls import path
from .views import UserManager



urlpatterns = [
    path('user', UserManager.as_view({'get': 'get_client_info'}), name='get_client_info'),
	path('logout', UserManager.as_view({'delete': 'logout'}), name='logout'),
]