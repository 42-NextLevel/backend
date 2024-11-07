from django.apps import AppConfig

class ContractConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'contract'

    def compile_and_deploy(self):
        try:
            # Web3 설정
            w3 = Web3(Web3.HTTPProvider(settings.WEB3_PROVIDER_URL))
            account = Account.from_key(settings.ETHEREUM_PRIVATE_KEY)

            # 컨트랙트 JSON 로드 (컴파일된 파일)
            contract_path = Path(settings.BASE_DIR) / 'contract' / 'solidity' / 'builds' / 'MyContract_deploy.json'
            with open(contract_path) as f:
                contract_json = json.load(f)

            # 컨트랙트 객체 생성
            Contract = w3.eth.contract(
                abi=contract_json['abi'],
                bytecode=contract_json['bytecode']
            )

            # 트랜잭션 준비
            nonce = w3.eth.get_transaction_count(account.address)
            gas_price = w3.eth.gas_price

            # 컨트랙트 배포 트랜잭션 생성
            transaction = Contract.constructor().build_transaction({
                'from': account.address,
                'nonce': nonce,
                'gas': 2000000,  # 적절한 가스 한도 설정
                'gasPrice': gas_price
            })

            # 트랜잭션 서명
            signed_txn = w3.eth.account.sign_transaction(
                transaction, settings.ETHEREUM_PRIVATE_KEY
            )

            # 트랜잭션 전송
            tx_hash = w3.eth.send_raw_transaction(signed_txn.rawTransaction)
            print(f"Transaction sent: {tx_hash.hex()}")

            # 트랜잭션 완료 대기
            tx_receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
            contract_address = tx_receipt.contractAddress
            
            return contract_address

        except Exception as e:
            print(f"Error during contract deployment: {e}")
            return None

    def ready(self):
        if os.environ.get('RUN_MAIN') != 'true':
            return

        print("Server started. Checking Contract address.")
        
        try:
            # 모델 임포트는 ready() 메서드 안에서 해야 함
            from .models import ContractAddress
            
            contract_address = ContractAddress.objects.first()
            
            if not contract_address:
                print("No contract address found in database.")
                
                # 컨트랙트 컴파일 및 배포
                deployed_address = self.compile_and_deploy()
                
                if deployed_address:
                    # 배포된 주소를 DB에 저장
                    ContractAddress.objects.create(
                        address=deployed_address,
                        status='ACTIVE'
                    )
                    print(f"Contract deployed and saved: {deployed_address}")
                else:
                    print("Failed to deploy contract")
            else:
                print(f"Contract address found: {contract_address.address}")
                
        except DatabaseError as e:
            print(f"Database error: {e}")
        except Exception as e:
            print(f"Unexpected error: {e}")