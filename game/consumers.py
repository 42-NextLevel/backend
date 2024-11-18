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
		self.room_group_name = f'room_{self.room_id}'
		print("Cookies: ", self.scope['cookies'], file=sys.stderr)
		query_string = self.scope['query_string'].decode()
		query_params = parse_qs(query_string)
		
		try:
			room = await self.get_room()
			if not room:
				print(f"WebSocket REJECT - Room not found: {self.room_id}", file=sys.stderr)
				print(f"Cache key used: game_room_{self.room_id}", file=sys.stderr)
				await self.close()
				return
		except Exception as e:
			print(f"WebSocket REJECT - Error getting room: {e}", file=sys.stderr)
			print(f"Attempted room_id: {self.room_id}", file=sys.stderr)
			await self.close()
			return
		
		intra_id = query_params.get('intraId', [None])[0]
		nickname = query_params.get('nickname', [None])[0]
		print(f"nickname: {nickname}, intra_id: {intra_id}", file=sys.stderr)
		print(f"room_id: {self.room_id}", file=sys.stderr)
		print(f"room_group_name: {self.room_group_name}", file=sys.stderr)
		print(f"Room data: {room}", file=sys.stderr)  # 룸 데이터 출력
		
		if not nickname or not intra_id:
			print(f"WebSocket REJECT - Missing parameters:", file=sys.stderr)
			print(f"- Nickname provided: {nickname}", file=sys.stderr)
			print(f"- Intra ID provided: {intra_id}", file=sys.stderr)
			print(f"- Query parameters: {query_params}", file=sys.stderr)
			print(f"- Full query string: {query_string}", file=sys.stderr)
			await self.close()
			return

		try:
			user: User = await self.get_user(intra_id)
			if not user:
				print(f"WebSocket REJECT - User not found for intra_id: {intra_id}", file=sys.stderr)
				await self.close()
				return
			self.user_data = {'intraId': intra_id, 'nickname': nickname, 'profileImage': user.profile_image}
		except Exception as e:
			print(f"WebSocket REJECT - Error getting user data: {e}", file=sys.stderr)
			print(f"Attempted intra_id: {intra_id}", file=sys.stderr)
			await self.close()
			return

		try:
			await self.channel_layer.group_add(self.room_group_name, self.channel_name)
			await self.accept()
			await self.update_room_players(add=True)
		except Exception as e:
			print(f"WebSocket REJECT - Error in final connection steps: {e}", file=sys.stderr)
			await self.close()
			return

	async def disconnect(self, close_code):
		try:
			if hasattr(self, 'user_data'):
				await self.update_room_players(add=False)
			
			# room이 없는 경우 처리
			room = await self.get_room()
			if not room:
				await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
				return
				
			players = room.get('players', [])
			match_type = int(room.get('match_type', '0'))
			
			# tournament 게임(1, 2번 매치)에서 게임 시작 전 유저 나가면 destroy
			if (match_type in [1, 2]) and not room['game_started']:
				print(f"Tournament game {match_type} destroyed before start", file=sys.stderr)
				await self.channel_layer.group_send(
					self.room_group_name,
					{
						'type': 'destroy'
					}
				)
				await cache.delete(f'game_room_{self.room_id}')
				
			# 일반 게임에서 모든 플레이어가 나가고 게임 시작 전이면 삭제
			elif len(players) == 0 and not room['game_started']:
				print(f"Empty room {self.room_id} deleted", file=sys.stderr)
				await cache.delete(f'game_room_{self.room_id}')
				
			await self.channel_layer.group_discard(self.room_group_name, self.channel_name)
			
		except Exception as e:
			logger.error(f"Error in disconnect: {e}")
			# 에러가 발생해도 반드시 group_discard는 실행
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
		if not room or room['game_started'] == True:
			return

		players = room.get('players', [])
		print(f"Current players: {players}", file=sys.stderr)
		if not add and len(players) == 0:
			cache.delete(f'game_room_{self.room_id}')
			return
		if add:

			# 토너먼트 방식이라서 2명씩 묶어서 게임 시작
			if len(players) == 0 and not room.get('host'):
				room['host'] = self.user_data['nickname']


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
			print(f"Host: {room['host']}, User: {self.user_data['intraId']}", file=sys.stderr)
			print(f"Players: {players}", file=sys.stderr)
			if room['host'] == self.user_data['nickname']:
				if players:
					print("Changing host", file=sys.stderr)
					room['host'] = players[0]['nickname']
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
from django.utils import timezone
from .models import GameLog, UserGameLog

logger = logging.getLogger(__name__)

