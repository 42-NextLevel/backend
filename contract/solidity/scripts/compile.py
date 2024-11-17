import json
import os
import sys
from solcx import compile_standard, install_solc
from pathlib import Path

def compile_contracts():
	try:
		install_solc("0.8.24")
		
		# 소스 디렉토리와 빌드 디렉토리 경로
		current_dir = Path(__file__).parent.parent
		sources_dir = current_dir / "sources"
		builds_dir = current_dir / "builds"
		
		# 소스 디렉토리가 존재하는지 확인
		if not sources_dir.exists():
			raise FileNotFoundError(f"Sources directory not found: {sources_dir}")
			
		# 빌드 디렉토리가 없으면 생성
		builds_dir.mkdir(exist_ok=True)
		
		compiler_settings = {
			"optimizer": {
				"enabled": True,
				"runs": 200
			},
			"outputSelection": {
				"*": {
					"": ["ast"],
					"*": [
						"abi",
						"metadata",
						"devdoc",
						"userdoc",
						"storageLayout",
						"evm.legacyAssembly",
						"evm.bytecode",
						"evm.deployedBytecode",
						"evm.methodIdentifiers",
						"evm.gasEstimates",
						"evm.assembly"
					]
				}
			}
		}

		# 컴파일된 파일 수를 추적
		compiled_count = 0

		# 각 .sol 파일에 대해 컴파일 수행
		for sol_file in sources_dir.glob("*.sol"):
			try:
				with open(sol_file, "r", encoding='utf-8') as file:
					source = file.read()
				
				# 컴파일 설정
				compiled_sol = compile_standard(
					{
						"language": "Solidity",
						"sources": {
							sol_file.name: {
								"content": source
							}
						},
						"settings": compiler_settings
					},
					solc_version="0.8.26"
				)

				# 컴파일 결과 저장
				contract_name = sol_file.stem
				build_file = builds_dir / f"{contract_name}.json"
				
				# 필요한 정보만 추출하여 저장
				contract_data = compiled_sol['contracts'][sol_file.name][contract_name]
				output = {
					'abi': contract_data['abi'],
					'bytecode': contract_data['evm']['bytecode']['object']
				}
				
				with open(build_file, 'w', encoding='utf-8') as f:
					json.dump(output, f, indent=2)
				
				print(f"Compiled {contract_name} -> {build_file}", file=sys.stderr)
				compiled_count += 1
				
			except Exception as e:
				print(f"Error compiling {sol_file.name}: {str(e)}", file=sys.stderr)
				continue

		if compiled_count == 0:
			print("No Solidity files found to compile.", file=sys.stderr)
		else:
			print(f"\nSuccessfully compiled {compiled_count} contracts.", file=sys.stderr)
			
	except Exception as e:
		print(f"Compilation failed: {str(e)}", file=sys.stderr)
		sys.exit(1)

if __name__ == "__main__":
	compile_contracts()