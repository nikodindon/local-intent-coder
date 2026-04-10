"""
LLM client — uses raw HTTP requests to avoid openai library hanging issues.

Works with:
  - llama.cpp (llama-server)
  - LM Studio
  - Ollama (openai-compat mode)
  - Any OpenAI-compat endpoint

All calls are streaming; the full reply is returned as a string.
"""

import json
import sys
import http.client
from urllib.parse import urlparse

# Ensure stdout can handle UTF-8 box-drawing characters even when redirected
if sys.stdout.encoding and sys.stdout.encoding.lower() in ("cp1252", "cp850", "cp437"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def _safe_char(char: str) -> str:
    """Ensure a character can be printed on the current stdout."""
    try:
        sys.stdout.write(char)
        return char
    except UnicodeEncodeError:
        return "-"


def _sep(label: str = ""):
    sep_line = "─" * 66
    print(f"\n{sep_line}")
    if label:
        print(f"  {label}")
        print(sep_line)


def _est_tokens(text: str) -> int:
    """Rough token estimate: 1 token ≈ 4 characters."""
    return max(1, len(str(text)) // 4)


def _messages_tokens(messages: list[dict]) -> int:
    return sum(_est_tokens(m.get("content", "")) for m in messages)


def _print_context_bar(messages: list[dict], max_out: int, context_size: int, label: str = ""):
    inp = _messages_tokens(messages)
    total = inp + max_out
    pct = total / context_size * 100
    bar_w = 30
    filled = int(bar_w * total / context_size)
    bar = "█" * filled + "░" * (bar_w - filled)
    icon = "⚠️ " if pct > 80 else ("🔶 " if pct > 60 else "✅ ")
    print(f"\n  {icon}Context [{bar}] {pct:.1f}%")
    print(f"     Input ~{inp} tok | +{max_out} out | = ~{total}/{context_size} [{label}]")


class LLMClient:
    def __init__(self, config: dict):
        self.config = config
        # Parse the base_url
        parsed = urlparse(config["base_url"])
        self._host = parsed.hostname or "localhost"
        self._port = parsed.port or (443 if parsed.scheme == "https" else 80)
        self._path = parsed.path or "/v1"
        self._is_https = (parsed.scheme == "https")

    def call(
        self,
        messages: list[dict],
        label: str = "",
        max_tokens: int | None = None,
    ) -> str:
        """
        Call the LLM with a list of messages.
        Uses streaming via Server-Sent Events and returns the full reply.
        """
        max_tokens = max_tokens or self.config["max_out_tokens"]
        context_size = self.config["context_size"]
        temperature = self.config.get("temperature", 0.1)

        _sep(label)
        _print_context_bar(messages, max_tokens, context_size, label)
        print()

        # Build request
        payload = {
            "model": self.config["model"],
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": True,
        }
        
        full_reply = ""
        try:
            conn = http.client.HTTPConnection(self._host, self._port, timeout=120)
            conn.request(
                "POST",
                f"{self._path}/chat/completions",
                body=json.dumps(payload),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.config['api_key']}",
                }
            )
            response = conn.getresponse()
            
            if response.status != 200:
                print(f"\n  ⚠️  HTTP {response.status}: {response.read().decode()[:200]}")
                return ""
            
            # Parse SSE stream
            for line in response:
                line = line.decode('utf-8').strip()
                if not line.startswith("data: "):
                    continue
                data_str = line[6:]
                if data_str == "[DONE]":
                    break
                try:
                    data = json.loads(data_str)
                    delta = data.get("choices", [{}])[0].get("delta", {}).get("content", "")
                    if delta:
                        print(delta, end="", flush=True)
                        full_reply += delta
                except json.JSONDecodeError:
                    continue
            
            conn.close()
        except Exception as e:
            print(f"\n  ⚠️  LLM error: {e}")

        print("\n")
        return full_reply
