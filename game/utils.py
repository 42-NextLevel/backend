import asyncio
from typing import Dict, Any, Optional
from datetime import datetime
from django.core.cache import cache
from asgiref.sync import sync_to_async
import logging
import random
import sys
import time

logger = logging.getLogger(__name__)

class RoomStateManager:
	def __init__(self):
		self.room_locks = {}
		self._lock_creation_lock = asyncio.Lock()

	async def get_room_lock(self, room_id: str) -> asyncio.Lock:
		# room_id가 딕셔너리인 경우 문자열로 변환
		
		
		async with self._lock_creation_lock:
			if room_id not in self.room_locks:
				self.room_locks[room_id] = asyncio.Lock()
			return self.room_locks[room_id]

	async def get_room(self, room_id: str) -> Optional[Dict[str, Any]]:
		"""Room 데이터 조회"""
		# room_id가 딕셔너리인 경우 문자열로 변환
		
			
		result = await sync_to_async(cache.get)(room_id)
		return result

	async def set_room(self, room_id: str, room: Dict[str, Any]):
		"""Room 데이터 저장"""
		# room_id가 딕셔너리인 경우 문자열로 변환
		print("set Room id:", room_id, sys.stderr)
		print("set Room:", room, sys.stderr)
		
		if  (int(room['roomType']) == 3 or int(room['roomType'] == 4)) and int(room['version']) == 0:
			print("set Room id:", room_id, sys.stderr)
			await sync_to_async(cache.set)(room_id, room)
			return
			
		if room['host'] is None:
			await sync_to_async(cache.delete)(room_id)
		else:
			await sync_to_async(cache.set)(room_id, room)


	async def update_room_with_retry(self, room_id: str, update_func, max_retries: int = 5) -> Optional[Dict[str, Any]]:
		"""충돌 시 반복 재시도를 수행하는 업데이트 로직"""
		for attempt in range(max_retries):
			try:
				current_room = await self.get_room(room_id)
				if not current_room:
					return None

				current_version = current_room.get('version', 0)
				result = await self.try_update_room(room_id, update_func, current_version)
				
				if result:
					logger.debug(f"Update successful for room_id {room_id} on attempt {attempt + 1}")
					return result

				logger.debug(f"Version conflict detected for room_id {room_id} on attempt {attempt + 1}")
				await asyncio.sleep(0.1 * (2 ** attempt))

			except Exception as e:
				logger.error(f"Error in update_room_with_retry: {e}")
				if attempt == max_retries - 1:
					break

		logger.error(f"Failed to update room {room_id} after {max_retries} attempts")
		return None

	async def try_update_room(self, room_id: str, update_func, current_version: int) -> Optional[Dict[str, Any]]:
		"""단일 업데이트 시도를 수행"""
		lock = await self.get_room_lock(room_id)
		async with lock:
			try:
				current_room = await self.get_room(room_id)
				if not current_room:
					return None

				if current_room['version'] != current_version:
					logger.debug(f"Version conflict detected for room {room_id}. Reloading state.")
					return None

				# 업데이트 함수 실행
				updated_room = (
					await update_func(current_room.copy())
					if asyncio.iscoroutinefunction(update_func)
					else update_func(current_room.copy())
				)

				if not updated_room:
					return None

				# 버전 및 타임스탬프 업데이트
				updated_room['version'] = current_room['version'] + 1
				updated_room['last_modified'] = datetime.now().isoformat()

				await self.set_room(room_id, updated_room)
				return updated_room

			except Exception as e:
				logger.error(f"Error in try_update_room: {e}")
				return None

	async def apply_update_safely(self, room_id: str, update_type: str, update_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
		"""안전한 업데이트 적용"""
		async def perform_update(current_room: Dict[str, Any]) -> Optional[Dict[str, Any]]:
			if current_room is None or (current_room.get('host') is None and current_room.get('roomType') not in [3, 4]):
				logger.debug(f"No valid room found for room_id {room_id}")
				return None

			try:
				updated_room = current_room.copy()
				
				if update_type == "add_player":
					player_data = {
						'intraId': update_data['intraId'],
						'nickname': update_data['nickname'],
						'profileImage': update_data['profileImage']
					}
					# if player_data['intraId'] not in [p['intraId'] for p in updated_room.get('players', [])]:
					updated_room.setdefault('players', []).append(player_data)
					if not updated_room.get('host'):
						updated_room['host'] = player_data['nickname']
							
				elif update_type == "remove_player":
					updated_room['players'] = [
						p for p in updated_room.get('players', [])
						if p['intraId'] != update_data['intraId']
					]
					if updated_room.get('host') == update_data['nickname']:
						updated_room['host'] = updated_room['players'][0]['nickname'] if updated_room['players'] else None
						
				elif update_type == "update_game_state":
					# 게임 상태 업데이트
					if 'game_started' in update_data:
						updated_room['game_started'] = update_data['game_started']
					if 'started_at' in update_data:
						updated_room['started_at'] = update_data['started_at']
					if 'game1' in update_data:
						updated_room['game1'] = update_data['game1']
					if 'game2' in update_data:
						updated_room['game2'] = update_data['game2']
					if 'game1_ended' in update_data:
						updated_room['game1_ended'] = update_data['game1_ended']
					if 'game2_ended' in update_data:
						updated_room['game2_ended'] = update_data['game2_ended']
					if 'disconnected' in update_data:
						updated_room['disconnected'] = update_data['disconnected']
				
				logger.debug(f"Update type {update_type} applied to room_id {room_id}: {updated_room}")
				return updated_room

			except Exception as e:
				logger.error(f"Error during perform_update for room_id {room_id}: {e}")
				return None

		return await self.update_room_with_retry(room_id, perform_update)

	async def remove_room(self, room_id: str) -> bool:
		"""Room 즉시 삭제"""
		try:
			await sync_to_async(cache.delete)(room_id)
			return True
		except Exception as e:
			logger.error(f"Error removing room {room_id}: {e}")
			return False

	async def remove_room_safely(self, room_id: str) -> bool:
		"""Room을 안전하게 삭제 (lock 사용)"""
		async def delete_room(current_room: Dict[str, Any]) -> Optional[Dict[str, Any]]:
			if current_room is None:
				return None
			# host를 None으로 설정하면 set_room에서 삭제 처리
			current_room['host'] = None
			return current_room

		result = await self.update_room_with_retry(room_id, delete_room)
		return result is not None
	


class WebsocketEventMixin:
	"""
	웹소켓 이벤트 전송을 위한 공통 메서드를 제공하는 Mixin
	"""
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

			# 해당 그룹에 join
			await self.channel_layer.group_add(room_group_name, self.channel_name)
			
			# 메시지 전송
			await self.channel_layer.group_send(
				room_group_name,
				{
					'type': event_type,
					**data
				}
			)

			# 메시지 전송 후 그룹에서 leave
			await self.channel_layer.group_discard(room_group_name, self.channel_name)
		
		except Exception as e:
			logger.error(f"Error sending to room socket: {e}")

	async def send_destroy_event(self, room_id, reason):
		"""
		destroy 이벤트 전송을 위한 통일된 메서드
		
		Args:
			room_id (str): 대상 룸 ID
			reason (str): 파괴 사유
			additional_data (dict, optional): 추가 데이터
		"""
		data = {
			'type': 'destroy',
			'data': reason,
		}
		await self.send_to_room_socket(room_id, 'destroy', data)