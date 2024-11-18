from django.shortcuts import render
from .solidity.scripts import Web3Client  # 상대 경로로 수정
from django.http import JsonResponse

# Create your views here.

def get_contract_info(request, game_id):
	client = Web3Client()
	history = client.get_match_history(game_id)
	fromated_history = format_match_history(history)
	return JsonResponse(fromated_history)
