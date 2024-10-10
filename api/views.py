from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
import requests
import os
from .models import User
from dotenv import load_dotenv
from django.core.cache import cache
from .utils import EmailManager, CookieManager
from django.core.mail import BadHeaderError
from .serializers import UserCreateSerializer, UserEmailUpdateSerializer
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework import status
from . import utils
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.conf import settings
load_dotenv()

import sys

class AuthCodeView(APIView):
	def post(self, request):
		code = request.data.get('code')
		
		if not code:
			return Response({'registered': False, 'error': 'No code provided'}, status=status.HTTP_400_BAD_REQUEST)
		
		try:
			access_token = self.get_42_token(code)
			intra_id, user_image = self.get_user_info(access_token)
			
			print(intra_id, file=sys.stderr)
			print(user_image, file=sys.stderr)
			# user = User.get_or_create(intra_id, user_image)
			user = User.get(intra_id)
			if not user:
				serializer = UserCreateSerializer(data={'intra_id': intra_id, 'profile_image': user_image})  
				if not serializer.is_valid():
					return Response({'registered': False, 'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
				user = serializer.save()
			if not user.email:
				response = Response({'registered': False}, status=status.HTTP_200_OK)
				CookieManager.set_intra_id_cookie(response, intra_id)
				return response
			
			
			try:
				auth_code = EmailManager.send_Auth_email(user.email)
				cache.set(intra_id, auth_code, timeout=3600)
			except BadHeaderError:
				return Response({'error': 'Failed to send email'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
			
			response = Response({'registered': True}, status=status.HTTP_200_OK)
			return CookieManager.set_intra_id_cookie(response, intra_id)
			
		except Exception as e:
			return Response({'registered': False, 'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)

	def get_42_token(self, code):
		CLIENT_ID = os.environ.get('FT_ID')
		CLIENT_SECRET = os.environ.get('FT_SECRET')
		REDIRECT_URI = "https://localhost:443/auth"
		TOKEN_URL = "https://api.intra.42.fr/oauth/token"
		token_data = {
			"grant_type": "authorization_code",
			"client_id": CLIENT_ID,
			"client_secret": CLIENT_SECRET,
			"code": code,
			"redirect_uri": REDIRECT_URI
		}

		try:
			response = requests.post(TOKEN_URL, data=token_data)
			response.raise_for_status()  # Raises an HTTPError for bad responses
			return response.json().get('access_token')
		except requests.RequestException as e:
			raise Exception(f"Failed to obtain access token: {str(e)}")
	
	def get_user_info(self, access_token):
		USER_URL = "https://api.intra.42.fr/v2/me"
		headers = {
			"Authorization": f"Bearer {access_token}",
		}
		try:
			response = requests.get(USER_URL, headers=headers)
			response.raise_for_status()
			user_data = response.json()
			intra_id = user_data.get('login')
			user_image = user_data.get('image', {}).get('link')
			return intra_id, user_image
		except requests.RequestException as e:
			raise Exception(f"Failed to obtain user info: {str(e)}")

	def get(self, request):
		return Response({'error': 'GET method not allowed'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

		
		
class AuthEmailView(APIView):

	# def get_intra_id_from_cookie(self, request):
	# 	signed_value = request.COOKIES.get('intra_id')
	# 	if signed_value:
	# 		try:
	# 			intra_id = signing.loads(signed_value, salt='intra-id-cookie', key=settings.SECRET_KEY)
	# 			return intra_id
	# 		except signing.BadSignature:
	# 			return None
	# 	return None

	def post(self, request):
		intra_id = CookieManager.get_intra_id_from_cookie(request)
		if not intra_id:
			return Response({'error': 'Invalid intra_id'}, status=status.HTTP_400_BAD_REQUEST)

		user = User.get_by_intra_id(intra_id)
		
		if not user:
			return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
		
		serializer = UserEmailUpdateSerializer(user, data=request.data)
		if serializer.is_valid():
			email = serializer.validated_data.get('email')
			if not EmailManager.validate_email(email):
				return Response(status=status.HTTP_400_BAD_REQUEST)
		
			try:
				code = EmailManager.send_Auth_email(email)
				cache.set(intra_id, code, timeout=300)
			except BadHeaderError:
				return Response(status=status.HTTP_400_BAD_REQUEST)
		
			serializer.save()
			return Response(status=status.HTTP_200_OK)
		return Response({'error': serializer.errors}, status=status.HTTP_400_BAD_REQUEST)

	def get(self, request):
		return Response({'error': 'GET method not allowed'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)
	
	
class AuthTokenView(APIView):
	def post(self, request):
		intra_id = CookieManager.get_intra_id_from_cookie(request)
		if not intra_id:
			return Response({"detail": "No intra_id found"}, status=status.HTTP_400_BAD_REQUEST)
		
		if not EmailManager.verify_auth_code(intra_id, request):
			return Response({"detail": "Invalid auth code"}, status=status.HTTP_400_BAD_REQUEST)
		
		user = User.get_by_intra_id(intra_id)
		if not user:
			return Response({"detail": "User not found"}, status=status.HTTP_404_NOT_FOUND)
		
		refresh = RefreshToken.for_user(user)
		refresh['intra_id'] = user.intra_id
		
		# SIMPLE_JWT 설정에 따라 user_id 추가
		# user_id_claim = getattr(settings, 'SIMPLE_JWT', {}).get('USER_ID_CLAIM', 'user_id')
		# user_id_field = getattr(settings, 'SIMPLE_JWT', {}).get('USER_ID_FIELD', 'id')
		# user_id = getattr(user, user_id_field)
		# refresh[user_id_claim] = user_id


		response = Response({
			'access': str(refresh.access_token),
			# 'refresh': str(refresh),
		}, status=status.HTTP_200_OK)

		# HttpOnly 쿠키로 refresh 토큰 설정
		response.set_cookie(
			'refresh_token', 
			str(refresh), 
			httponly=True, 
			samesite='Strict',
			secure=request.is_secure(),  # HTTPS를 사용하는 경우에만 True
			max_age=settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds()
		)

		return response

	def get(self, request):
		return Response({'error': 'GET method not allowed'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)
		



class CustomTokenRefreshView(TokenRefreshView):
	def post(self, request, *args, **kwargs):
		try:
			refresh_token = request.COOKIES.get('refresh_token')
			if not refresh_token:
				return Response({'error': 'No refresh token provided'}, status=status.HTTP_400_BAD_REQUEST)

			refresh = RefreshToken(refresh_token)
			cache.set()
			
			if 'intra_id' not in refresh:
				raise InvalidToken('Invalid refresh token')
			
			intra_id = CookieManager.get_intra_id_from_cookie(request)
			if not intra_id or refresh['intra_id'] != intra_id:
				raise InvalidToken('Token mismatch')

			# Generate new access token
			access_token = refresh.access_token
			access_token['intra_id'] = intra_id

			response = Response({
				'accessToken': str(access_token),
			})
			
			# Optionally rotate the refresh token
			new_refresh = RefreshToken.for_user(utils.User.get_by_intra_id(intra_id))
			new_refresh['intra_id'] = intra_id
			response.set_cookie('refresh_token', str(new_refresh), httponly=True, samesite='Strict')

			return response
		except (InvalidToken, TokenError) as e:
			return Response({'error': str(e)}, status=status.HTTP_401_UNAUTHORIZED)

	def get(self, request):
		return Response({'error': 'GET method not allowed'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)
	

class Auth42InfoView(APIView):
	def get(self, request):
		return Response({'uid': os.environ.get('FT_ID')}, status=status.HTTP_200_OK)
	
	def post(self, request):

		return Response({'error': 'POST method not allowed'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

class SendEmailView(APIView):
	def get(self, request):
		print("send email", file=sys.stderr)
		try:
			code = EmailManager.send_Auth_email("ssddgg99@daum.net")
			return Response({'code': code}, status=status.HTTP_200_OK)
		except BadHeaderError:
			return Response({'error': 'Failed to send email'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
		
	def post(self, request):
		return Response({'error': 'POST method not allowed'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)


class UserProfilesView(APIView):
	def get(self, request):
		access_token = request.headers.get('Authorization')
		if not access_token:
			return Response({'error': 'No access token provided'}, status=status.HTTP_400_BAD_REQUEST)
		access_token = JWTAuthentication().get_validated_token(access_token)
		user = JWTAuthentication().get_user(access_token)
		if not user:
			return Response({'error': 'Invalid token'}, status=status.HTTP_401_UNAUTHORIZED)
		intra_id = user.intra_id
		user = User.get_by_intra_id(intra_id)
		if not user:
			return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
		return Response({'intra_id': user.intra_id, 'profile_image': user.profile_image}, status=status.HTTP_200_OK)

	def post(self, request):
		return Response({'error': 'POST method not allowed'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)
	

class LogoutView(APIView):
	def post(self, request):
		response = Response(status=status.HTTP_200_OK)
		response.delete_cookie('refresh_token')
		return response

	def get(self, request):
		return Response({'error': 'GET method not allowed'}, status=status.HTTP_405_METHOD_NOT_ALLOWED)