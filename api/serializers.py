from rest_framework import serializers
from .models import User

class UserSerializer(serializers.ModelSerializer):
	class Meta:
		model = User
		fields = ['id', 'intra_id', 'profile_image', 'email']
		read_only_fields = ['id']


class UserCreateSerializer(serializers.ModelSerializer):
	class Meta:
		model = User
		fields = ['intra_id', 'profile_image']

	def create(self, validated_data):
		user = User.create(**validated_data)
		return user
	
	def get_user(self, intra_id):
		user = User.get(intra_id)
		return user

class UserEmailUpdateSerializer(serializers.ModelSerializer):
	class Meta:
		model = User
		fields = ['email']

	def update(self, instance, validated_data):
		instance.email = validated_data.get('email', instance.email)
		instance.save()
		return instance
	