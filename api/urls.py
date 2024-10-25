from django.urls import path, include
from . import views

app_name = 'api'

urlpatterns = [
	path('42-code', views.AuthCodeView.as_view(), name='auth'),
	path('email', views.AuthEmailView.as_view(), name='email'),
	path('code', views.AuthTokenView.as_view(), name='code'),
	path('token', views.CustomTokenRefreshView.as_view(), name='token_refresh'),
	path('send-email', views.SendEmailView.as_view(), name='send_email'),
]