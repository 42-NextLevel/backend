from django.shortcuts import render
from contract.solidity.scripts.Web3Client import Web3Client
from django.http import JsonResponse
from datetime import datetime

# Create your views here.

def get_contract_info(request, game_id):
	try:
		client = Web3Client()
		history = client.get_match_history(game_id)
		
		# 1970년도는 기본값이므로 아직 데이터가 없는 상태로 간주
		if history['startTime'] == 0 or history['startTime'] == '1970-01-01 09:00:00':
			return JsonResponse({
				'status': 'pending',
				'message': 'This game not started yet or transaction is now pending'
			}, status=202)
			
		# 유저 주소가 비어있는 경우
		if not history['user1'] or not history['user2']:
			return JsonResponse({
				'status': 'invalid',
				'message': 'fatal'
			}, status=400)
			
		# 정상적인 데이터인 경우
		if history['startTime']:  # Unix timestamp인 경우
			history['startTime'] = datetime.fromtimestamp(history['startTime']).strftime('%Y-%m-%d %H:%M:%S')
			history['status'] = 'OK'
		return JsonResponse(history)
	except Exception as e:
		return JsonResponse({
			'status': 'error',
			'message': f'error found: {str(e)}'
		}, status=500)