import logging
import sys
from django.utils.functional import SimpleLazyObject
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.http import JsonResponse
from .utils import CookieManager
from .models import User
import jwt

def get_user_jwt(request):
    print("get_user_jwt called", file=sys.stderr)
    user = None
    auth_header = request.META.get('HTTP_AUTHORIZATION')
    if auth_header:
        print(f"Authorization header: {auth_header}", file=sys.stderr)
        try:
            token = auth_header.split()[1] if len(auth_header.split()) > 1 else None
            if not token:
                raise InvalidToken('No token provided')

            # 액세스 토큰 검증
            access_token = AccessToken(token)
            
            # 토큰에서 intra_id 추출
            intra_id = access_token.get('intra_id')
            if not intra_id:
                raise InvalidToken('Token does not contain intra_id')

            # 사용자 조회
            user = User.get_by_intra_id(intra_id)
            if not user:
                raise InvalidToken('User not found')
            
            # intra_id 쿠키와 토큰의 불일치 확인
            cookie_intra_id = CookieManager.get_intra_id_from_cookie(request)
            print(f"Token intra_id: {intra_id}, Cookie intra_id: {cookie_intra_id}", file=sys.stderr)
            if not cookie_intra_id or cookie_intra_id != intra_id:
                raise InvalidToken('Token intra_id mismatch')
                
        except (InvalidToken, TokenError, jwt.DecodeError) as e:
            print(f"Token error: {str(e)}", file=sys.stderr)
            raise InvalidToken('Token is invalid or expired')

    return user or AnonymousUser()

class JWTAuthenticationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        print("JWTAuthenticationMiddleware initialized", file=sys.stderr)

    def __call__(self, request):
        if request.path.startswith('/api/auth'):
            return self.get_response(request)
        try:
            request.user = SimpleLazyObject(lambda: get_user_jwt(request))
            
            if request.user.is_authenticated:
                print(f"User is authenticated: {request.user}", file=sys.stderr)
            else:
                print("User is not authenticated", file=sys.stderr)

            response = self.get_response(request)
            return response
        except InvalidToken as e:
            print(f"Token error: {str(e)}", file=sys.stderr)
            return JsonResponse({'error': str(e)}, status=401)