class GameState:
	active_games = {}
	_game_tasks = {}  # game_id를 키로 하는 task dict

	
	@classmethod
	def get_game(cls, game_id):
		if game_id not in cls.active_games:
			initial_speed = 8  # physics의 BALL_SPEED와 동일하게
			angle = random.uniform(-math.pi/4, math.pi/4)  # -45도에서 45도 사이의 랜덤 각도
			
			# 삼각함수로 x, y 방향 속도 계산
			vx = initial_speed * math.sin(angle)
			vy = (random.random() - 0.5) * 2  # y축 변화는 좀 더 자유롭게
			vz = initial_speed  # 기본 z축 속도
			
			# 50% 확률로 반대 방향으로
			if random.random() < 0.5:
				vz *= -1

			cls.active_games[game_id] = {
				'ball': {
					'position': {'x': 0, 'y': 0.2, 'z': -42/2},
					'velocity': {
						'x': vx,
						'y': vy,
						'z': vz
					},
				},
				'players': {},
				'score': {'player1': 0, 'player2': 0},
				'timestamp': int(time.time() * 1000),
				'lastProcessedInput': {'player1': 0, 'player2': 0},
				'game_started': False,
				'match_type': None,
				'disconnected_player': [],
				'is_paused': False,
				'pause_start_time': None,
				'game_loop_running': False
			}
		return cls.active_games[game_id]

	@classmethod
	def remove_game(cls, game_id):
		if game_id in cls.active_games:
			del cls.active_games[game_id]

	@classmethod
	def set_game_task(cls, game_id, task):
		cls._game_tasks[game_id] = task

	@classmethod
	def get_game_task(cls, game_id):
		return cls._game_tasks.get(game_id)
	
	@classmethod
	def remove_game_task(cls, game_id):
		if game_id in cls._game_tasks:
			del cls._game_tasks[game_id]

import math
import random
import logging

logger = logging.getLogger(__name__)

import math
import random
import logging

logger = logging.getLogger(__name__)

