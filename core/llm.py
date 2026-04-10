"""
LLM client — thin wrapper around the OpenAI-compatible API.

Works with:
  - llama.cpp (llama-server)
  - LM Studio
  - Ollama (openai-compat mode)
  - Any OpenAI-compat endpoint

All calls are streaming; the full reply is returned as a string.
"""

from openai import OpenAI


def _sep(label: str = ""):
    print(f"\n{'─' * 66}")
    if label:
        print(f"  {label}")
        print("─" * 66)


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
        self._client = OpenAI(
            base_url=config["base_url"],
            api_key=config["api_key"],
        )

    def call(
        self,
        messages: list[dict],
        label: str = "",
        max_tokens: int | None = None,
    ) -> str:
        """
        Call the LLM with a list of messages.
        Streams the response and returns the full reply as a string.
        """
        max_tokens = max_tokens or self.config["max_out_tokens"]
        context_size = self.config["context_size"]
        temperature = self.config.get("temperature", 0.1)

        _sep(label)
        _print_context_bar(messages, max_tokens, context_size, label)
        print()

        full_reply = ""
        try:
            with self._client.chat.completions.create(
                model=self.config["model"],
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            ) as stream:
                for chunk in stream:
                    delta = chunk.choices[0].delta.content or ""
                    print(delta, end="", flush=True)
                    full_reply += delta
        except Exception as e:
            print(f"\n  ⚠️  LLM error: {e}")

        print("\n")
        return full_reply
