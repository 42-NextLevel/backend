from django.shortcuts import render

# Create your views here.
from rest_framework import viewsets, status
from rest_framework.response import Response

from django.core.cache import cache
import time
from api.utils import CookieManager
from rest_framework_simplejwt.authentication import JWTAuthentication
import sys
from api.models import User
from rest_framework.decorators import action

# user manager
class UserManager(viewsets.ViewSet):
	def get_client_info(self, request):
		# get client info by User DataBase
		try:
			intra_id = request.user
			user = User.get_by_intra_id(intra_id)
			if not user:
				return Response({'error': 'User not found'}, status=status.HTTP_404_NOT_FOUND)
		except Exception as e:
			return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
		return Response({'intra_id': user.intra_id, 'profile_image': user.profile_image}, status=status.HTTP_200_OK)
	
	@action(detail=False, methods=['delete'])
	def logout(self, request):
		try:
			# 성공 메시지와 함께 Response 객체 생성
			response = Response(
				{'message': 'Logout success'}, 
				status=status.HTTP_200_OK
			)
			
			# 쿠키 삭제
			cookie_manager = CookieManager()
			response = cookie_manager.delete_cookie(response)
			
			return response
		except Exception as e:
			return Response(
				{'error': str(e)}, 
				status=status.HTTP_400_BAD_REQUEST
			)

		