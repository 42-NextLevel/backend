from django.shortcuts import render
from solidity.scripts import Web3Client
from solidity.scripts import compile
from django.http import JsonResponse

# Create your views here.

def get_contract_info(request, game_id):
	history = Web3Client.get_match_history(game_id)
	fromated_history = format_match_history(history)
	return JsonResponse(fromated_history)
