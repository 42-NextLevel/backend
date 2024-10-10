import logging
from django.utils.functional import SimpleLazyObject
from django.contrib.auth.models import AnonymousUser
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework import status
from .models import User
import jwt
import sys
# Response: 401 Unauthorized
from rest_framework.response import Response

logger = logging.getLogger(__name__)

def get_user_jwt(request):
    logger.info("get_user_jwt called")
    auth_header = request.META.get('HTTP_AUTHORIZATION')
    logger.info(f"Authorization header: {auth_header}")
    print("Authorization header: ", auth_header, file=sys.stderr)
    
    if not auth_header:
        logger.warning("No Authorization header found")
        return AnonymousUser()

    try:
        token_parts = auth_header.split()
        if len(token_parts) != 2 or token_parts[0].lower() != "bearer":
            logger.warning("Invalid Authorization header format")
            return AnonymousUser()
        
        token = token_parts[1]
        logger.info(f"Token: {token[:10]}...")  # 토큰의 일부만 로그에 기록
        
        # 액세스 토큰 검증
        # JWTAuthentication().authenticate(request)
        # if user is not None:
        #     request.user = user[0]
        access_token = AccessToken(token)
        
        # 토큰에서 intra_id 추출
        intra_id = access_token.get('intra_id')
        print("intra_id: ", intra_id, file=sys.stderr)
        if not intra_id:
            print("No intra_id found in token", file=sys.stderr)
            return AnonymousUser()

        # 사용자 조회
        user = User.get_by_intra_id(intra_id)
        print("User: ", user, file=sys.stderr)
        if not user:
            print("User not found", file=sys.stderr)
            return AnonymousUser()
        
        print("User found", file=sys.stderr)
        return user

    except (InvalidToken, TokenError, jwt.DecodeError) as e:
        logger.error(f"Token error: {str(e)}")
        return AnonymousUser()

class JWTAuthenticationMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        logger.info("JWTAuthenticationMiddleware initialized")

    def __call__(self, request):
        logger.info(f"Processing request: {request.path}")
        if request.path.startswith('/api/auth'):
            logger.info("Skipping authentication for /api/auth")
            return self.get_response(request)

        request.user = SimpleLazyObject(lambda: get_user_jwt(request))
        
        if isinstance(request.user, AnonymousUser):
            logger.warning("User is not authenticated (AnonymousUser)")
            response = self.get_response(request)
            response.status_code = status.HTTP_401_UNAUTHORIZED
            return response
            
        else:
            logger.info(f"User is authenticated: {request.user}")

        response = self.get_response(request)
        logger.info(f"Response status code: {response.status_code}")
        return response
