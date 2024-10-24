import json
from channels.generic.websocket import AsyncWebsocketConsumer
from django.core.cache import cache
from channels.db import database_sync_to_async
import sys
from typing import Dict, Any
from api.models import User
from urllib.parse import parse_qs
import time
ROOM_TIMEOUT = 3600  # 1 hour
import asyncio

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
			user : User = await self.get_user(intra_id)
			self.user_data = {'intraId': intra_id, 'nickname': nickname, 'profileImage': user.profile_image}
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
		return User.get_by_intra_id(intra_id)

	@database_sync_to_async
	def get_room(self) -> Dict[str, Any]:
		return cache.get(f'game_room_{self.room_id}')

	@database_sync_to_async
	def set_room(self, room: Dict[str, Any]):
		if room['host'] is None:
			cache.delete(f'game_room_{self.room_id}')
		else:
			cache.set(f'game_room_{self.room_id}', room, timeout=ROOM_TIMEOUT)

	async def update_room_players(self, add: bool):
		print(f"Updating room players: {add}", file=sys.stderr)
		room = await self.get_room()
		if not room:
			return

		players = room.get('players', [])
		if not add and len(players) == 0:
			return
		if add:
			if self.user_data['intraId'] not in [p['intraId'] for p in players]:
				players.append(self.user_data)
		else:
			players = [p for p in players if p['intraId'] != self.user_data['intraId']]
			# change host if host leaves
			if room['host'] == self.user_data['intraId']:
				if players:
					room['host'] = players[0]['intraId']
				else:
					room['host'] = None
					cache.delete(f'game_room_{self.room_id}')

					

		room['players'] = players
		await self.set_room(room)
		await self.broadcast_room_update(room)

	async def broadcast_room_update(self, room: Dict[str, Any]):
		await self.channel_layer.group_send(
			self.room_group_name,
			{
				'type': 'room_update',
				'data': room
			}
		)

	async def room_update(self, event):
		room = event['data']
		await self.send(text_data=json.dumps({
			'type': 'room_update',
			'data': room
		}))





import json
import time
import random
import logging
import asyncio
import sys
from channels.generic.websocket import AsyncWebsocketConsumer
from django.core.cache import cache
from asgiref.sync import sync_to_async
import math

logger = logging.getLogger(__name__)

class GamePysics:
# 물리 상수
    WALL_X = 5.0
    WALL_BOUNCE_FACTOR = 0.98
    PADDLE_WIDTH = 2.0
    PADDLE_DEPTH = 0.5
    PADDLE_Z = 7.0
    SCORE_Z = 7.5
    
    # 속도 제한
    MIN_VELOCITY = 3.0
    MAX_VELOCITY = 15.0
    
    # 게임 설정
    INITIAL_BALL_SPEED = 8.0
    MIN_ANGLE = math.pi/6  # 30도
    MAX_ANGLE = math.pi/3  # 60도
    
    # 충돌 설정
    EDGE_THRESHOLD = 0.1
    EDGE_BOUNCE_FACTOR = 0.8
    EDGE_HIT_MULTIPLIER = 1.2

class GameState:
	active_games = {}
	
	@classmethod
	def get_game(cls, game_id):
		if game_id not in cls.active_games:
			cls.active_games[game_id] = {
				'ball': {'position': {'x': 0, 'y': 0.2, 'z': 0}, 
						'velocity': {'x': 5, 'y': 0, 'z': 5}},
				'players': {},
				'score': {'player1': 0, 'player2': 0},
				'timestamp': int(time.time() * 1000),
				'lastProcessedInput': {'player1': 0, 'player2': 0},
				'game_started': False
			}
		return cls.active_games[game_id]

	@classmethod
	def remove_game(cls, game_id):
		if game_id in cls.active_games:
			del cls.active_games[game_id]

