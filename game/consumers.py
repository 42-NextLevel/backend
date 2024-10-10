import json
from channels.generic.websocket import AsyncWebsocketConsumer
from django.core.cache import cache
from channels.db import database_sync_to_async
import sys
from typing import Dict, Any
from api.serializers import UserCreateSerializer
from urllib.parse import parse_qs

ROOM_TIMEOUT = 3600  # 1 hour

class GameConsumer(AsyncWebsocketConsumer):
	async def connect(self):
		self.room_id = self.scope['url_route']['kwargs']['room_id']
		self.room_group_name = f'game_{self.room_id}'
		print("Cookies: ", self.scope['cookies'], file=sys.stderr)
		query_string = self.scope['query_string'].decode()
		query_params = parse_qs(query_string)
		
		intra_id = query_params.get('intra_id', [None])[0]
		nickname = query_params.get('nickname', [None])[0]
		print(f"nickname: {nickname}, intra_id: {intra_id}", file=sys.stderr)
		print(f"room_id: {self.room_id}", file=sys.stderr)
		print(f"room_group_name: {self.room_group_name}", file=sys.stderr)
		if not nickname or not intra_id:
			print("Missing required query parameters", file=sys.stderr)
			await self.close()
			return

		try:
			user = await self.get_user(intra_id)
			self.user_data = {'nickname': nickname, 'profile_image': user.profile_image}
		except Exception as e:
			print(f"Error getting user data: {e}", file=sys.stderr)
			await self.close()
			return

		await self.channel_layer.group_add(self.room_group_name, self.channel_name)
		await self.accept()
		
		await self.update_room_players(add=True)

	async def disconnect(self, close_code):
		if hasattr(self, 'user_data'):
			await self.update_room_players(add=False)
		await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

	@database_sync_to_async
	def get_user(self, intra_id: str):
		return UserCreateSerializer().get_user(intra_id)

	@database_sync_to_async
	def get_room(self) -> Dict[str, Any]:
		return cache.get(f'game_room_{self.room_id}')

	@database_sync_to_async
	def set_room(self, room: Dict[str, Any]):
		cache.set(f'game_room_{self.room_id}', room, timeout=ROOM_TIMEOUT)

	async def update_room_players(self, add: bool):
		print(f"Updating room players: {add}", file=sys.stderr)
		room = await self.get_room()
		if not room:
			return

		players = room.get('players', [])
		if add:
			if self.user_data['nickname'] not in [p['nickname'] for p in players]:
				players.append(self.user_data)
		else:
			players = [p for p in players if p['nickname'] != self.user_data['nickname']]

		room['players'] = players
		await self.set_room(room)
		await self.broadcast_room_update(room)

	async def broadcast_room_update(self, room: Dict[str, Any]):
		await self.channel_layer.group_send(
			self.room_group_name,
			{
				'type': 'room_update',
				'room': room
			}
		)

	async def room_update(self, event):
		# 이 메서드를 추가합니다
		room = event['room']
		await self.send(text_data=json.dumps({
			'type': 'room_update',
			'room': room
		}))


# room -> data
# gamestart -> game_start

	# async def receive(self, text_data):
	# 	try:
	# 		data = json.loads(text_data)
	# 		message_type = data.get('type')

	# 		if message_type == 'chat_message':
	# 			await self.handle_chat_message(data)
	# 		elif message_type == 'game_action':
	# 			await self.handle_game_action(data)
	# 		else:
	# 			print(f"Received unknown message type: {message_type}", file=sys.stderr)
	# 	except json.JSONDecodeError:
	# 		print(f"Received invalid JSON: {text_data}", file=sys.stderr)
	# 	except Exception as e:
	# 		print(f"Error processing message: {e}", file=sys.stderr)
