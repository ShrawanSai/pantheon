import requests
import json

url = "http://127.0.0.1:8030/api/v1/sessions/a2c6ae79-73bc-4f19-b71e-7ab70b905105/turns/stream"
headers = {"Authorization": "Bearer dev-override"}
payload = {"message": "I want all CEOs to review each others critiques in managing style. and then present all results to me"}

with requests.post(url, headers=headers, json=payload, stream=True) as r:
    for line in r.iter_lines():
        if line:
            print(line.decode('utf-8'))
