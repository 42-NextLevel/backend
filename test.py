import requests

request = requests.get('https://localhost:8000/api/auth')

print(request.text)