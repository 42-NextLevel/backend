from django.db import models
from django.core.exceptions import ObjectDoesNotExist

class User(models.Model):
	id = models.AutoField(primary_key=True)
	intra_id = models.CharField(max_length=100, unique=True)
	profile_image = models.CharField(max_length=255)
	email = models.CharField(max_length=255, null=True)


	def __str__(self):
		return self.intra_id
	
	@classmethod
	def create(cls, intra_id, profile_image):
		user = cls.objects.create(
			intra_id=intra_id,
			profile_image=profile_image,
			email=None
		)
		return user
	
	@classmethod
	def get_by_intra_id(cls, intra_id):
		try:
			return cls.objects.get(intra_id=intra_id)
		except cls.DoesNotExist:
			return None

	@classmethod
	def get(cls, intra_id):
		try:
			return cls.objects.get(intra_id=intra_id)
		except cls.DoesNotExist:
			return None
	
	class Meta:
		db_table = 'users'

