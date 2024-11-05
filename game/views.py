from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
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



ROOM_TIMEOUT = 3600  # 1 hour


class GameRoomViewSet(viewsets.ViewSet):
	

	def list(self, request):
		print("list", sys.stderr)
		"""모든 게임 방 목록을 반환합니다."""
		game_room_datas = []
		game_rooms_keys = cache.keys('game_room_*')
		for room_key in game_rooms_keys:
			room = cache.get(room_key)
			# room에 플레이어가 없으면 삭제
			if len(room['players']) == 0:
				cache.delete(room_key)
				continue
			if room and not room['game_started']:
				game_room_datas.append({
					'id': room['id'],
					'name': room['name'],
					'roomType': room['roomType'],
					'people': len(room['players']),
					'created_at': room['created_at']
				})
		game_room_datas.sort(key=lambda x: x['created_at'], reverse=True)
		return Response(game_room_datas, status=status.HTTP_200_OK)

	def create(self, request):
		print("create", sys.stderr)
		"""새로운 게임 방을 생성합니다."""
		room_id = str(uuid.uuid4())
		room_data = {
			'id': room_id,
			'name': request.data.get('name'),
			'roomType': request.data.get('roomType'),
			'players': [],
			'host': request.data.get('nickname'),
			'game_started': False,
			'created_at': time.time(),
			'game1': [],
			'game2': [],
			'started_at': None
		}
		print("Room id:", room_id, sys.stderr)
		cache.set(f'game_room_{room_id}', room_data, timeout=ROOM_TIMEOUT)
		responseData = {"roomId": room_id}
		response = Response(responseData, status=status.HTTP_201_CREATED)
		# CookieManager.set_intra_id_cookie(response, 'dongkseo')
		CookieManager.set_nickname_cookie(response, request.data.get('nickname'))
		
		return response

	@action(detail=True, methods=['post'])
	def join(self, request):
		
		"""게임 방에 참가합니다."""
		game_room_id = request.data.get('roomId')
		print("game_room_id", game_room_id, sys.stderr)
		nickname = request.data.get('nickname')
		print("nickname", nickname, sys.stderr)
		room = cache.get(f'game_room_{game_room_id}')
		print("request.COOKIES", request.COOKIES, sys.stderr)


		if not room:
			return Response({'error': 'Room not found'}, status=status.HTTP_404_NOT_FOUND)

		if (room['roomType'] == 0 and len(room['players']) >= 2) or (room['roomType'] == 1 and len(room['players']) >= 4):
			return Response({'error': 'Room is full'}, status=status.HTTP_400_BAD_REQUEST)


		if any(player['nickname'] == nickname for player in room['players']):
			return Response({'error': 'Nickname already exists'}, status=status.HTTP_400_BAD_REQUEST)
		
		intra_id = CookieManager.get_intra_id_from_cookie(request)
		user = User.get_by_intra_id(intra_id)

		print("user", user, sys.stderr)
		
		room['players'].append({'intraId':intra_id, 'nickname': nickname, 'profileImage': user.profile_image})
		cache.set(f'game_room_{game_room_id}', room, timeout=ROOM_TIMEOUT)
		# nickname 쿠키 설정
		response = Response(status=status.HTTP_200_OK)
		CookieManager.set_nickname_cookie(response, nickname)

		channel_layer = get_channel_layer()
		async_to_sync(channel_layer.group_send)(
			f'game_{game_room_id}',
			{
				'type': 'room_update',
				'data': room
			}
		)
		return response

	@action(detail=True, methods=['post'])
	def start_game(self, request):
		roomId = request.data.get('roomId')
		"""게임을 시작합니다."""
		room = cache.get(f'game_room_{roomId}')
		if not room:
			return Response({'error': 'Room not found'}, status=status.HTTP_404_NOT_FOUND)

		# intra_id = CookieManager.get_intra_id_from_cookie(request)

		# host = room['host']
		
		# if intra_id != room['host']:
		# 	return Response({'error': 'Only host can start the game'}, status=status.HTTP_403_FORBIDDEN)
		

		# 인원수 체크
		if (room['roomType'] == 0 and len(room['players']) != 2) or (room['roomType'] == 1 and len(room['players']) != 4):
			return Response({'error': 'Not enough players'}, status=status.HTTP_400_BAD_REQUEST)

		room['game_started'] = True
		room['started_at'] = time.time()
		cache.set(f'game_room_{roomId}', room, timeout=ROOM_TIMEOUT)

		channel_layer = get_channel_layer()
		async_to_sync(channel_layer.group_send)(
			f'room_{roomId}',
			{
				'type': 'game_start',
				'data': room
			}
		)
		# 만약 토너면트 라면 패자 룸 승사 룸 생성 
		roomType = room['roomType']
		if roomType == 1: # 토너먼트
			room_id = roomId + '_final'
			room1 = {
				'id': room_id,
				'name': '결승전',
				'roomType': 3,
				'players': [],
				'host': None,
				'game_started': False,
				'created_at': time.time(),
				'game1': [],
				'game2': [],
				'started_at': None
			}
			cache.set(f'game_room_{room_id}', room1, timeout=ROOM_TIMEOUT)
			room_id = roomId + '_3rd'
			room2 = {
				'id': room_id,
				'name': '3,4위 결정전',
				'roomType': 4,
				'players': [],
				'host': None,
				'game_started': False,
				'created_at': time.time(),
				'game1': [],
				'game2': [],
				'started_at': None
			}
			cache.set(f'game_room_{room_id}', room2, timeout=ROOM_TIMEOUT)
		
		return Response(status=status.HTTP_200_OK)
	
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
				'success': True,
				'data': result
			})

		except Exception as e:
			return JsonResponse({
				'success': False,
				'message': str(e)
			}, status=500)
		


def get_client_info(request):
    return JsonResponse({
        'intra_id': CookieManager.get_intra_id_from_cookie(request),
        'nickname': CookieManager.get_nickname_from_cookie(request)
    })

# def game_test(request):
# 	return render(request, 'game.html')