class GamePhysics:
	def __init__(self):
		# 터널 상수들
		self.TUNNEL_HEIGHT = 5
		self.TUNNEL_WIDTH = 8
		self.TUNNEL_LENGTH = 42
		
		# 패들 위치

		self.PADDLE_Z_PLAYER1 = -1  # Player 1 패들의 z 위치 (0에 가깝게)
		self.PADDLE_Z_PLAYER2 = -41  # Player 2 패들의 z 위치 (-42에 가깝게)

		# 공 상수
		self.BALL_SCALE = 1.5
		self.INITIAL_BALL_SCALE = 0.8
		
		# 패들 설정
		self.PADDLE_SIZE = 1
		self.HIT_THRESHOLD = 1.0  # 고정된 히트박스 크기
		self.BASE_HIT_THRESHOLD = 1.0
		self.MAX_BALL_SCALE = 2.0


		self.HIT_ZONE_DEPTH = 0.5
		
		# Player 1의 히트존 (0쪽)
		self.PLAYER1_HIT_ZONE_START = self.PADDLE_Z_PLAYER1 + self.HIT_ZONE_DEPTH
		self.PLAYER1_HIT_ZONE_END = self.PADDLE_Z_PLAYER1 - self.HIT_ZONE_DEPTH
		
		# Player 2의 히트존 (-42쪽)
		self.PLAYER2_HIT_ZONE_START = self.PADDLE_Z_PLAYER2 + self.HIT_ZONE_DEPTH
		self.PLAYER2_HIT_ZONE_END = self.PADDLE_Z_PLAYER2 - self.HIT_ZONE_DEPTH

		# 속도 관련 상수
		self.BALL_SPEED = 10
		self.BALL_SPEED_FACTOR = 4
		self.MIN_SPEED = 3
		self.MAX_SPEED = self.BALL_SPEED * 2.0  # 최대 속도 제한

		# 충돌 관련 상수
		self.COLLISION_ANGLE_FACTOR = 1.0  # 충돌 각도 영향력
		self.COLLISION_SPEED_INCREASE = 1.05  # 충돌 후 속도 증가 비율

		# 물리 연산 설정
		self.MAX_DELTA_TIME = 1/120
		self.PHYSICS_SUBSTEPS = 3

		# 로깅 설정
		self.debug_counter = 0
		self.LOG_INTERVAL = 60

		# 애니메이션 설정
		self.SCORE_ANIMATION_DURATION = 1.5
		self.GAME_RESUME_DELAY = 0.5

	def normalize_velocity(self, velocity, target_speed):
		"""속도 벡터를 정규화하여 일정한 속도 유지"""
		speed = math.sqrt(velocity['x']**2 + velocity['y']**2 + velocity['z']**2)
		if speed > target_speed:
			scale = target_speed / speed
			velocity['x'] *= scale
			velocity['y'] *= scale
			velocity['z'] *= scale
		return velocity

	def reset_ball(self):
		"""공을 터널 중앙에서 랜덤한 방향으로 시작"""
		initial_speed = self.BALL_SPEED
		angle = random.uniform(-math.pi/4, math.pi/4)
		
		vx = initial_speed * math.sin(angle)
		vy = (random.random() - 0.5) * 2
		vz = initial_speed
		
		if random.random() < 0.5:
			vz *= -1

		return {
			'position': {'x': 0, 'y': 0.2, 'z': -self.TUNNEL_LENGTH/2},
			'velocity': {'x': vx, 'y': vy, 'z': vz},
			'scale': self.BALL_SCALE
		}
	
	def calculate_ball_scale(self, z_position):
		# 터널 중앙점 계산 (예: -42 ~ 0 범위에서는 -21이 중앙)
		tunnel_center = -self.TUNNEL_LENGTH / 2
		
		# 중앙으로부터의 거리 계산 (절대값)
		distance_from_center = abs(z_position - tunnel_center)
		
		# 거리를 0~1 사이 값으로 정규화 (중앙이 0, 양 끝이 1)
		normalized_distance = distance_from_center / (self.TUNNEL_LENGTH / 2)
		
		# normalized_distance를 그대로 사용하면 중앙이 작고 양 끝이 큼
		progress = normalized_distance
		
		return self.INITIAL_BALL_SCALE + (self.MAX_BALL_SCALE - self.INITIAL_BALL_SCALE) * progress



	def calculate_hit_threshold(self, z_position):
		"""공의 z 위치에 따른 히트박스 크기 계산"""
		ball_scale = self.calculate_ball_scale(z_position)
		return self.BASE_HIT_THRESHOLD * (ball_scale / self.INITIAL_BALL_SCALE)

	async def _process_physics_substep(self, game_state, delta_time):
		ball = game_state['ball']
		current_time = int(time.time() * 1000)
		
		# 다음 위치 계산
		next_x = ball['position']['x'] + ball['velocity']['x'] * delta_time * self.BALL_SPEED_FACTOR
		next_y = ball['position']['y'] + ball['velocity']['y'] * delta_time * self.BALL_SPEED_FACTOR
		next_z = ball['position']['z'] + ball['velocity']['z'] * delta_time * self.BALL_SPEED_FACTOR

		# 공의 크기 업데이트
		ball['scale'] = self.calculate_ball_scale(next_z)
		
		# 1. 득점 체크
		if next_z <= -self.TUNNEL_LENGTH - 1:
			ball['position'].update({'x': next_x, 'y': next_y, 'z': next_z})
			return 'player1'
		elif next_z >= 1:
			ball['position'].update({'x': next_x, 'y': next_y, 'z': next_z})
			return 'player2'

		# 2. x, y축 벽 충돌 처리
		if abs(next_x) > self.TUNNEL_WIDTH:
			ball['velocity']['x'] *= -1
			next_x = math.copysign(self.TUNNEL_WIDTH - 0.01, next_x)
			
		if abs(next_y) > self.TUNNEL_HEIGHT:
			ball['velocity']['y'] *= -1
			next_y = math.copysign(self.TUNNEL_HEIGHT - 0.01, next_y)

		# Player 1 패들 충돌 검사 (0쪽)
		if (next_z >= self.PLAYER1_HIT_ZONE_END and 
			next_z <= self.PLAYER1_HIT_ZONE_START):
			
			player = game_state['players'].get('player1')
			if player:
				# 동적 히트박스 크기 계산
				current_hit_threshold = self.calculate_hit_threshold(next_z)
				
				dx = abs(next_x - player['position']['x'])
				dy = abs(next_y - player['position']['y'])
				distance = math.sqrt(dx * dx + dy * dy)
				
				if distance <= current_hit_threshold:
					hit_angle_x = (next_x - player['position']['x']) / current_hit_threshold
					hit_angle_y = (next_y - player['position']['y']) / current_hit_threshold
					
					current_speed = math.sqrt(
						ball['velocity']['x']**2 +
						ball['velocity']['y']**2 +
						ball['velocity']['z']**2
					)
					new_speed = min(current_speed * self.COLLISION_SPEED_INCREASE, self.MAX_SPEED)
					
					ball['velocity']['x'] = hit_angle_x * new_speed * self.COLLISION_ANGLE_FACTOR
					ball['velocity']['y'] = hit_angle_y * new_speed * self.COLLISION_ANGLE_FACTOR
					ball['velocity']['z'] = -abs(new_speed)
					
					ball['velocity'] = self.normalize_velocity(ball['velocity'], new_speed)
					next_z = self.PLAYER1_HIT_ZONE_END - 0.1

		# Player 2 패들 충돌 검사 (-42쪽)
		elif (next_z >= self.PLAYER2_HIT_ZONE_END and 
			next_z <= self.PLAYER2_HIT_ZONE_START):
			
			player = game_state['players'].get('player2')
			if player:
				# 동적 히트박스 크기 계산
				current_hit_threshold = self.calculate_hit_threshold(next_z)
				
				dx = abs(next_x - player['position']['x'])
				dy = abs(next_y - player['position']['y'])
				distance = math.sqrt(dx * dx + dy * dy)
				
				if distance <= current_hit_threshold:
					hit_angle_x = (next_x - player['position']['x']) / current_hit_threshold
					hit_angle_y = (next_y - player['position']['y']) / current_hit_threshold
					
					current_speed = math.sqrt(
						ball['velocity']['x']**2 +
						ball['velocity']['y']**2 +
						ball['velocity']['z']**2
					)
					new_speed = min(current_speed * self.COLLISION_SPEED_INCREASE, self.MAX_SPEED)
					
					ball['velocity']['x'] = hit_angle_x * new_speed * self.COLLISION_ANGLE_FACTOR
					ball['velocity']['y'] = hit_angle_y * new_speed * self.COLLISION_ANGLE_FACTOR
					ball['velocity']['z'] = abs(new_speed)
					
					ball['velocity'] = self.normalize_velocity(ball['velocity'], new_speed)
					next_z = self.PLAYER2_HIT_ZONE_START + 0.1

		# 위치 업데이트
		ball['position'].update({'x': next_x, 'y': next_y, 'z': next_z})
		game_state['timestamp'] = current_time

		return None

	async def process_physics(self, game_state, delta_time):
		delta_time = min(delta_time, self.MAX_DELTA_TIME)
		substep_delta = delta_time / self.PHYSICS_SUBSTEPS
		
		for _ in range(self.PHYSICS_SUBSTEPS):
			scoring_player = await self._process_physics_substep(game_state, substep_delta)
			if scoring_player:
				return scoring_player
				
		return None



