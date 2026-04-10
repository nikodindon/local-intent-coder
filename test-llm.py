from openai import OpenAI

client = OpenAI(base_url='http://localhost:8090/v1', api_key='sk-test')

print("Testing WITHOUT streaming...")
resp = client.chat.completions.create(
    model='Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf', 
    messages=[{'role': 'user', 'content': 'Say hello in 3 words'}], 
    max_tokens=20, 
    temperature=0.1,
    stream=False
)
print(f"Response: {resp.choices[0].message.content}")
print("✓ Non-streaming works!")

print("\nTesting WITH streaming...")
stream = client.chat.completions.create(
    model='Qwen2.5-Coder-7B-Instruct-Q4_K_M.gguf', 
    messages=[{'role': 'user', 'content': 'Say goodbye in 3 words'}], 
    max_tokens=20, 
    temperature=0.1,
    stream=True
)
full = ""
for chunk in stream:
    delta = chunk.choices[0].delta.content or ""
    print(delta, end="", flush=True)
    full += delta
print(f"\n✓ Streaming works! Got {len(full)} chars")
