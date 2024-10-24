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
		try :
			room = await self.get_room()
			if not room:
				await self.close()
				return
		except Exception as e:
			print(f"Error getting room: {e}", file=sys.stderr)
			await self.close()
			return

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
		# if room is empty, delete it
		room = await self.get_room()
		if room and not room.get('players', []):
			print("Deleting room", file=sys.stderr)
			cache.delete(f'game_room_{self.room_id}')
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
			cache.delete(f'game_room_{self.room_id}')
			return
		if add:
			# 토너먼트 방식이라서 2명씩 묶어서 게임 시작


			if self.user_data['intraId'] not in [p['intraId'] for p in players]:
				players.append(self.user_data)

			if len(players) == 4:
				game1 = [players[0], players[1]]
				game2 = [players[2], players[3]]
				room['game1'] = game1
				room['game2'] = game2
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

	async def game_start(self, event):
		await self.send(text_data=json.dumps({
			'type': 'game_start',
			'data': event['data']
		}))






import json
import time
import random
import logging
import math
import sys
from channels.generic.websocket import AsyncWebsocketConsumer
from django.core.cache import cache
from asgiref.sync import sync_to_async

logger = logging.getLogger(__name__)

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
		# 남은 플레이어에게 승리 메시지 전송
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

	async def check_collisions(self):
		ball = self.game_state['ball']
		PADDLE_WIDTH = 2
		PADDLE_DEPTH = 0.5
		PADDLE_HEIGHT = 1
		BALL_RADIUS = 0.25

		for player_id, player in self.game_state['players'].items():
			z_pos = 7 if player_id == 'player1' else -7
			
			# 패들의 바운딩 박스 정의
			paddle_bounds = {
				'min_x': player['position']['x'] - PADDLE_WIDTH/2,
				'max_x': player['position']['x'] + PADDLE_WIDTH/2,
				'min_z': z_pos - PADDLE_DEPTH/2,
				'max_z': z_pos + PADDLE_DEPTH/2,
				'min_y': 0,
				'max_y': PADDLE_HEIGHT
			}

			# AABB 충돌 검사
			if (ball['position']['x'] + BALL_RADIUS > paddle_bounds['min_x'] and
				ball['position']['x'] - BALL_RADIUS < paddle_bounds['max_x'] and
				ball['position']['z'] + BALL_RADIUS > paddle_bounds['min_z'] and
				ball['position']['z'] - BALL_RADIUS < paddle_bounds['max_z']):

				# 충돌 위치는 항상 계산
				hit_position = (ball['position']['x'] - player['position']['x']) / (PADDLE_WIDTH/2)

				# 충돌이 감지되면 충돌 방향 결정
				penetration_x = min(
					abs(ball['position']['x'] - paddle_bounds['min_x']),
					abs(ball['position']['x'] - paddle_bounds['max_x'])
				)
				penetration_z = min(
					abs(ball['position']['z'] - paddle_bounds['min_z']),
					abs(ball['position']['z'] - paddle_bounds['max_z'])
				)

				current_speed = math.sqrt(ball['velocity']['x']**2 + ball['velocity']['z']**2)

				# 충돌 위치에 따른 반사 처리
				if penetration_x < penetration_z:
					# 패들의 측면과 충돌
					ball['velocity']['x'] *= -1
				else:
					# 패들의 전면/후면과 충돌
					ball['velocity']['z'] *= -1
					
					# 비선형적인 반사각 계산
					angle_factor = math.pow(abs(hit_position), 1.5) * math.copysign(1, hit_position)
					
					# 속도 성분 재계산
					ball['velocity']['x'] = current_speed * angle_factor * 0.5
					ball['velocity']['z'] = math.copysign(
						current_speed * math.sqrt(1 - (angle_factor * 0.5)**2),
						ball['velocity']['z']
					)

				# 최소/최대 속도 제한
				MAX_SPEED = 15
				MIN_SPEED = 5
				current_speed = math.sqrt(ball['velocity']['x']**2 + ball['velocity']['z']**2)
				
				if current_speed > MAX_SPEED:
					speed_scale = MAX_SPEED / current_speed
					ball['velocity']['x'] *= speed_scale
					ball['velocity']['z'] *= speed_scale
				elif current_speed < MIN_SPEED:
					speed_scale = MIN_SPEED / current_speed
					ball['velocity']['x'] *= speed_scale
					ball['velocity']['z'] *= speed_scale

				print(f"{player_id} hit! Position: {hit_position:.2f}, Speed: {current_speed:.2f}", 
					file=sys.stderr)

	async def update_game_state(self):
		current_time = time.time()
		delta_time = current_time - self.last_update_time
		self.last_update_time = current_time
		
		ball = self.game_state['ball']
		
		# 득점 애니메이션 중인지 확인
		if hasattr(self, 'score_animation') and self.score_animation['active']:
			if current_time - self.score_animation['start_time'] >= 1.5:  # 1.5초 후 리셋
				self.score_animation['active'] = False
				self.reset_ball()
			else:
				# 득점 애니메이션 중에는 공이 멈춤
				return
		else:
			# 일반 게임 플레이
			ball['position']['x'] += ball['velocity']['x'] * delta_time
			ball['position']['z'] += ball['velocity']['z'] * delta_time
			await self.check_collisions()

			# 벽 충돌 처리
			if abs(ball['position']['x']) > 5:
				ball['position']['x'] = math.copysign(5, ball['position']['x'])
				ball['velocity']['x'] *= -1

			# 득점 처리
			if abs(ball['position']['z']) > 7:
				scoring_player = 'player1' if ball['position']['z'] > 0 else 'player2'
				
				# 득점 처리 시작
				if not hasattr(self, 'score_animation'):
					self.score_animation = {'active': False, 'start_time': 0}
				
				if not self.score_animation['active']:
					self.game_state['score'][scoring_player] += 1
					print(f"Score! {scoring_player}", file=sys.stderr)
					
					# 공의 속도를 조정하여 더 멀리 날아가게 함
					ball['velocity']['z'] *= 1.5  # 공이 더 멀리 날아가도록 속도 증가
					self.score_animation = {
						'active': True,
						'start_time': current_time
					}

		await self.broadcast_partial_state()

	def reset_ball(self):
		# 초기 속도를 약간 랜덤하게 설정
		initial_speed = 7  # 기본 속도
		angle = random.uniform(-math.pi/4, math.pi/4)  # -45도에서 45도 사이의 각도
		
		vx = initial_speed * math.sin(angle)
		vz = initial_speed * math.cos(angle)
		
		# 무작위로 방향 선택
		if random.random() < 0.5:
			vz *= -1
		
		self.game_state['ball'] = {
			'position': {'x': 0, 'y': 0.2, 'z': 0},
			'velocity': {
				'x': vx,
				'y': 0,
				'z': vz
			}
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



# DB 게임시작할때 초기 데이터 넣고
# 3점 게임 방식
# 관전 방식 
# 