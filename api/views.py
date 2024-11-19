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
from rest_framework_simplejwt.authentication import JWTAuthentication
from django.conf import settings
from django.db import transaction
from django.core.exceptions import ValidationError, PermissionDenied
from django.utils.html import escape
from django.utils.crypto import constant_time_compare
import bleach
import re
import logging
from functools import wraps

logger = logging.getLogger(__name__)

def rate_limit(key_prefix, max_attempts=5, timeout=900):
    def decorator(func):
        @wraps(func)
        def wrapper(self, request, *args, **kwargs):
            client_ip = request.META.get('REMOTE_ADDR')
            key = f"{key_prefix}_{client_ip}"
            
            attempts = cache.get(key, 0)
            if attempts >= max_attempts:
                logger.warning(f"Rate limit exceeded for IP: {client_ip}")
                return Response(
                    {"detail": "Too many attempts. Please try again later."}, 
                    status=status.HTTP_429_TOO_MANY_REQUESTS
                )
            
            response = func(self, request, *args, **kwargs)
            
            if response.status_code != status.HTTP_200_OK:
                cache.set(key, attempts + 1, timeout)
            
            return response
        return wrapper
    return decorator

class SecurityMixin:
    @staticmethod
    def sanitize_input(value, allowed_patterns=None):
        if not isinstance(value, str):
            return value
            
        value = re.sub(r'[\;\'\"\-\-\%\_\$]', '', value)
        value = bleach.clean(value, strip=True)
        value = escape(value)
        
        if allowed_patterns and not any(pattern.match(value) for pattern in allowed_patterns):
            raise ValidationError("Invalid input format")
            
        return value

