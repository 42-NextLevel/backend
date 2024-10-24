# Create a new file named 'management/commands/insert_dummy_data.py' in your app directory

from django.core.management.base import BaseCommand
from api.models import User  # 'Transcendence.api'를 'api'로 변경
from django.db import transaction
from django.core.cache import cache

class Command(BaseCommand):
	help = 'Insert dummy data into the database'

	@transaction.atomic
	def handle(self, *args, **kwargs):
		dummy_users = [
			{'intra_id': 'dongkseo', 'profile_image': 'https://placehold.co/600x400', 'email': 'ssddgg99@daum.net'},
			{'intra_id': 'junsbae', 'profile_image': 'https://placehold.co/600x400', 'email': 'gentlmanjun@naver.com'},
		]

		for user_data in dummy_users:
			user, created = User.objects.get_or_create(
				intra_id=user_data['intra_id'],
				defaults={
					'profile_image': user_data['profile_image'],
					'email': user_data['email']
				}
			)
			if created:
				self.stdout.write(self.style.SUCCESS(f"생성된 사용자: {user_data['intra_id']}"))
			else:
				self.stdout.write(self.style.WARNING(f"이미 존재하는 사용자: {user_data['intra_id']}"))
				
		# room 세팅
		# room_data = {
		# 	'id': room_id,
		# 	'name': request.data.get('name'),
		# 	'roomType': request.data.get('roomType'),
		# 	'players': [],
		# 	'host': request.data.get('nickname'),
		# 	'game_started': False,
		# 	'created_at': time.time(),
		# 	'game1': [],
		# 	'game2': []
		# }
		# {'intraId':intra_id, 'nickname': nickname, 'profileImage': user.profile_image}
		cache.set('game_room_1', {
			'id': '1',
			'name': 'room1',
			'roomType': '1',
			'players': [
				{'intraId': 'dongkseo', 'nickname': 'dongkseo', 'profileImage': 'https://placehold.co/600x400'},
				{'intraId': 'junsbae', 'nickname': 'junsbae', 'profileImage': 'https://placehold.co/600x400'},
				{'intraId': 'test1', 'nickname': 'test1', 'profileImage': 'https://placehold.co/600x400'},
				{'intraId': 'test2', 'nickname': 'test2', 'profileImage': 'https://placehold.co/600x400'},
			   ],
			'host': 'dongkseo',
			'game_started': False,
			'created_at': 1630478400.0,
			'game1': [
				{'intraId': 'dongkseo', 'nickname': 'dongkseo', 'profileImage': 'https://placehold.co/600x400'},
				{'intraId': 'junsbae', 'nickname': 'junsbae', 'profileImage': 'https://placehold.co/600x400'}
			 ],
			'game2': [
				{'intraId': 'test1', 'nickname': 'test1', 'profileImage': 'https://placehold.co/600x400'},
				{'intraId': 'test2', 'nickname': 'test2', 'profileImage': 'https://placehold.co/600x400'}
			]
		})

		self.stdout.write(self.style.SUCCESS('더미 데이터 삽입 완료'))