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
	def get_or_create(cls, intra_id, profile_image):
		try:
			user = cls.objects.get(filter(intra_id=intra_id))
			user.save()
			CREATE = False
		except ObjectDoesNotExist:
			user = cls.objects.create(
				intra_id=intra_id,
				profile_image=profile_image,
				email=None
			)
			CREATE = True
		return user, CREATE
	class Meta:
		db_table = 'users'

