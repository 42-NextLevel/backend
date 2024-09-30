import logging
import sys
from django.utils.functional import SimpleLazyObject
from django.contrib.auth.models import AnonymousUser  # 추가
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.http import JsonResponse
from . import utils

def get_user_jwt(request):
	print("get_user_jwt called", file=sys.stderr)  # 함수 호출 시 로그 출력
	user = None
	auth_header = request.META.get('HTTP_AUTHORIZATION')
	if auth_header:
		print(f"Authorization header: {auth_header}", file=sys.stderr)
		try:
			# Authorization 헤더에서 "Bearer" 제거하고 토큰 추출
			token = auth_header.split()[1] if len(auth_header.split()) > 1 else None
			if not token:
				raise InvalidToken('No token provided')

			# 액세스 토큰 검증
			validated_token = JWTAuthentication().get_validated_token(token)
			user = JWTAuthentication().get_user(validated_token)
			
			# intra_id 쿠키와 토큰의 불일치 확인
			intra_id = utils.CookieManager.get_intra_id_from_cookie(request)
			print(f"Token intra_id: {user.intra_id}, Cookie intra_id: {intra_id}", file=sys.stderr)
			if not intra_id or intra_id != user.intra_id:
				raise InvalidToken('Token intra_id mismatch')
				
		except (InvalidToken, TokenError) as e:
			print(f"Token error: {str(e)}", file=sys.stderr)
			raise InvalidToken('Token is invalid or expired')

	# 인증되지 않은 경우 AnonymousUser 반환
	return user or AnonymousUser()

class JWTAuthenticationMiddleware:
	def __init__(self, get_response):
		self.get_response = get_response
		print("JWTAuthenticationMiddleware initialized", file=sys.stderr)

	def __call__(self, request):
		# 특정 URL에 대한 미들웨어 적용 제외
		# /api/auth 로 시작하는 URL은 JWTAuthenticationMiddleware 적용 제외
		if request.path.startswith('/api/auth'):
			return self.get_response(request)
		try:
			# `get_user_jwt` 호출 및 평가
			request.user = SimpleLazyObject(lambda: get_user_jwt(request))
			
			# `request.user`에 접근하여 `get_user_jwt`가 호출되도록 강제 평가
			if request.user.is_authenticated:
				print(f"User is authenticated: {request.user}", file=sys.stderr)
			else:
				print("User is not authenticated", file=sys.stderr)
				# return JsonResponse({'error': 'User is not authenticated'}, status=401)

			response = self.get_response(request)
			return response
		except InvalidToken as e:
			print(f"Token error: {str(e)}", file=sys.stderr)
			return JsonResponse({'error': 'Token is invalid or expired'}, status=401)
