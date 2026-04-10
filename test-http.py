import http.client
import json

# Test 1: Raw HTTP
print("Test 1: Raw HTTP POST to /v1/chat/completions")
conn = http.client.HTTPConnection("localhost", 8090, timeout=30)
payload = json.dumps({
    "model": "Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf",
    "messages": [{"role": "user", "content": "Say hi"}],
    "max_tokens": 10,
    "temperature": 0.1,
    "stream": False
})
headers = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer sk-test'
}
conn.request("POST", "/v1/chat/completions", payload, headers)
response = conn.getresponse()
print(f"Status: {response.status}")
data = json.loads(response.read().decode())
print(f"Response: {data['choices'][0]['message']['content']}")
conn.close()
print("✓ HTTP works!")

# Test 2: OpenAI library with timeout
print("\nTest 2: OpenAI library with timeout")
from openai import OpenAI
client = OpenAI(
    base_url='http://localhost:8090/v1', 
    api_key='sk-test',
    timeout=30.0
)
resp = client.chat.completions.create(
    model='Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf', 
    messages=[{'role': 'user', 'content': 'Say bye'}], 
    max_tokens=10, 
    temperature=0.1,
    stream=False
)
print(f"Response: {resp.choices[0].message.content}")
print("✓ OpenAI library works!")