class AuthCodeView(APIView, SecurityMixin):
    @rate_limit("42_auth", max_attempts=20, timeout=900)
    @transaction.atomic
    def post(self, request):
        try:
            code = self.sanitize_input(request.data.get('code'))
            
            if not code:
                return Response(
                    {'registered': False, 'error': 'No code provided'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            access_token = self._get_42_token(code)
            intra_id, user_image = self._get_user_info(access_token)
            
            intra_id = self.sanitize_input(intra_id)
            user_image = self.sanitize_input(user_image or '')
            
            user = self._get_or_create_user(intra_id, user_image)

            # 사용자가 이미 등록되어 있는 경우 (이메일이 있는 경우)
            if user.email:
                try:
                    auth_code = EmailManager.send_Auth_email(user.email)
                    cache.set(f"auth_code_{intra_id}", auth_code, timeout=300)
                    
                    response = Response(
                        {'registered': True}, 
                        status=status.HTTP_200_OK
                    )
                    return CookieManager.set_intra_id_cookie(response, intra_id)
                    
                except BadHeaderError as e:
                    logger.error(f"Email sending failed for user {intra_id}: {str(e)}")
                    return Response(
                        {'error': 'Failed to send authentication email'}, 
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR
                    )
            
            # 새로운 사용자인 경우
            response = Response(
                {'registered': False}, 
                status=status.HTTP_200_OK
            )
            return CookieManager.set_intra_id_cookie(response, intra_id)

        except Exception as e:
            logger.error(f"Error in AuthCodeView: {str(e)}")
            return Response(
                {'error': 'An unexpected error occurred'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def _get_42_token(self, code):
        try:
            response = requests.post(
                "https://api.intra.42.fr/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "client_id": os.environ.get('FT_ID'),
                    "client_secret": os.environ.get('FT_SECRET'),
                    "code": code,
                    "redirect_uri": f"https://{os.environ.get('SERVER_NAME')}:443/auth"
                }
            )
            response.raise_for_status()
            return response.json().get('access_token')
        except requests.RequestException as e:
            logger.error(f"42 API token error: {str(e)}")
            raise ValidationError("Failed to obtain access token")

    def _get_user_info(self, access_token):
        try:
            response = requests.get(
                "https://api.intra.42.fr/v2/me",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()
            data = response.json()
            return data.get('login'), data.get('image', {}).get('link')
        except requests.RequestException as e:
            logger.error(f"42 API user info error: {str(e)}")
            raise ValidationError("Failed to obtain user info")

    def _get_or_create_user(self, intra_id, user_image):
        try:
            return User.objects.get(intra_id=intra_id)
        except User.DoesNotExist:
            serializer = UserCreateSerializer(data={
                'intra_id': intra_id,
                'profile_image': user_image
            })
            if serializer.is_valid():
                return serializer.save()
            raise ValidationError(serializer.errors)

class AuthEmailView(APIView, SecurityMixin):
    """이메일 등록 및 인증 메일 발송 뷰"""
    
    @rate_limit("email_auth", max_attempts=40, timeout=900)
    @transaction.atomic
    def post(self, request):
        try:
            intra_id = CookieManager.get_intra_id_from_cookie(request)
            if not intra_id:
                return Response(
                    {'error': 'Invalid intra_id'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            user = User.objects.select_for_update().get(intra_id=intra_id)
            serializer = UserEmailUpdateSerializer(user, data=request.data)
            
            if not serializer.is_valid():
                return Response(
                    {'error': serializer.errors}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            email = serializer.validated_data['email']
            if not EmailManager.validate_email(email):
                return Response(
                    {'error': 'Invalid email format'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            try:
                auth_code = EmailManager.send_Auth_email(email)
                cache.set(f"auth_code_{intra_id}", auth_code, timeout=300)
                serializer.save()
                return Response(status=status.HTTP_200_OK)
            except BadHeaderError:
                return Response(
                    {'error': 'Failed to send email'}, 
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        except User.DoesNotExist:
            return Response(
                {'error': 'User not found'}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error in AuthEmailView: {str(e)}")
            return Response(
                {'error': 'An unexpected error occurred'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class AuthTokenView(APIView, SecurityMixin):
    """인증 코드 확인 및 토큰 발급 뷰"""
    
    @rate_limit("auth_token", max_attempts=5, timeout=900)
    @transaction.atomic
    def post(self, request):
        try:
            intra_id = CookieManager.get_intra_id_from_cookie(request)
            if not intra_id:
                return Response(
                    {"detail": "No intra_id found"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            auth_code = request.data.get('code')
            cached_code = cache.get(f"auth_code_{intra_id}")
            
            if not cached_code or not constant_time_compare(str(auth_code), str(cached_code)):
                return Response(
                    {"detail": "Invalid auth code"}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            user = User.objects.select_for_update().get(intra_id=intra_id)
            refresh = RefreshToken.for_user(user)
            refresh['intra_id'] = user.intra_id

            response = Response({
                'accessToken': str(refresh.access_token),
            }, status=status.HTTP_200_OK)

            response.set_cookie(
                'refresh_token',
                str(refresh),
                httponly=True,
                samesite='Strict',
                secure=True,
                max_age=settings.SIMPLE_JWT['REFRESH_TOKEN_LIFETIME'].total_seconds()
            )

            cache.delete(f"auth_code_{intra_id}")
            return response

        except User.DoesNotExist:
            return Response(
                {"detail": "User not found"}, 
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error in AuthTokenView: {str(e)}")
            return Response(
                {'error': 'An unexpected error occurred'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class CustomTokenRefreshView(TokenRefreshView):
    """토큰 갱신 뷰"""
    
    @rate_limit("token_refresh", max_attempts=10, timeout=300)
    def post(self, request, *args, **kwargs):
        try:
            refresh_token = request.COOKIES.get('refresh_token')
            if not refresh_token:
                return Response(
                    {'error': 'No refresh token provided'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            refresh = RefreshToken(refresh_token)
            
            if 'intra_id' not in refresh:
                raise InvalidToken('Invalid refresh token')
            
            intra_id = CookieManager.get_intra_id_from_cookie(request)
            if not intra_id or refresh['intra_id'] != intra_id:
                raise InvalidToken('Token mismatch')

            access_token = refresh.access_token
            access_token['intra_id'] = intra_id

            return Response({'accessToken': str(access_token)})

        except (InvalidToken, TokenError) as e:
            return Response(
                {'error': str(e)}, 
                status=status.HTTP_401_UNAUTHORIZED
            )

class SendEmailView(APIView, SecurityMixin):
    """테스트용 이메일 발송 뷰"""
    
    @rate_limit("send_email", max_attempts=3, timeout=1800)
    def get(self, request):
        try:
            code = EmailManager.send_Auth_email("test@example.com")
            return Response({'code': code}, status=status.HTTP_200_OK)
        except BadHeaderError:
            return Response(
                {'error': 'Failed to send email'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class UserProfilesView(APIView, SecurityMixin):
    @rate_limit("user_profile", max_attempts=10, timeout=300)
    def get(self, request):
        try:
            # Bearer 토큰 추출 및 검증
            auth_header = request.headers.get('Authorization', '')
            if not auth_header.startswith('Bearer '):
                return Response(
                    {'error': 'Invalid authorization header'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )
                
            access_token = auth_header.split(' ')[1]
            if not access_token:
                return Response(
                    {'error': 'No access token provided'}, 
                    status=status.HTTP_400_BAD_REQUEST
                )

            # JWT 토큰 검증
            try:
                token = JWTAuthentication().get_validated_token(access_token)
                user = JWTAuthentication().get_user(token)
            except (InvalidToken, TokenError) as e:
                logger.warning(f"Invalid token attempt: {str(e)}")
                return Response(
                    {'error': 'Invalid token'}, 
                    status=status.HTTP_401_UNAUTHORIZED
                )

            if not user:
                return Response(
                    {'error': 'Invalid user'}, 
                    status=status.HTTP_401_UNAUTHORIZED
                )

            # 사용자 정보 조회
            try:
                user = User.objects.select_related().get(intra_id=user.intra_id)
            except User.DoesNotExist:
                return Response(
                    {'error': 'User not found'}, 
                    status=status.HTTP_404_NOT_FOUND
                )

            # 응답 데이터 sanitize
            return Response({
                'intra_id': self.sanitize_input(user.intra_id),
                'profile_image': self.sanitize_input(user.profile_image)
            }, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error in UserProfilesView: {str(e)}")
            return Response(
                {'error': 'An unexpected error occurred'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def post(self, request):
        return Response(
            {'error': 'POST method not allowed'}, 
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )

class LogoutView(APIView):
    @rate_limit("logout", max_attempts=5, timeout=300)
    def post(self, request):
        try:
            response = Response(status=status.HTTP_200_OK)
            
            # 모든 인증 관련 쿠키 삭제
            response.delete_cookie(
                'refresh_token',
                path='/',
                domain=None,
                samesite='Strict'
            )
            response.delete_cookie('intra_id')
            
            # 세션 클리어 (만약 세션을 사용한다면)
            if hasattr(request, 'session'):
                request.session.flush()
                
            # 캐시된 인증 데이터 삭제
            if hasattr(request.user, 'intra_id'):
                cache.delete(f"auth_code_{request.user.intra_id}")
                cache.delete(f"auth_attempts_{request.user.intra_id}")
            
            return response

        except Exception as e:
            logger.error(f"Error in LogoutView: {str(e)}")
            return Response(
                {'error': 'Logout failed'}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def get(self, request):
        return Response(
            {'error': 'GET method not allowed'}, 
            status=status.HTTP_405_METHOD_NOT_ALLOWED
        )