from django.apps import AppConfig
# from .blockchain import ContractInit
import redis


class ApiConfig(AppConfig):
	default_auto_field = 'django.db.models.BigAutoField'
	name = 'api'
