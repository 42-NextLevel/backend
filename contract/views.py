from django.shortcuts import render
from contract.solidity.scripts.Web3Client import Web3Client
from django.http import JsonResponse

# Create your views here.

def get_contract_info(request, game_id):
	client = Web3Client()
	history = client.get_match_history(game_id)
	history['startTime'] = history['startTime'].strftime('%Y-%m-%d %H:%M:%S')
	
	return JsonResponse(history)