class GameScoreHandler:
	def __init__(self, game_state, physics, channel_layer, game_group_name):
		self.game_state = game_state
		self.physics = physics
		self.channel_layer = channel_layer
		self.game_group_name = game_group_name
		self.score_animation = {'active': False, 'start_time': 0}
		self.WIN_SCORE = 5
		self.game_end = False

	async def handle_scoring(self, scoring_player):
		"""득점 처리"""
		if self.score_animation['active']:
			return
			
		print(f"Player {scoring_player} scored", file=sys.stderr)
		self.game_state['score'][scoring_player] += 1
		
		# 즉시 공 리셋
		self.game_state['ball'] = self.physics.reset_ball()
		
		# 승리 조건 확인
		if self.game_state['score'][scoring_player] >= self.WIN_SCORE:
			await self._handle_game_end(scoring_player)
		else:
			await self._handle_score_animation()

	async def _handle_game_end(self, winner):
		"""게임 종료 처리"""
		self.game_state['game_started'] = False
		self.game_end = True
		await self.channel_layer.group_send(
			self.game_group_name,
			{
				'type': 'game_end',
				'winner': winner,
				'match': self.game_state.get('match_type', '0')
			}
		)
		logger.info(f"Game ended. Winner: {winner}")

	async def _handle_score_animation(self):
		"""득점 애니메이션 처리"""
		self.score_animation = {
			'active': True,
			'start_time': time.time()
		}
		await asyncio.sleep(1)
		
		self.game_state['ball'] = self.physics.reset_ball()
		self.game_state['ball']['velocity']['z'] *= 1.5  # 더 빠르게

	async def update_score_animation(self):
		"""애니메이션 상태 업데이트"""
		if not self.score_animation['active']:
			return False
			
		current_time = time.time()
		if current_time - self.score_animation['start_time'] >= self.physics.SCORE_ANIMATION_DURATION:
			self.score_animation['active'] = False
			# 새 라운드 시작을 위한 리셋
			self.game_state['ball'] = self.physics.reset_ball()
			await asyncio.sleep(self.physics.GAME_RESUME_DELAY)
			return False
			
		return True
			


from datetime import datetime

