from django.urls import path, include
from . import views

app_name = 'api'

urlpatterns = [
	path('auth/42-code', views.AuthCodeView.as_view(), name='auth'),
	path('auth/email', views.AuthEmailView.as_view(), name='email'),
	path('auth/code', views.AuthTokenView.as_view(), name='code'),
	path('auth/token/access', views.CustomTokenRefreshView.as_view(), name='token_refresh'),
	path('auth/token/42-uid', views.Auth42InfoView.as_view(), name='42_info'),
	path('auth/send-email', views.SendEmailView.as_view(), name='send_email'),
]