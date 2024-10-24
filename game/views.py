from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import uuid
from django.core.cache import cache
import time
from django.shortcuts import render
from api.utils import CookieManager
from api.models import User
import sys


ROOM_TIMEOUT = 3600  # 1 hour


class GameRoomViewSet(viewsets.ViewSet):
	

	def list(self, request):
		print("list", sys.stderr)
		"""모든 게임 방 목록을 반환합니다."""
		game_room_datas = []
		game_rooms_keys = cache.keys('game_room_*')
		for room_key in game_rooms_keys:
			room = cache.get(room_key)
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
			'created_at': time.time()
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
		cache.set(f'game_room_{roomId}', room, timeout=ROOM_TIMEOUT)

		channel_layer = get_channel_layer()
		async_to_sync(channel_layer.group_send)(
			f'game_{roomId}',
			{
				'type': 'game_start',
				'data': room
			}
		)

		return Response(status=status.HTTP_200_OK)
	
	def players_info(self, request):
		response = {}
		roomId = request.data.get('roomId')
		room = cache.get(f'game_room_{roomId}')
		if not room:
			return Response({'error': 'Room not found'}, status=status.HTTP_404_NOT_FOUND)
		roomType = room['roomType']
		if roomType == 0:
			response = {
				'matchType': 0,
				'players': room['players']
			}
		elif roomType == 1:
			intra_id = CookieManager.get_intra_id_from_cookie(request)
			game1 = room['game1']
			game2 = room['game2']
			for player in game1:
				if player['intraId'] == intra_id:
					response = {
						'matchType': 1,
						'players': game1
					}
					return Response(response, status=status.HTTP_200_OK)

			for player in game2:
				if player['intraId'] == intra_id:
					response = {
						'matchType': 2,
						'players': game2
					}
					break
		return Response(response, status=status.HTTP_200_OK)
				

		

		return Response(room['players'], status=status.HTTP_200_OK)

def game_room_test(request):
	return render(request, 'game_room_test.html')

def socket_api_test(request):
	return render(request, 'socket_api_test.html')

from django.http import JsonResponse

def get_client_info(request):
    return JsonResponse({
        'intra_id': CookieManager.get_intra_id_from_cookie(request),
        'nickname': request.COOKIES.get('nickname')
    })