class GamePingPongConsumer(AsyncWebsocketConsumer):
	def __init__(self):
		super().__init__()
		self.game_id = None
		self.game_group_name = None
		self.player_number = None
		self.nickname = None
		self.game_state = None
		self.last_update_time = time.time()
		self.update_interval = 1/60  # 60 FPS
		self.backup_task = None

	async def connect(self):
		self.game_id = self.scope['url_route']['kwargs']['game_id']
		self.game_group_name = f'game_{self.game_id}'
		self.nickname = self.scope['query_string'].decode().split('=')[1]
		
		self.game_state = GameState.get_game(self.game_id)
		
		await self.channel_layer.group_add(self.game_group_name, self.channel_name)
		await self.accept()

		self.player_number = await self.assign_player_number()
		
		if self.player_number:
			print(f"Player number: {self.player_number}", file=sys.stderr)
			await self.send(json.dumps({
				'type': 'player_assigned',
				'player_number': self.player_number
			}))
			logger.info(f"Player {self.nickname} assigned as {self.player_number}")
			
			if len(self.game_state['players']) == 2:
				await self.start_game()
				self.backup_task = asyncio.create_task(self.periodic_backup())
		else:
			logger.warning(f"Failed to assign player number for {self.nickname}")
			await self.send(json.dumps({
				'type': 'connection_failed',
				'reason': 'Game is full'
			}))
			await self.close()

	async def assign_player_number(self):
		if 'player1' not in self.game_state['players']:
			self.game_state['players']['player1'] = {'position': {'x': -1, 'z': -1}}
			print(f"Player 1 assigned to {self.nickname}", file=sys.stderr)
			return 'player1'
		elif 'player2' not in self.game_state['players']:
			self.game_state['players']['player2'] = {'position': {'x': -1, 'z': -1}}
			print(f"Player 2 assigned to {self.nickname}", file=sys.stderr)
			return 'player2'
		print(f"No player slot available for {self.nickname}", file=sys.stderr)
		return None

	async def disconnect(self, close_code):
		if self.backup_task:
			self.backup_task.cancel()
			
		if self.player_number and self.game_state:
			if self.player_number in self.game_state['players']:
				del self.game_state['players'][self.player_number]
			
			if not self.game_state['players']:
				GameState.remove_game(self.game_id)
				
		await self.channel_layer.group_discard(self.game_group_name, self.channel_name)
		logger.info(f"Player {self.nickname} disconnected")

	async def receive(self, text_data):
		try:
			data = json.loads(text_data)
			print(f"Received data: {data}", file=sys.stderr)
			
			if data['type'] == 'client_state_update':
				await self.handle_client_update(data)
			elif data['type'] == 'sync_time':
				await self.sync_time(data)
			elif data['type'] == 'request_game_state':
				await self.send_full_game_state()
		except json.JSONDecodeError:
			logger.error(f"Invalid JSON received: {text_data}")
		except KeyError as e:
			logger.error(f"Missing key in received data: {e}")
		except Exception as e:
			logger.error(f"Unexpected error in receive: {e}")

	async def start_game(self):
		self.game_state['game_started'] = True
		
		await self.channel_layer.group_send(
			self.game_group_name,
			{
				'type': 'game_message',
				'message': {'type': 'game_start'}
			}
		)
		logger.info(f"Game {self.game_id} started")
		asyncio.create_task(self.game_loop())

	async def game_loop(self):
		while self.game_state['game_started']:
			current_time = time.time()
			
			if current_time - self.last_update_time >= self.update_interval:
				await self.update_game_state()
				self.last_update_time = current_time
			
			await asyncio.sleep(0.001)

	async def update_game_state(self):
		current_time = time.time()
		delta_time = min(current_time - self.last_update_time, 0.032)  # 최대 32ms로 제한
		self.last_update_time = current_time
		
		ball = self.game_state['ball']
		
		# 이전 위치 저장 (충돌 후 위치 보정에 사용)
		prev_x = ball['position']['x']
		prev_z = ball['position']['z']
		
		# 새 위치 계산
		new_x = ball['position']['x'] + ball['velocity']['x'] * delta_time
		new_z = ball['position']['z'] + ball['velocity']['z'] * delta_time
		
		# 벽 충돌 처리 (부드러운 반사)

		
		
		if abs(new_x) > GamePysics.WALL_X:
			# 정확한 충돌 지점으로 되돌리기
			penetration = abs(new_x) - GamePysics.WALL_X
			ball['position']['x'] = (GamePysics.WALL_X if new_x > 0 else - GamePysics.WALL_X) - (penetration * 0.1)
			ball['velocity']['x'] *= -GamePysics.WALL_BOUNCE_FACTOR
		else:
			ball['position']['x'] = new_x
			
		ball['position']['z'] = new_z
		
		# 패들 충돌 처리
		await self.check_paddle_collisions(prev_x, prev_z)
		
		# 득점 판정
		
		if abs(ball['position']['z']) > GamePysics.SCORE_Z:
			scoring_player = 'player1' if ball['position']['z'] > 0 else 'player2'
			self.game_state['score'][scoring_player] += 1
			print(f"Score! {scoring_player}", file=sys.stderr)
			self.reset_ball()
		
		await self.broadcast_partial_state()

	async def check_paddle_collisions(self, prev_x, prev_z):
		ball = self.game_state['ball']
		
		
		
		for player_id, player in self.game_state['players'].items():
			paddle_z = GamePysics.PADDLE_Z if player_id == 'player1' else -GamePysics.PADDLE_Z
			paddle_x = player['position']['x']
			
			# 패들과의 거리 계산
			dx = ball['position']['x'] - paddle_x
			dz = ball['position']['z'] - paddle_z
			
			# 패들 충돌 영역 확인
			if (abs(dz) < GamePysics.PADDLE_DEPTH and 
				abs(dx) < GamePysics.PADDLE_WIDTH/2):
				
				# 모서리 충돌 확인
				edge_hit = abs(dx) > (GamePysics.PADDLE_WIDTH/2 - 0.1)
				
				# 이전 위치를 기반으로 더 정확한 충돌 방향 결정
				from_front = (prev_z - paddle_z) * ball['velocity']['z'] < 0
				
				if edge_hit and not from_front:
					# 모서리 충돌: 더 극적인 반사각
					hit_factor = 1.2 if dx > 0 else -1.2
					ball['velocity']['x'] = abs(ball['velocity']['z']) * hit_factor
					ball['velocity']['z'] *= -0.8
				else:
					# 일반 충돌
					# 히트 포인트에 따른 반사각 계산 (-1.0 to 1.0)
					hit_position = dx / (GamePysics.PADDLE_WIDTH/2)
					
					# 기본 반사
					ball['velocity']['z'] *= -1.0
					
					# X 속도 조정 (히트 포인트에 따라)
					velocity_adjustment = hit_position * 8.0
					new_x_velocity = ball['velocity']['x'] + velocity_adjustment
					
					# 전체 속도 벡터 정규화
					total_velocity = (new_x_velocity ** 2 + ball['velocity']['z'] ** 2) ** 0.5
					if total_velocity > GamePysics.MAX_VELOCITY:
						scale = GamePysics.MAX_VELOCITY / total_velocity
						new_x_velocity *= scale
						ball['velocity']['z'] *= scale
					elif total_velocity < GamePysics.MIN_VELOCITY:
						scale = GamePysics.MIN_VELOCITY / total_velocity
						new_x_velocity *= scale
						ball['velocity']['z'] *= scale
					
					ball['velocity']['x'] = new_x_velocity
				
				# 충돌 후 위치 보정 (패들 뚫림 방지)
				if from_front:
					ball['position']['z'] = paddle_z + (GamePysics.PADDLE_DEPTH * 1.1 * (-1 if ball['velocity']['z'] < 0 else 1))
				
				print(f"{player_id} hit! Position: {hit_position:.2f} Edge: {edge_hit}", file=sys.stderr)
				return

	def reset_ball(self):
		"""공을 중앙으로 리셋하고 랜덤한 방향으로 발사"""
		self.game_state['ball']['position'] = {'x': 0, 'y': 0.2, 'z': 0}
		
		# 랜덤한 각도로 발사 (너무 수직이나 수평에 가깝지 않게)
		angle = random.uniform(math.pi/6, math.pi/3)  # 30-60도
		direction = random.choice([-1, 1])  # 랜덤한 방향
		speed = 8.0
		
		self.game_state['ball']['velocity'] = {
			'x': math.cos(angle) * speed,
			'y': 0,
			'z': math.sin(angle) * speed * direction
		}

	async def handle_client_update(self, data):
		if not self.player_number:
			logger.error(f"Player number not assigned for {self.nickname}")
			return

		try:
			player = data['player']
			position = data['position']
			input_sequence = data['input_sequence']

			self.game_state['players'][player]['position'] = position
			self.game_state['lastProcessedInput'][player] = input_sequence
			print("self_game_state: ", self.game_state, file=sys.stderr)

			await self.channel_layer.group_send(
				self.game_group_name,
				{
					'type': 'opponent_update',
					'player': player,
					'position': position,
					'input_sequence': input_sequence
				}
			)
		except KeyError as e:
			logger.error(f"Missing key in client update data: {e}")
		except Exception as e:
			logger.error(f"Unexpected error in handle_client_update: {e}")

	async def opponent_update(self, event):
		if self.player_number != event['player']:
			await self.send(text_data=json.dumps({
				'type': 'opponent_update',
				'player': event['player'],
				'position': event['position'],
				'input_sequence': event['input_sequence']
			}))

	async def sync_time(self, data):
		await self.send(json.dumps({
			'type': 'sync_time',
			'client_timestamp': data['timestamp'],
			'server_timestamp': int(time.time() * 1000)
		}))

	async def broadcast_partial_state(self):
		updates = {
			'type': 'game_state_update',
			'ball': self.game_state['ball'],
			'score': self.game_state['score'],
			'timestamp': int(time.time() * 1000)
		}
		
		await self.channel_layer.group_send(
			self.game_group_name,
			{
				'type': 'state_update',
				'updates': updates
			}
		)

	async def state_update(self, event):
		await self.send(text_data=json.dumps(event['updates']))

	async def game_message(self, event):
		await self.send(text_data=json.dumps(event['message']))

	async def send_full_game_state(self):
		await self.send(json.dumps({
			'type': 'full_game_state',
			'game_state': self.game_state
		}))

	@sync_to_async
	def save_to_cache(self):
		cache.set(f'game_backup_{self.game_id}', self.game_state)

	async def periodic_backup(self):
		while True:
			try:
				await self.save_to_cache()
				await asyncio.sleep(300)
			except Exception as e:
				logger.error(f"Error in periodic backup: {e}")
				await asyncio.sleep(60)