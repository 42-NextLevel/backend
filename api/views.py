from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.apps import apps
import requests
import os
from django.db import models
from dotenv import load_dotenv

load_dotenv()


# Create your views here.

class AuthView(APIView):
	def post(self, request):
		code = request.data.get('code')
		# redis_instance = apps.get_app_config('api').redis
		
		if not code:
			return Response({'registered': False, 'error': 'No code provided'}, status=status.HTTP_400_BAD_REQUEST)
		
		try:
			access_token = self.get_42_token(code)

			if not access_token:
				raise Exception("Failed to obtain access token")
			
			intra_id, user_image = self.get_user_info(access_token)

			user, CREATED = models.User.get_or_create(intra_id, user_image)

			if CREATED or user.email is None:
				return Response({'registered': False}, status=status.HTTP_200_OK)
				
		except Exception as e:
			return Response({'registered': False, 'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


		response = Response({'registered': True}, status=status.HTTP_200_OK)
		return response


	def get_42_token(self, code):
		# Get the access token from 42 API
		CLIENT_ID = os.environ.get('CLIENT_ID')
		CLIENT_SECRET = os.environ.get('CLIENT_SECRET')
		REDIRECT_URI = "https://example.com/callback"
		TOKEN_URL = "https://api.intra.42.fr/oauth/token"
		token_data = {
			"grant_type": "authorization_code",
			"client_id": CLIENT_ID,
			"client_secret": CLIENT_SECRET,
			"code": code,
			"redirect_uri": REDIRECT_URI
		}

		response = requests.post(TOKEN_URL, data=token_data)
		if response.status_code != 200:
			raise Exception("Failed to obtain access token")
		return response.json().get('access_token')
	
	def get_user_info(self, access_token):
		# Get the user info from 42 API
		USER_URL = "https://api.intra.42.fr/v2/me"
		headers = {
			"Authorization": f"Bearer {access_token}",
		}
		response = requests.get(USER_URL, headers=headers)
		if response.status_code != 200:
			raise Exception("Failed to obtain user info")
		user_data = response.json()
		intra_id = user_data.get('id')
		user_image = user_data.get('image', {}).get('link')  # 유저 이미지 URL

		return intra_id, user_image


	def get(self, request):
		return Response({'error': 'GET method not allowed'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

		
		