class GamePingPongConsumer(AsyncWebsocketConsumer):
	def __init__(self):
		super().__init__()
		self.PLAYER_ASSIGN_EVENT = 0
		self.GAME_START_EVENT = 1
		self.GAME_STATE_UPDATE_EVENT = 2
		self.OPPONENT_UPDATE_EVENT = 3
		self.GAME_END_EVENT = 4

		self.game_id = None
		self.game_group_name = None
		self.player_number = None
		self.nickname = None
		self.intra_id = None
		self.game_state = None
		self.last_update_time = time.time()
		self.update_interval = 1/60  # 60 FPS
		self.backup_task = None
		self.physics = GamePhysics()
		self.last_cache_update = time.time()
		self.CACHE_UPDATE_INTERVAL = 0.1  # 100ms
		self.match = None
		self.PAUSE_DURATION = 10 # 10초
		self.pause_task = None
		self.game_started = False
		


	async def connect(self):
		super().__init__()
		self.UPDATE_RATE = 1/60  # 60 FPS
		self.game_id : str = self.scope['url_route']['kwargs']['game_id']
		self.game_group_name = f'game_{self.game_id}'
		query_string = self.scope['query_string'].decode()
		query_params = parse_qs(query_string)
		self.nickname = query_params.get('nickname', [None])[0]
		self.intra_id = query_params.get('intraId', [None])[0]
		self.score_handler = None
		self.last_update_time = time.time()
		self.POSITION_PRECISION = 3
		self.VELOCITY_PRECISION = 2
		self.match = self.game_id.split('_')[-1]  # 항상 마지막 값이 매치 타입
		print(f"Game ID: {self.game_id}", file=sys.stderr)
		print(f"Match type: {self.match}", file=sys.stderr)

		game_cache_key = f'game_status_{self.game_id}'
		print(f"Game cache key: {game_cache_key}", file=sys.stderr)
		game_status = await sync_to_async(cache.get)(game_cache_key)
		print(f"Game status: {game_status}", file=sys.stderr)

		if game_status is None:
			pass
		elif game_status is False:
			print(f"WebSocket REJECT - Game in progress: {self.game_id}", file=sys.stderr)
			await self.close()
			return
		
		self.game_state = GameState.get_game(self.game_id)
		# if self.game_state['game_started']:
		# 	print(f"WebSocket REJECT - Game already started for {self.nickname}", file=sys.stderr)
		# 	await self.close()
		# 	return
		# 탈주자 인지 확인
		is_reconnecting = False
		if self.nickname in self.game_state['disconnected_player']:
			print(f"Player {self.nickname} reconnecting to game", file=sys.stderr)
			self.game_state['disconnected_player'].remove(self.nickname)
			is_reconnecting = True

			if not self.game_state['disconnected_player']:
				self.game_state['is_paused'] = False
				self.game_state['pause_start_time'] = None
				if self.pause_task and not self.pause_task.done():
					self.pause_task.cancel()
					self.pause_task = None
			
		
		
		

		# 	return
		await self.channel_layer.group_add(self.game_group_name, self.channel_name)
		await self.accept()

		
		
		print("game_state: ", self.game_state, file=sys.stderr)
		self.game_state['match_type'] = self.match

		
		self.score_handler = GameScoreHandler(
		self.game_state,
		self.physics,
		self.channel_layer,
		self.game_group_name
		)


		self.player_number = await self.assign_player_number()
		
		
		if self.player_number:
			
			await self.send(json.dumps({
				'type': 'player_assigned',
				'player_number': self.player_number
			}))
			logger.info(f"Player {self.nickname} assigned as {self.player_number}")
			if is_reconnecting:
				print(f"Reconnection for {self.nickname}", file=sys.stderr)
				await self.handle_reconnection()
			if len(self.game_state['players']) == 2:
				print(f"Game starting for {self.nickname}", file=sys.stderr)
				await self.start_game()
				self.backup_task = asyncio.create_task(self.periodic_backup())
		else:
			logger.warning(f"Failed to assign player number for {self.nickname}")
			await self.send(json.dumps({
				'type': 'connection_failed',
				'reason': 'Game is full'
			}))
			await self.close()


	async def handle_reconnection(self):
		"""재연결 시 처리 로직"""
		# 기존 game_loop task가 있다면 종료
		# game_loop_task = GameState.get_game_task(self.game_id)
		# if game_loop_task:
		# 	game_loop_task.cancel()
		# 	try:
		# 		await game_loop_task
		# 	except asyncio.CancelledError:
		# 		pass
			
		# 현재 게임 상태 전송
		await self.send_reconnection_state()
		
		# 게임 재시작
		if not self.game_state['disconnected_player']:
			self.game_state['is_paused'] = False
			self.game_state['pause_start_time'] = None
			if self.pause_task and not self.pause_task.done():
				self.pause_task.cancel()
				self.pause_task = None
				
			# 새로운 game_loop 시작
			# self.game_state['game_loop_task'] = asyncio.create_task(self.game_loop())
			# print(f"Game resumed after reconnection countdown for {self.nickname}", file=sys.stderr)


		

	async def send_reconnection_state(self):
		current_state = {
			'type': 'initial_game_state',
			'ball': self.game_state['ball'],  # 이미 scale 포함
			'paddle': {
				'players': {
					'player1': self.game_state['players'].get('player1', {
						'position': {'x': 0, 'y': 0, 'z': self.physics.PADDLE_Z_PLAYER1}
					}),
					'player2': self.game_state['players'].get('player2', {
						'position': {'x': 0, 'y': 0, 'z': self.physics.PADDLE_Z_PLAYER2}
					})
				},
				'lastProcessedInput': self.game_state['lastProcessedInput']
			},
			'score': self.game_state['score'],
			'game_started': self.game_state['game_started'],
			'timestamp': int(time.time() * 1000)
		}
		await self.send(json.dumps(current_state))


	async def assign_player_number(self):
		if 'player1' not in self.game_state['players']:
			self.game_state['players']['player1'] = {'position': {'x': 1, 'y': 0, 'z': self.physics.PADDLE_Z_PLAYER1}}
			print(f"Player 1 assigned to {self.nickname}", file=sys.stderr)
			return 'player1'
		elif 'player2' not in self.game_state['players']:
			self.game_state['players']['player2'] = {'position': {'x': 1, 'y': 0, 'z': self.physics.PADDLE_Z_PLAYER2}}
			print(f"Player 2 assigned to {self.nickname}", file=sys.stderr)
			return 'player2'
		print(f"No player slot available for {self.nickname}", file=sys.stderr)
		return None

	async def disconnect(self, close_code):
		# 남은 플레이어에게 승리 메시지 전송
		game_loop_task = GameState.get_game_task(self.game_id)
		if game_loop_task:
			game_loop_task.cancel()
			try:
				await game_loop_task
			except asyncio.CancelledError:
				pass
			GameState.remove_game_task(self.game_id)

			
		print(f"Player {self.nickname} disconnected", file=sys.stderr)
		if self.game_state and self.game_state.get('game_started', False):
			# 게임 pause 상태 설정
			self.game_state['is_paused'] = True
			self.game_state['pause_start_time'] = time.time()
			print(f"Game paused for 30 seconds due to {self.nickname} disconnect", file=sys.stderr)
			if self.pause_task and not self.pause_task.done():
				self.pause_task.cancel()
			self.pause_task = asyncio.create_task(self.resume_game_after_delay())
			
		await self.handle_room_disconnect()

			
		# 게임 종료 처리
		if self.score_handler:
			self.score_handler.game_end = True
			self.score_handler = None


		if self.backup_task:
			self.backup_task.cancel()
			
		if self.player_number and self.game_state:
			if self.player_number in self.game_state['players']:
				print(f"Removing player {self.player_number} from game state", file=sys.stderr)
				del self.game_state['players'][self.player_number]
			
			if not self.game_state['players']:
				GameState.remove_game(self.game_id)
				
		await self.channel_layer.group_discard(self.game_group_name, self.channel_name)
		logger.info(f"Player {self.nickname} disconnected")

	async def handle_room_disconnect(self):
		# 1. 플레이어 탈주 기록 추가
		self.game_state['disconnected_player'].append(self.nickname)
		disconnect_count = len(self.game_state['disconnected_player'])
		print(f"Disconnected players: {self.game_state['disconnected_player']}", file=sys.stderr)
		print(f"Disconnect count: {disconnect_count}", file=sys.stderr)
		if disconnect_count == 2:
			await sync_to_async(cache.set)(f'game_status_{self.game_id}', False, timeout=ROOM_TIMEOUT)
			print(f"Game ended due to 2 players disconnecting", file=sys.stderr)
			# 2. 탈주자 수에 따른 처리
			# 같은 게임에서 2명 탈주한 경우 final 룸 처리
			if self.match == '0' or self.match == '3' or self.match == '4':
				return
			room_final = await cache.get(f'game_room_{self.game_id}_final')
			if room_final:
				num_disconnected = int(room_final.get('disconnected', 0))
				if num_disconnected > 0:
					await sync_to_async(cache.delete)(f'game_room_{self.game_id}_final')
				else:
					room_final['disconnected'] = num_disconnected + 1
					try:
						await sync_to_async(cache.set)(
							f'game_room_{self.game_id}_final', 
							room_final, 
							timeout=ROOM_TIMEOUT
						)
					except Exception as e:
						logger.error(f"Cache set error in final room: {e}")
			self.send_to_room_socket(room_id=room_final, event='destroy')
		
		

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

	async def count_start(self, event):
		await self.send(json.dumps({
			'type': 'countdown_start'
		}))
	async def start_game(self):
		
		await asyncio.sleep(1)
		
		self.game_state['game_started'] = True
		await self.channel_layer.group_send(
			self.game_group_name,
			{
				'type': 'game_message',
				'message': {'type': 'game_start'}
			}
		)
		
		
		game_loop_task = asyncio.create_task(self.game_loop())
		GameState.set_game_task(self.game_id, game_loop_task)
	async def countdown(self, event):
		print(f"Sending countdown event: {event}", file=sys.stderr)  # 디버그 로그
		
		# event에서 count 값을 가져옴 ('countdown' 대신 'count' 사용)
		await self.send(json.dumps({
			'type': 'countdown',
			'count': event.get('count', 3)  # 기본값 3 설정
		}))

	async def game_loop(self):
		

		# 시간 동기화 요청
		server_time = time.time()
		await self.channel_layer.group_send(
			self.game_group_name,
			{
				'type': 'sync_time',
				'server_time': server_time
			}
		)

			# 카운트다운 시퀀스 정보 전송
		countdown_sequence = {
			'type': 'countdown_sequence',
			'server_time': server_time,
			'sequence': [
				{'count': 3, 'delay': 1},  # 1초 후
				{'count': 2, 'delay': 2},  # 2초 후
				{'count': 1, 'delay': 3},  # 3초 후
				{'count': 'GO!', 'delay': 4}  # 4초 후
			]
		}

		await self.channel_layer.group_send(
			self.game_group_name,
			{
				'type': 'game_message',
				'message': countdown_sequence
			}
		)

		await asyncio.sleep(5)  # 카운트다운 완료 + 여유시간


		self.physics.game_started = True
		while self.game_state['game_started']:
			if not self.game_state['is_paused']:  # 공유 상태로 체크
				current_time = time.time()
				
				if current_time - self.last_update_time >= self.update_interval:
					await self.update_game_state()
					self.last_update_time = current_time
			
			await asyncio.sleep(self.UPDATE_RATE/2)

	async def update_game_state(self):
		current_time = time.time()
		delta_time = current_time - self.last_update_time
		
		# 로그 추가
		logger.debug(f"Raw delta time: {delta_time}")
		
		# 최소 프레임 시간 보장
		if delta_time < 1/120:  # 120 FPS
			return
			
		self.last_update_time = current_time

		# 득점 애니메이션 중인지 확인
		# print(f"Updating game state for {self.nickname}", file=sys.stderr)
		if await self.score_handler.update_score_animation():
			await self.save_to_cache()  # 득점 시 상태 저장

			return

		# 게임 물리 처리
		scoring_player = await self.physics.process_physics(self.game_state, delta_time)
		
		# 득점 처리
		if scoring_player:
			await self.save_to_cache()  # 득점 시 상태 저장
			await self.score_handler.handle_scoring(scoring_player)
		
		await self.broadcast_partial_state()

	async def game_end(self, event):
		await self.send(text_data=json.dumps({
			'type': 'game_end',
			'winner': event['winner'],
			'match': event['match']
		}))
		
		# 게임 상태 초기화
		self.game_state['game_started'] = False
		if self.backup_task:
			self.backup_task.cancel()
		
		game_cache_key = f'game_status_{self.game_id}'
		await sync_to_async(cache.set)(game_cache_key, False, timeout=180)
		print(f"Game {self.game_id} ended. Winner: {event['winner']}", file=sys.stderr)

		
		# 게임 로그 저장
		print(f"Game {self.game_id} ended. Winner: {event['winner']}", file=sys.stderr)
		await self.save_game_log(event['winner'])
		
		logger.info(f"Game {self.game_id} ended. Winner: {event['winner']}")
		
		await asyncio.sleep(8)
		GameState.remove_game(self.game_id)

	# 탈주자 처리
	async def handle_deserter(self, event):
		if self.match == '0' or self.match == '3' or self.match == '4':
			return
		if len(self.game_state['disconnected_player']) == 1:
			# 한 게임에서 1명 탈주한 경우 3rd 룸 처리
			print("Handling 3rd room disconnect", file=sys.stderr)
			room_3rd = await sync_to_async(cache.get)(f'game_room_{self.game_id}_3rd')
			if room_3rd:
				num_disconnected = int(room_3rd.get('disconnected', 0))
				if num_disconnected > 0:
					await sync_to_async(cache.delete)(f'game_room_{self.game_id}_3rd')
				else:
					room_3rd['disconnected'] = num_disconnected + 1
					try:
						await sync_to_async(cache.set)(
							f'game_room_{self.game_id}_3rd', 
							room_3rd, 
							timeout=ROOM_TIMEOUT
						)
					except Exception as e:
						logger.error(f"Cache set error in 3rd room: {e}")
			self.send_to_room_socket(room_id=room_3rd, event='destroy')
		

	
	async def save_blockchain_data(self, players):
		from contract.solidity.scripts.Web3Client import Web3Client
		from asgiref.sync import sync_to_async
		import os
		
		try:
			# 환경 변수 확인
			if not os.environ.get('ETHEREUM_PRIVATE_KEY') or not os.environ.get('WEB3_PROVIDER_URL'):
				print("Missing required environment variables", file=sys.stderr)
				return None

			# GameLog.objects.latest('id') 호출을 sync_to_async로 래핑
			get_latest_id = sync_to_async(lambda: GameLog.objects.latest('id').id)
			game_id = await get_latest_id()

			client = await sync_to_async(Web3Client)()
			start_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
			
			match_info = client.make_match_struct(
				start_time=start_time,
				match_type=int(self.match),
				user1=str(players[0]['intraId']),
				user2=str(players[1]['intraId']),
				nick1=str(players[0]['nickname']),
				nick2=str(players[1]['nickname']),
				score1=int(self.game_state['score']['player1']),
				score2=int(self.game_state['score']['player2'])
			)

			tx_hash = await client.add_match_history(game_id, match_info)
			print(f"Transaction sent. Hash: {tx_hash}", file=sys.stderr)
			return tx_hash

		except Exception as e:
			print(f"Error in blockchain operation: {str(e)}", file=sys.stderr)
			import traceback
			traceback.print_exc(file=sys.stderr)
			return None

	@sync_to_async
	def create_game_log(self, start_time, match_type):
		return GameLog.objects.create(
			start_time=start_time,
			match_type=match_type,
			address=None
		)

	@sync_to_async
	def create_user_game_log(self, user_id, game_log_id, nickname, score):
		return UserGameLog.objects.create(
			user_id=user_id,
			game_log_id=game_log_id,
			nickname=nickname,
			score=score
		)

	@sync_to_async
	def get_user_by_intra_id(self, intra_id):
		return User.get_by_intra_id(intra_id)

	@sync_to_async
	def handle_cache_operations(self, room_id, room, room_type):
		if room_type == 1 or room_type == 2:
			room[f'game{room_type}_ended'] = True
			if room.get('game1_ended', False) and room.get('game2_ended', False):
				cache.delete(f'game_room_{room_id}')
			cache.set(f'game_room_{room_id}', room)
		else:
			cache.delete(f'game_room_{room_id}')

	async def save_game_log(self, winner):
		print(f"Saving game log for {self.game_id}", file=sys.stderr)
		
		room_id = '_'.join(self.game_id.split('_')[:-1])
		print(f"Room ID: {room_id}", file=sys.stderr)
		
		room = await sync_to_async(cache.get)(f'game_room_{room_id}')
		if not room:
			print(f"Room {room_id} not found", file=sys.stderr)
			return
		
		room_type = int(self.match)
		
		if room_type in [1, 2] and room.get(f'game{room_type}_ended', False):
			return
		
		try:
			# started_at 처리
			if isinstance(room['started_at'], str):
				start_time = datetime.fromisoformat(room['started_at'])
			elif isinstance(room['started_at'], (int, float)):
				start_time = datetime.fromtimestamp(room['started_at'])
			else:
				start_time = datetime.now()
			
			# GameLog 생성
			game_log = await self.create_game_log(start_time, int(self.match))

			# 플레이어 정보 가져오기
			if room_type == 0:
				players = room['players']
			elif room_type == 1:
				players = room['game1']
				print("game1 players:", players, file=sys.stderr)
			elif room_type == 2:
				players = room['game2']
				print("game2 players:", players, file=sys.stderr)
			else:
				players = room['players']
			
			# 플레이어 로그 저장
			for i, player_data in enumerate(players, 1):
				player_number = f'player{i}'
				user = await self.get_user_by_intra_id(player_data['intraId'])
				print(f"Player {player_number}: {player_data['nickname']}, {player_data['intraId']}", file=sys.stderr)
				
				if user:
					score = self.game_state['score'].get(player_number, 0)
					await self.create_user_game_log(
						user.id,
						game_log.id,
						player_data['nickname'],
						score
					)
				else:
					print(f"User not found for {player_data['nickname']}", file=sys.stderr)
			
			# 블록체인 저장
			await self.save_blockchain_data(players)
			print(f"Game log saved: {game_log}", file=sys.stderr)
			
			# 캐시 처리
			await self.handle_cache_operations(room_id, room, room_type)
				
		except Exception as e:
			print(f"Error saving game log: {str(e)}", file=sys.stderr)
			import traceback
			traceback.print_exc(file=sys.stderr)

	async def handle_client_update(self, data):
		if not self.player_number:
			return

		try:
			player = data['player']
			position = data['position']  # 이제 x, y 좌표 모두 포함
			input_sequence = data['input_sequence']
			
			# 패들 위치 범위 검사
			if (abs(position['x']) > self.physics.TUNNEL_WIDTH or 
				abs(position['y']) > self.physics.TUNNEL_HEIGHT):
				return

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
		except Exception as e:
			logger.error(f"Error in handle_client_update: {e}")

	async def opponent_update(self, event):
		if self.player_number != event['player']:
			await self.send(text_data=json.dumps({
				'type': 'opponent_update',
				'player': event['player'],
				'position': event['position'],
				'input_sequence': event['input_sequence']
			}))

	async def sync_time(self, data):
		try:
			# 'timestamp' 또는 'client_time' 키를 사용
			client_time = data.get('timestamp', data.get('client_time', int(time.time() * 1000)))
			
			await self.send(json.dumps({
				'type': 'sync_time',
				'client_timestamp': client_time,
				'server_timestamp': int(time.time() * 1000)
			}))
		except Exception as e:
			logger.error(f"Error in sync_time: {e}, data: {data}")

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
		"""중요 게임 상태 주기적 백업"""
		while True:
			try:
				await self.save_to_cache()
				await asyncio.sleep(30)  # 30초마다 백업
			except Exception as e:
				logger.error(f"Error in periodic backup: {e}")
				await asyncio.sleep(60)  # 오류 발생시 1분 후 재시도
	
	async def send_to_room_socket(self, room_id, event_type, data):
		"""
		룸 소켓으로 메시지 전송
		
		Args:
			room_id (str): 대상 룸 ID
			event_type (str): 이벤트 타입
			data (dict): 전송할 데이터
		"""
		try:
			print(f"Sending {event_type} event to room {room_id}", file=sys.stderr)
			room_group_name = f'room_{room_id}'
			await self.channel_layer.group_send(
				room_group_name,
				{
					'type': event_type,
					**data
				}
			)
		except Exception as e:
			logger.error(f"Error sending to room socket: {e}")


	async def resume_game_after_delay(self):
		"""30초 후 게임 상태 확인 및 처리"""
		try:
			await asyncio.sleep(self.PAUSE_DURATION)
			
			if self.game_state['is_paused']:  # 여전히 pause 상태인 경우
				if len(self.game_state['disconnected_player']) == 1:
					disconnected_nickname = self.game_state['disconnected_player'][0]
					
					# disconnected_nickname이 현재 플레이어가 아니면 현재 플레이어가 승자
					winner = self.player_number if disconnected_nickname != self.nickname else ('player2' if self.player_number == 'player1' else 'player1')
					
					print(f"Game ended due to timeout. {disconnected_nickname} disconnected. Winner: {winner}", file=sys.stderr)
					
					await self.channel_layer.group_send(
						self.game_group_name,
						{
							'type': 'game_end',
							'winner': winner,
							'match': self.match
						}
					)
				else:
					# 모든 플레이어가 재연결된 상태라면 게임 재개
					self.game_state['is_paused'] = False
					self.game_state['pause_start_time'] = None
			
		except asyncio.CancelledError:
			print("Resume game task cancelled", file=sys.stderr)
		except Exception as e:
			logger.error(f"Error in resume_game_after_delay: {e}")
