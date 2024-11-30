from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync, sync_to_async  # sync_to_async 추가
import uuid
from django.core.cache import cache
import time
from django.http import JsonResponse
from api.utils import CookieManager
from api.models import User
import sys
from django.shortcuts import render
from game.models import GameLog, UserGameLog
from django.db.models import F
from game.utils import RoomStateManager
import re



ROOM_TIMEOUT = 3600  # 1 hour


class GameRoomViewSet(viewsets.ViewSet):
	def __init__(self, **kwargs):
		super().__init__(**kwargs)
		self.room_manager = RoomStateManager()
		self.NICKNAME_PATTERN = re.compile(r'^[a-zA-Z0-9가-힣]*$')

	def list(self, request):
		print("list", sys.stderr)
		"""모든 게임 방 목록을 반환합니다."""
		@async_to_sync
		async def async_list():
			game_room_datas = []
			game_rooms_keys = await sync_to_async(cache.keys)('game_room_*')
			for room_key in game_rooms_keys:
				room = await self.room_manager.get_room(room_key)
				if not room:
					continue
				if len(room['players']) == 0 and room['roomType'] != 3 and room['roomType'] != 4:
					await self.room_manager.remove_room(room_key)
					continue
				if room and not room['game_started'] and int(room['roomType'] != 3) and int(room['roomType']) != 4:
					game_room_datas.append({
						'id': room['id'],
						'name': room['name'],
						'roomType': room['roomType'],
						'people': len(room['players']),
						'created_at': room['created_at']
					})
			game_room_datas.sort(key=lambda x: x['created_at'], reverse=True)
			return Response(game_room_datas, status=status.HTTP_200_OK)
		return async_list()

	def create(self, request):
		nickname = request.data.get('nickname')
		room_name = request.data.get('name')
		
		if not nickname or len(nickname) < 2 or len(nickname) > 10:
			return Response({'error': '닉네임은 2-10자 사이여야 합니다'}, status=status.HTTP_400_BAD_REQUEST)
			
		if not self.NICKNAME_PATTERN.match(nickname):
			return Response({'error': '닉네임은 한글, 영문, 숫자만 사용할 수 있습니다'}, status=status.HTTP_400_BAD_REQUEST)

		if not room_name or len(room_name) < 2 or len(room_name) > 10:
			return Response({'error': '방 이름은 2-10자 사이여야 합니다'}, status=status.HTTP_400_BAD_REQUEST)
		
		# 공백으로만 이루어진 방 이름은 허용하지 않음
		if not room_name.strip():
			return Response({'error': '방 이름은 공백으로만 이루어질 수 없습니다'}, status=status.HTTP_400_BAD_REQUEST )
		# 닉네임에는 공백이 들어갈 수 없음
		if ' ' in nickname:
			return Response({'error': '닉네임에는 공백이 들어갈 수 없습니다'}, status=status.HTTP_400_BAD_REQUEST)

		room_id = str(uuid.uuid4())
		room_data = {
			'id': room_id,
			'name': room_name,
			'roomType': request.data.get('roomType'),
			'players': [],
			'host': nickname,
			'game_started': False,
			'created_at': time.time() + (9 * 3600),
			'game1': [],
			'game2': [],
			'game1_ended': False,
			'game2_ended': False,
			'started_at': None,
			'disconnected': 0,
			'version': 0
		}
		print("Room id:", room_id, sys.stderr)
		
		@async_to_sync
		async def async_create():
			await self.room_manager.set_room(f'game_room_{room_id}', room_data)
			responseData = {"roomId": room_id}
			response = Response(responseData, status=status.HTTP_201_CREATED)
			CookieManager.set_nickname_cookie(response, nickname)
			return response
			
		return async_create()

	@action(detail=True, methods=['post'])
	def join(self, request):
		@async_to_sync
		async def async_join():
			game_room_id = request.data.get('roomId')
			nickname = request.data.get('nickname')
			if not nickname or len(nickname) < 2 or len(nickname) > 10:
				return Response({'error': '닉네임은 2-10자 사이여야 합니다'}, status=status.HTTP_400_BAD_REQUEST)

			if not self.NICKNAME_PATTERN.match(nickname):
				return Response({'error': '닉네임은 한글, 영문, 숫자만 사용할 수 있습니다'}, status=status.HTTP_400_BAD_REQUEST)
			
			room = await self.room_manager.get_room(f'game_room_{game_room_id}')
			if not room:
				return Response({'error': '방을 찾을 수 없습니다'}, status=status.HTTP_404_NOT_FOUND)
			
			# 내 intra_id가 이미 방에 있는지 확인

			if (room['roomType'] == 0 and len(room['players']) >= 2) or (room['roomType'] == 1 and len(room['players']) >= 4):
				return Response({'error': '방이 꽉 찼습니다'}, status=status.HTTP_400_BAD_REQUEST)

			if any(player['nickname'] == nickname for player in room['players']):
				return Response({'error': '다른 닉네임을 사용해주세요'}, status=status.HTTP_400_BAD_REQUEST)
			
			intra_id = CookieManager.get_intra_id_from_cookie(request)
			if any(player['intraId'] == intra_id for player in room['players']):
				return Response({'error': '이미 방에 참가하셨습니다'}, status=status.HTTP_400_BAD_REQUEST)
			user = await sync_to_async(User.get_by_intra_id)(intra_id)

			response = Response(status=status.HTTP_200_OK)
			CookieManager.set_nickname_cookie(response, nickname)
			return response

		return async_join()

	@action(detail=True, methods=['post'])
	def start_game(self, request):
		@async_to_sync 
		async def async_start_game():
			roomId = request.data.get('roomId')
			room = await self.room_manager.get_room(f'game_room_{roomId}')
			
			if not room:
				return Response({'error': 'Room not found'}, status=status.HTTP_404_NOT_FOUND)

			if (room['roomType'] == 0 and len(room['players']) != 2) or (room['roomType'] == 1 and len(room['players']) != 4):
				return Response({'error': 'Not enough players'}, status=status.HTTP_400_BAD_REQUEST)

			room['game_started'] = True
			room['started_at'] = time.time() + (9 * 3600)
			await self.room_manager.set_room(f'game_room_{roomId}', room)

			roomType = room['roomType'] 
			if roomType == 1:
				# Final room
				final_room_id = f"{roomId}_final"
				room1 = {
					'id': final_room_id,
					'name': '결승전',
					'roomType': 3,
					'players': [],
					'host': None,
					'game_started': False,
					'created_at': time.time(),
					'game1': [],
					'game2': [],
					'game1_ended': False,
					'game2_ended': False,
					'started_at': None,
					'disconnected': 0,
					'version': 0
				}
				await self.room_manager.set_room(f'game_room_{final_room_id}', room1)
				
				# 3rd place room
				third_room_id = f"{roomId}_3rd"
				room2 = {
					'id': third_room_id,
					'name': '3,4위 결정전',
					'roomType': 4,
					'players': [],
					'host': None,
					'game_started': False,
					'created_at': time.time(),
					'game1': [],
					'game2': [],
					'game1_ended': False,
					'game2_ended': False,
					'started_at': None,
					'disconnected': 0,
					'version': 0
				}
				await self.room_manager.set_room(f'game_room_{third_room_id}', room2)

			channel_layer = get_channel_layer()
			await channel_layer.group_send(
				f'room_{roomId}',
				{
					'type': 'game_start',
					'data': room
				}
			)
			return Response(status=status.HTTP_200_OK)

		return async_start_game()
	
	def players_info(self, request):
		
		response = {}
		roomId = request.data.get('roomId')
		print("roomId", roomId, sys.stderr)
		room = cache.get(f'game_room_{roomId}')
		print("room", room, sys.stderr)
		if not room:
			return Response({'error': 'Room not found'}, status=status.HTTP_404_NOT_FOUND)
		roomType = room['roomType']
		roomType = int(roomType)
		print("roomType", roomType, sys.stderr)
		if roomType == 0 or roomType == 3 or roomType == 4:
			intra_id = CookieManager.get_intra_id_from_cookie(request)
			response = {
				'matchType': roomType,
				'players': room['players'],
				'intraId': intra_id
			}
			return Response(response, status=status.HTTP_200_OK)
		elif roomType == 1 or roomType == 2:
			
			intra_id = CookieManager.get_intra_id_from_cookie(request)
			if not intra_id:
				return Response({'error': 'Invalid request'}, status=status.HTTP_400_BAD_REQUEST)
			print("intra_id", intra_id, sys.stderr)
			game1 = room['game1']
			game2 = room['game2']
			if not game1 or not game2:
				return Response({'error': 'Invalid request'}, status=status.HTTP_400_BAD_REQUEST)
			for player in game1:
				if player['intraId'] == intra_id:
					response = {
						'matchType': 1,
						'players': game1,
						'intraId': intra_id
					}
					print("response", response, sys.stderr)
					return Response(response, status=status.HTTP_200_OK)

			for player in game2:
				if player['intraId'] == intra_id:
					response = {
						'matchType': 2,
						'players': game2,
						'intraId': intra_id
					}
					print("response", response, sys.stderr)
					return Response(response, status=status.HTTP_200_OK)
		# error
		return Response({'error': 'Invalid request'}, status=status.HTTP_400_BAD_REQUEST)
	
	@action(detail=False, methods=['get'])
	def game_history(self, request):
		try:
			# 게임 로그와 유저 정보를 한 번에 조회
			game_logs = GameLog.objects.select_related().annotate(
				date=F('start_time')
			).values('id', 'date', 'match_type')
			result = []
			for game in game_logs:
				# 해당 게임의 유저 정보 조회 (점수 순 정렬)
				users = UserGameLog.objects.select_related('user').filter(
					game_log_id=game['id']
				).order_by('-score')[:2]  # 상위 2명만 가져옴
				
				# 2명의 유저가 있는 경우만 처리
				if len(users) == 2:
					result.append({
						'game_id': game['id'],
						'matchType': game['match_type'],
						'date': game['date'].strftime('%Y-%m-%d %H:%M:%S'),
						'leftId': str(users[0].user.id),
						'leftScore': str(users[0].score),
						'leftNick': users[0].nickname,
						'rightId': str(users[1].user.id),
						'rightScore': str(users[1].score),
						'rightNick': users[1].nickname
					})

			return JsonResponse({
				'history': result
			}, json_dumps_params={'ensure_ascii': False})  # 한글 처리를 위해 ensure_ascii=False 추가


		except Exception as e:
			return JsonResponse({
				'message': str(e)
			}, status=500)
		


def get_client_info(request):
    return JsonResponse({
        'intra_id': CookieManager.get_intra_id_from_cookie(request),
        'nickname': CookieManager.get_nickname_from_cookie(request)
    })

# def game_test(request):
# 	return render(request, 'game.html')