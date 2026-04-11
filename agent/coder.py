"""
Coder agent — generates files using the LLM.
"""

import json
import os
import re

from core.llm import LLMClient
from core.session import Session
from agent.prompts import CODER


def _try_parse_json(fragment: str) -> dict | None:
    attempts = [fragment, fragment + '"}', fragment + '"}}', re.sub(r'\}+\s*$', '}', fragment.strip())]
    for a in attempts:
        try:
            return json.loads(a)
        except:
            pass
    return None


def extract_tool_call(text: str) -> dict | None:
    # Case 1: properly closed <tool>...</tool>
    m = re.search(r'<tool>(.*?)</tool>', text, re.DOTALL | re.IGNORECASE)
    if m:
        return _try_parse_json(m.group(1).strip())
    # Case 2: model writes <tool>...<tool> (no slash) — match between first <tool> and second <tool>
    m = re.search(r'<tool>(.*?)(?=<tool\b)', text, re.DOTALL | re.IGNORECASE)
    if m:
        return _try_parse_json(m.group(1).strip())
    # Case 3: model writes <tool>... with no closing tag — grab everything after first <tool>
    m = re.search(r'<tool>(.*)', text, re.DOTALL | re.IGNORECASE)
    if m:
        return _try_parse_json(m.group(1).strip())
    return None


def write_file(full_path: str, content: str, allowed_files: list) -> bool:
    """Write content to the specified path."""
    try:
        os.makedirs(os.path.dirname(os.path.abspath(full_path)), exist_ok=True)
        real = content.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"')
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(real)
        print(f"  ✅ Written to: {full_path} ({len(real):,} chars)")
        return True
    except Exception as e:
        print(f"  ❌ Write error: {e}")
        return False


class Coder:
    def __init__(self, client: LLMClient, config: dict):
        self.client = client
        self.config = config

    def write(self, filename: str, filepath: str, session: Session, reason: str = "") -> bool:
        """Write a file using the LLM. filepath is the full path."""
        context_parts = [
            f"File to write: {filename}",
            f"Role: {session.file_roles.get(filename, '')}",
        ]
        
        # Add spec features for context
        if session.spec_md:
            import re
            features = re.search(r'## Features\n(.*?)(?=##|$)', session.spec_md, re.DOTALL)
            if features:
                context_parts.insert(1, f"SPEC FEATURES:\n{features.group(1).strip()}")
        
        if reason:
            context_parts.insert(1, f"⚠️  THIS IS A REPAIR — YOU MUST FIX: {reason}")
            context_parts.append("CRITICAL: Read the current snapshot below and add the missing functionality. Do NOT repeat the same code.")
            context_parts.append("IMPORTANT: Implement the EXACT features from the spec above. Do NOT implement a different game or app.")
        
        context_parts.append(f"Current snapshot:\n{session.snapshot()}")
        context_parts.append("Write complete code now.")
        
        context = "\n\n".join(context_parts)

        for attempt in range(6):
            if attempt > 0:
                print(f"  🔁 Attempt {attempt}/6")

            messages = [
                {"role": "system", "content": CODER},
                {"role": "user", "content": context}
            ]

            reply = self.client.call(messages, label=f"CODER — {filename}", max_tokens=self.config.get("max_out_tokens", 3000))
            tool = extract_tool_call(reply)

            if tool and tool.get("command") == "write_file":
                # Ignore the filename from LLM and force the correct filepath
                return write_file(filepath, tool.get("content", ""), session.file_list)

        print(f"  ❌ Failed to write {filename}")
        return False