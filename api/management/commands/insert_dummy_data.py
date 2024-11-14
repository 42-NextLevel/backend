# Create a new file named 'management/commands/insert_dummy_data.py' in your app directory

from django.core.management.base import BaseCommand
from contract.models import ContractAddress
from django.db import transaction
from contract.solidity.scripts.Web3Client import Web3Client
from django.core.cache import cache

class Command(BaseCommand):
	help = 'Insert dummy data into the database'

	@transaction.atomic
	def handle(self, *args, **kwargs):
		print("Inserting dummy data into the database")
		# Web3Client 인스턴스 생성
		try:
			web3 = Web3Client()
		except Exception as e:
			print(f"Web3Client initialization failed: {e}")
			return