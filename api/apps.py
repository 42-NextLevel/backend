from django.apps import AppConfig
import redis


class ApiConfig(AppConfig):
	default_auto_field = 'django.db.models.BigAutoField'
	name = 'api'
    
	def ready(self):
		self.redis = redis.StrictRedis(host='localhost', port=6379, db=0)

