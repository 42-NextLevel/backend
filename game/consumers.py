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
from django.utils import timezone
from .models import GameLog, UserGameLog

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
				'game_started': False,
				'match_type': None
			}
		return cls.active_games[game_id]

	@classmethod
	def remove_game(cls, game_id):
		if game_id in cls.active_games:
			del cls.active_games[game_id]
import math
import random
import logging

logger = logging.getLogger(__name__)

class GamePhysics:
	def __init__(self):
		# 게임 오브젝트 크기
		self.PADDLE_WIDTH = 2.1
		self.PADDLE_DEPTH = 0.1
		self.PADDLE_HEIGHT = 1
		self.BALL_RADIUS = 0.25
		
		# 충돌 및 물리 설정
		self.COLLISION_TOLERANCE = 0.1
		self.POSITION_ZONES = 7
		self.POSITION_PRECISION = 2
		self.VELOCITY_PRECISION = 1
		
		# 속도 관련 설정
		self.BASE_SPEED = 10
		self.MIN_SPEED = 5
		self.MAX_SPEED = 15
		self.SPEED_VARIANCE = 0.2
		self.SPEED_QUANTIZATION = 1
		
		# 각도 관련 설정
		self.ANGLE_VARIANCE = 0.6
		self.ANGLE_PRECISION = 2
		
		# 게임 영역 경계
		self.FIELD_WIDTH = 5
		self.FIELD_LENGTH = 7
		
		# 득점 애니메이션 설정
		self.SCORE_ANIMATION_DURATION = 1.5
		self.GAME_RESUME_DELAY = 0.5
		self.MAX_DELTA_TIME = 1/60  # 최대 델타 타임을 60fps 기준으로 제한
		self.PHYSICS_SUBSTEPS = 4    # 물리 연산 세부 단계 수
		self.BASE_SPEED = 10
		self.MIN_SPEED = 5
		self.MAX_SPEED = 30
		self.SPEED_VARIANCE = 0.2
		self.SPEED_QUANTIZATION = 1
		self.ACCELERATION_FACTOR = 1.03  # 각 충돌마다 3% 속도 증가
		self.MAX_ACCELERATION_SPEED = 35  # 최대 가속 속도 (기존 MAX_SPEED보다 높게 설정)
	
	async def process_physics(self, game_state, delta_time):
		"""게임 물리를 처리합니다."""
		# delta_time 제한
		delta_time = min(delta_time, self.MAX_DELTA_TIME)
		
		# 물리 연산을 여러 단계로 나누어 처리
		substep_delta = delta_time / self.PHYSICS_SUBSTEPS
		
		for _ in range(self.PHYSICS_SUBSTEPS):
			scoring_player = await self._process_physics_step(game_state, substep_delta)
			if scoring_player:
				return scoring_player
				
		return None
	
	async def _process_physics_step(self, game_state, delta_time):
		"""단일 물리 연산 스텝을 처리합니다."""
		ball = game_state['ball']
		
		# 이전 위치 저장 (충돌 감지 보완용)
		prev_position = {
			'x': ball['position']['x'],
			'z': ball['position']['z']
		}
		
		# 공 위치 업데이트
		ball['position']['x'] += ball['velocity']['x'] * delta_time
		ball['position']['z'] += ball['velocity']['z'] * delta_time
		
		# 이동 거리 계산
		movement_distance = math.sqrt(
			(ball['position']['x'] - prev_position['x'])**2 +
			(ball['position']['z'] - prev_position['z'])**2
		)
		
		# 로그 추가
		logger.debug(f"Ball movement distance: {movement_distance}")
		logger.debug(f"Delta time: {delta_time}")
		logger.debug(f"Ball velocity: {ball['velocity']}")
		
		# 벽 충돌 검사
		if abs(ball['position']['x']) > self.FIELD_WIDTH:
			ball['position']['x'] = math.copysign(self.FIELD_WIDTH, ball['position']['x'])
			ball['velocity']['x'] *= -1
			logger.debug("Ball hit wall")
		
		# 득점 검사
		if abs(ball['position']['z']) > self.FIELD_LENGTH:
			return 'player1' if ball['position']['z'] > 0 else 'player2'
		
		# 패들 충돌 검사
		for player_id, player in game_state['players'].items():
			# 이전 위치 정보 전달
			if self._check_paddle_collision(ball, player, player_id):
				logger.info(f"Ball hit {player_id}'s paddle")
				break
		
		return None


	
	def _check_paddle_collision(self, ball, player, player_id):
		"""패들과 공의 충돌을 검사합니다."""
		z_pos = self.FIELD_LENGTH if player_id == 'player1' else -self.FIELD_LENGTH
		
		# 이전 프레임에서의 공의 위치를 고려한 충돌 영역 계산
		paddle_area = {
			'left': player['position']['x'] - (self.PADDLE_WIDTH/2 + self.COLLISION_TOLERANCE),
			'right': player['position']['x'] + (self.PADDLE_WIDTH/2 + self.COLLISION_TOLERANCE),
			'front': z_pos - (self.PADDLE_DEPTH/2 + self.COLLISION_TOLERANCE),
			'back': z_pos + (self.PADDLE_DEPTH/2 + self.COLLISION_TOLERANCE)
		}
		
		# 디버깅을 위한 로그 추가
		logger.debug(f"Ball position: {ball['position']}")
		logger.debug(f"Paddle area: {paddle_area}")
		logger.debug(f"Ball velocity: {ball['velocity']}")
		
		# 충돌 검사 전에 공이 패들 방향으로 움직이는지 확인
		moving_towards_paddle = (
			(player_id == 'player1' and ball['velocity']['z'] > 0) or
			(player_id == 'player2' and ball['velocity']['z'] < 0)
		)
		
		# 충돌 검사
		if not moving_towards_paddle:
			return False
			
		if not self._is_collision(ball, paddle_area):
			return False
				
		# 충돌 위치 계산
		hit_pos = self._calculate_hit_position(ball, player)
		
		# 충돌 면 판정 (더 정확한 계산)
		z_center = (paddle_area['front'] + paddle_area['back']) / 2
		relative_z = abs(ball['position']['z'] - z_center)
		is_front_hit = relative_z > (self.PADDLE_DEPTH/4)
		
		# 충돌 처리
		if is_front_hit:
			self._handle_front_collision(ball, hit_pos)
		else:
			self._handle_side_collision(ball)
		
		# 최종 속도 조정
		self._adjust_final_velocity(ball)
		
		return True
	
	def _is_collision(self, ball, paddle_area):
		"""충돌 여부를 확인합니다."""
		# 여유 공간을 조금 더 주어 충돌 감지를 더 관대하게 처리
		extra_tolerance = self.COLLISION_TOLERANCE * 1.0
		
		return (
			ball['position']['x'] + self.BALL_RADIUS + extra_tolerance > paddle_area['left'] and
			ball['position']['x'] - self.BALL_RADIUS - extra_tolerance < paddle_area['right'] and
			ball['position']['z'] + self.BALL_RADIUS + extra_tolerance > paddle_area['front'] and
			ball['position']['z'] - self.BALL_RADIUS - extra_tolerance < paddle_area['back']
		)
	
	def _calculate_hit_position(self, ball, player):
		"""패들에서 공이 맞은 상대적 위치를 계산합니다."""
		raw_hit = (ball['position']['x'] - player['position']['x']) / (self.PADDLE_WIDTH/2)
		raw_hit = max(-1.0, min(1.0, raw_hit))
		
		# 구간화
		zone_size = 2.0 / (self.POSITION_ZONES - 1)
		hit_pos = round(raw_hit / zone_size) * zone_size
		return round(hit_pos, self.POSITION_PRECISION)
	
	def _handle_front_collision(self, ball, hit_pos):
		"""전면/후면 충돌을 처리합니다."""
		# 방향 전환
		ball['velocity']['z'] *= -1
		
		# 현재 속도 계산
		current_speed = math.sqrt(ball['velocity']['x']**2 + ball['velocity']['z']**2)
		
		# 각도 및 속도 계산
		zone_factor = abs(hit_pos)
		angle = round(self.ANGLE_VARIANCE * zone_factor * math.copysign(1, hit_pos), 
						self.ANGLE_PRECISION)
		
		# 새로운 속도 계산 (기본 속도에 가속도 적용)
		base_speed = current_speed * self.ACCELERATION_FACTOR  # 현재 속도에서 가속
		speed_mult = 1 + (zone_factor * self.SPEED_VARIANCE)
		target_speed = round(base_speed * speed_mult / self.SPEED_QUANTIZATION) * self.SPEED_QUANTIZATION
		
		# 최대 속도 제한
		target_speed = min(target_speed, self.MAX_ACCELERATION_SPEED)
		
		# 속도 벡터 업데이트
		ball['velocity']['x'] = round(target_speed * angle, self.VELOCITY_PRECISION)
		ball['velocity']['z'] = round(math.copysign(
			target_speed * math.sqrt(1 - angle**2),
			ball['velocity']['z']
		), self.VELOCITY_PRECISION)
	
	def _handle_side_collision(self, ball):
		"""측면 충돌을 처리합니다."""
		ball['velocity']['x'] *= -1
		
		# 측면 충돌시 감속
		current_speed = math.sqrt(ball['velocity']['x']**2 + ball['velocity']['z']**2)
		current_speed *= (1 - self.SPEED_VARIANCE/2)
		
		# 속도 벡터 정규화
		magnitude = math.sqrt(ball['velocity']['x']**2 + ball['velocity']['z']**2)
		scale = current_speed / magnitude
		
		ball['velocity']['x'] = round(ball['velocity']['x'] * scale, self.VELOCITY_PRECISION)
		ball['velocity']['z'] = round(ball['velocity']['z'] * scale, self.VELOCITY_PRECISION)
	
	def _adjust_final_velocity(self, ball):
		"""최종 속도를 제한하고 조정합니다."""
		current_speed = math.sqrt(ball['velocity']['x']**2 + ball['velocity']['z']**2)
		current_speed = round(current_speed / self.SPEED_QUANTIZATION) * self.SPEED_QUANTIZATION
		# 최대 속도 제한을 MAX_ACCELERATION_SPEED로 변경
		current_speed = max(self.MIN_SPEED, min(current_speed, self.MAX_ACCELERATION_SPEED))
		
		# 속도 벡터 정규화
		magnitude = math.sqrt(ball['velocity']['x']**2 + ball['velocity']['z']**2)
		velocity_scale = current_speed / magnitude
		
		# 최종 속도 적용
		ball['velocity']['x'] = round(ball['velocity']['x'] * velocity_scale, self.VELOCITY_PRECISION)
		ball['velocity']['z'] = round(ball['velocity']['z'] * velocity_scale, self.VELOCITY_PRECISION)
	
	def reset_ball(self):
		"""공을 초기 상태로 리셋합니다."""
		initial_speed = 7
		angle = random.uniform(-math.pi/4, math.pi/4)
		
		vx = initial_speed * math.sin(angle)
		vz = initial_speed * math.cos(angle)
		
		# 무작위 방향 선택
		if random.random() < 0.5:
			vz *= -1
		
		return {
			'position': {'x': 0, 'y': 0.2, 'z': 0},
			'velocity': {'x': vx, 'y': 0, 'z': vz}
		}

