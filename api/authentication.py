from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed
from .models import User
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework_simplejwt.exceptions import TokenError, InvalidToken

class CustomJWTAuthentication(BaseAuthentication):
	def authenticate(self, request):
		auth_header = request.META.get('HTTP_AUTHORIZATION')
		# skip requests starting with '/api/auth/'
		if request.path.startswith('/api/auth/'):
			return None
		# if not auth_header:
		#     return None

		try:
			if not auth_header:
				raise AuthenticationFailed('No token provided')
			access_token = auth_header.split(' ')[1]
			payload = AccessToken(access_token)
			intra_id = payload['intra_id']
			user = User.get_by_intra_id(intra_id)
			if user is None:
				raise AuthenticationFailed('User not found')
			return (user, None)
		except (IndexError, KeyError, User.DoesNotExist):
			raise AuthenticationFailed('Invalid token')
		except (TokenError, InvalidToken):
			raise AuthenticationFailed('Invalid token')