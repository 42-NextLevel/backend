from django.core.mail import BadHeaderError, send_mail
from django.conf import settings
import re
from django.core.cache import cache
from rest_framework.response import Response
from django.core import signing
import secrets

class EmailManager:
	@staticmethod
	def generate_code():
		return str(secrets.randbelow(10**6)).zfill(6)

	@staticmethod
	def send_Auth_email(email):
		subject = "Transcendence 인증코드"
		verification_code = EmailManager.generate_code()  # generate_code 메서드 호출
		message = f"인증코드: {verification_code}"
		from_email = settings.EMAIL_HOST_USER
		try:
			send_mail(subject, message, from_email, [email])
		except BadHeaderError:
			raise BadHeaderError("Invalid header found.")
		return verification_code

	@staticmethod
	def validate_email(email):
		return re.match(r"[^@]+@[^@]+\.[^@]+", email)

	@staticmethod
	def verify_auth_code(intra_id, request):
		cached_code = cache.get(intra_id)
		request_code = request.data.get('code')
		if not cached_code or not request_code:
			return False
		if cached_code == request_code:
			cache.delete(intra_id)
			return True


class CookieManager:
	@staticmethod
	def get_intra_id_from_cookie(request):
		signed_value = request.COOKIES.get('intra_id')
		if signed_value:
			try:
				intra_id = signing.loads(signed_value, salt='intra-id-cookie', key=settings.SECRET_KEY)
				return intra_id
			except signing.BadSignature:
				return None
		return None

	@staticmethod
	def set_intra_id_cookie(response: Response, intra_id):
		signed_value = signing.dumps(intra_id, salt='intra-id-cookie', key=settings.SECRET_KEY)
		response.set_cookie('intra_id', signed_value, httponly=True, samesite='Strict', secure=True)
		return response

	def set_nickname_cookie(response: Response, nickname):
		response.set_cookie('nickname', nickname, httponly=True, samesite='Strict', secure=True)
		return response