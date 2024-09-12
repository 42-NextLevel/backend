from django.apps import AppConfig
import redis


class ApiConfig(AppConfig):
	default_auto_field = 'django.db.models.BigAutoField'
	name = 'api'

