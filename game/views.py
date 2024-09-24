from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import uuid
from django.core.cache import cache
import time
from django.shortcuts import render
import sys
class GameRoomViewSet(viewsets.ViewSet):
	def list(self, request):
		"""모든 게임 방 목록을 반환합니다."""
		game_room_datas = []
		game_rooms_keys = cache.keys('game_room_*')
		for room_key in game_rooms_keys:
			room = cache.get(room_key)
			if room['game_started']:
				continue
			if room is None:
				continue
			game_room_datas.append({
				'id': room['id'],
				'name': room['name'],
				'roomType': room['roomType'],
				'people': len(room['players']),
				'host': room['host'],
				'created_at': room['created_at']
			})
		# 생성된 시간 순으로 정렬
		game_room_datas.sort(key=lambda x: x['created_at'], reverse=True)
		
		
		return Response(game_room_datas, status=status.HTTP_200_OK)

	def create(self, request):
		"""새로운 게임 방을 생성합니다."""
		room_id = str(uuid.uuid4())
		room_data = {
			'id': room_id,
			'name': request.data.get('name'),
			'roomType': request.data.get('roomType'),
			'players': [{'username': request.data.get('nickname')}],
			'host': request.data.get('nickname'),
			'game_started': False,
			'created_at': time.time()
		}
		cache.set(f'game_room_{room_id}', room_data, timeout=3600)  # 1 hour timeout
		return Response(room_data, status=status.HTTP_201_CREATED)

	@action(detail=True, methods=['post'])
	def join(self, request):
		game_room_id = request.data.get('game_room_id')
		nickname = request.data.get('nickname')
		print("join called", file=sys.stderr)
		"""게임 방에 참가합니다."""
		room = cache.get(f'game_room_{game_room_id}')
		if not room:
			return Response({'error': 'Room not found'}, status=status.HTTP_404_NOT_FOUND)

		if (room['roomType'] == 0 and len(room['players']) >= 2) or (room['roomType'] == 1 and len(room['players']) >= 4):
			return Response({'error': 'Room is full'}, status=status.HTTP_400_BAD_REQUEST)

		if any(player['username'] == nickname for player in room['players']):
			return Response({'error': 'You are already in this room'}, status=status.HTTP_400_BAD_REQUEST)

		room['players'].append({'username': nickname})
		cache.set(f'game_room_{game_room_id}', room, timeout=3600)

		# Notify other players via WebSocket
		channel_layer = get_channel_layer()
		async_to_sync(channel_layer.group_send)(
			f'game_{game_room_id}',
			{
				'type': 'room_update',
				'room': room
			}
		)

		return Response(room)

	@action(detail=True, methods=['post'])
	def leave(self, request, pk=None):
		"""게임 방에서 나갑니다."""
		room = cache.get(f'game_room_{pk}')
		if not room:
			return Response({'error': 'Room not found'}, status=status.HTTP_404_NOT_FOUND)

		room['players'] = [p for p in room['players'] if p['username'] != request.user.username]

		if not room['players']:
			cache.delete(f'game_room_{pk}')
			event = 'room_closed'
		else:
			if room['host'] == request.user.username:
				room['host'] = room['players'][0]['username']
			cache.set(f'game_room_{pk}', room, timeout=3600)
			event = 'player_left'

		# Notify other players via WebSocket
		channel_layer = get_channel_layer()
		async_to_sync(channel_layer.group_send)(
			f'game_{pk}',
			{
				'type': 'room_update',
				'event': event,
				'room': room
			}
		)

		return Response({'message': 'Successfully left the room'})

	@action(detail=True, methods=['post'])
	def ready(self, request, pk=None):
		"""플레이어의 준비 상태를 변경합니다."""
		room = cache.get(f'game_room_{pk}')
		if not room:
			return Response({'error': 'Room not found'}, status=status.HTTP_404_NOT_FOUND)

		for player in room['players']:
			if player['username'] == request.user.username:
				player['ready'] = request.data.get('ready', not player['ready'])
				break
		else:
			return Response({'error': 'Player not in room'}, status=status.HTTP_400_BAD_REQUEST)

		cache.set(f'game_room_{pk}', room, timeout=3600)

		# Notify other players via WebSocket
		channel_layer = get_channel_layer()
		async_to_sync(channel_layer.group_send)(
			f'game_{pk}',
			{
				'type': 'room_update',
				'room': room
			}
		)

		return Response(room)

	@action(detail=True, methods=['post'])
	def start_game(self, request, pk=None):
		"""게임을 시작합니다."""
		room = cache.get(f'game_room_{pk}')
		if not room:
			return Response({'error': 'Room not found'}, status=status.HTTP_404_NOT_FOUND)

		if request.user.username != room['host']:
			return Response({'error': 'Only host can start the game'}, status=status.HTTP_403_FORBIDDEN)

		if not all(player['ready'] for player in room['players']):
			return Response({'error': 'Not all players are ready'}, status=status.HTTP_400_BAD_REQUEST)

		room['game_started'] = True
		cache.set(f'game_room_{pk}', room, timeout=3600)

		# Notify players via WebSocket
		channel_layer = get_channel_layer()
		async_to_sync(channel_layer.group_send)(
			f'game_{pk}',
			{
				'type': 'game_start',
				'room': room
			}
		)

		return Response(room)
	

def game_room_test(request):
	return render(request, 'game_room_test.html')