class GameScoreHandler:
	def __init__(self, game_state, physics, channel_layer, game_group_name):
		self.game_state = game_state
		self.physics = physics
		self.channel_layer = channel_layer
		self.game_group_name = game_group_name
		self.score_animation = {'active': False, 'start_time': 0}
		self.WIN_SCORE = 3

	async def handle_scoring(self, scoring_player):
		"""득점 처리를 합니다."""
		if self.score_animation['active']:
			return
			
		logger.info(f"Score! {scoring_player}")
		self.game_state['score'][scoring_player] += 1
		
		# 승리 조건 확인
		if self.game_state['score'][scoring_player] >= self.WIN_SCORE:
			await self._handle_game_end(scoring_player)
		else:
			await self._handle_score_animation()

	async def _handle_game_end(self, winner):
		"""게임 종료를 처리합니다."""
		self.game_state['game_started'] = False
		# match 정보를 위해서는 game_id가 필요한데, GamePingPongConsumer에서 가져와야 함
		await self.channel_layer.group_send(
			self.game_group_name,
			{
				'type': 'game_end',
				'winner': winner,
				'match': self.game_state.get('match_type', '0')  # match_type을 game_state에서 가져옴
			}
		)
		logger.info(f"Game ended. Winner: {winner}")

	async def _handle_score_animation(self):
		"""득점 애니메이션을 처리합니다."""
		current_time = time.time()
		self.score_animation = {
			'active': True,
			'start_time': current_time
		}
		
		# 공을 리셋하고 애니메이션 효과를 위한 속도 조정
		self.game_state['ball'] = self.physics.reset_ball()
		self.game_state['ball']['velocity']['z'] *= 1.5  # 더 멀리 날아가도록

	async def update_score_animation(self):
		"""득점 애니메이션 상태를 업데이트합니다."""
		if not self.score_animation['active']:
			return False
			
		current_time = time.time()
		if current_time - self.score_animation['start_time'] >= self.physics.SCORE_ANIMATION_DURATION:
			self.score_animation['active'] = False
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

	async def connect(self):
		super().__init__()
		self.UPDATE_RATE = 1/30  # 30Hz로 감소
		self.MIN_BROADCAST_INTERVAL = 1/30
		self.game_id : str = self.scope['url_route']['kwargs']['game_id']
		self.game_group_name = f'game_{self.game_id}'
		query_string = self.scope['query_string'].decode()
		query_params = parse_qs(query_string)
		self.nickname = query_params.get('nickname', [None])[0]
		self.intra_id = query_params.get('intra_id', [None])[0]
		self.score_handler = None
		self.last_update_time = time.time()
		self.POSITION_PRECISION = 3
		self.VELOCITY_PRECISION = 2
		self.match = self.game_id.split('_')[1] if len(self.game_id.split('_')) > 1 else '0'
		
		self.game_state = GameState.get_game(self.game_id)
		self.game_state['match_type'] = self.match

		
		await self.channel_layer.group_add(self.game_group_name, self.channel_name)
		await self.accept()

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
		
		
		logger.info(f"Game {self.game_id} started")
		asyncio.create_task(self.game_loop())
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



		while self.game_state['game_started']:
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
		if delta_time < 1/60:  # 60fps 이상의 업데이트는 제한
			return
			
		self.last_update_time = current_time

		# 득점 애니메이션 중인지 확인
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
		
		# 게임 로그 저장
		print(f"Game {self.game_id} ended. Winner: {event['winner']}", file=sys.stderr)
		await self.save_game_log(event['winner'])
		
		logger.info(f"Game {self.game_id} ended. Winner: {event['winner']}")
		
		await asyncio.sleep(10)
		GameState.remove_game(self.game_id)

	@sync_to_async
	def save_game_log(self, winner):
		print(f"Saving game log for {self.game_id}", file=sys.stderr)
		
		# Parse room_id from game_id
		room_id = self.game_id.split('_')[0]
		
		# Get room data from cache
		room = cache.get(f'game_room_{room_id}')
		if not room:
			print(f"Room {room_id} not found", file=sys.stderr)
			return
		
		try:
			# Handle different timestamp formats
			if isinstance(room['started_at'], str):
				start_time = datetime.fromisoformat(room['started_at'])
			elif isinstance(room['started_at'], (int, float)):
				start_time = datetime.fromtimestamp(room['started_at'])
			else:
				# If started_at is already a datetime object or another format
				start_time = datetime.now()  # Fallback to current time
				print(f"Warning: Unknown started_at format: {type(room['started_at'])}", file=sys.stderr)
			
			# Create GameLog
			game_log = GameLog.objects.create(
				start_time=start_time,
				match_type=self.match,
				address=None
			)
			
			# Create UserGameLog for each player
			for player_number, player_data in self.game_state['players'].items():
				if player_number == self.player_number:
					user = User.get_by_intra_id(self.intra_id)
					if user:
						score = self.game_state['score'].get(player_number, 0)
						UserGameLog.objects.create(
							user_id=user,
							game_log_id=game_log,
							nickname=self.nickname,
							score=score
						)
			
			print(f"Game log saved: {game_log}", file=sys.stderr)
			# Clean up cache after successful save
			cache.delete(f'game_room_{room_id}')
			
		except Exception as e:
			print(f"Error saving game log: {str(e)}", file=sys.stderr)
			# Log the full error traceback for debugging
			import traceback
			traceback.print_exc(file=sys.stderr)

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

			# 캐시 업데이트 쓰로틀링
			# current_time = time.time()
			# if current_time - self.last_cache_update >= self.CACHE_UPDATE_INTERVAL:
			# 	await self.save_to_cache()
			# 	self.last_cache_update = current_time

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
			logger.exception(e)

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



# DB 게임시작할때 초기 데이터 넣고
# 3점 게임 방식
# 관전 방식 
# 