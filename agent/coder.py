"""
Coder agent — version forcée pour écrire dans le bon dossier
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
    m = re.search(r'<tool>(.*?)</tool>', text, re.DOTALL | re.IGNORECASE)
    if m:
        return _try_parse_json(m.group(1).strip())
    m = re.search(r'<tool>(.*)', text, re.DOTALL | re.IGNORECASE)
    if m:
        return _try_parse_json(m.group(1).strip())
    return None


def write_file(full_path: str, content: str, allowed_files: list) -> bool:
    """FORCE l'écriture au chemin complet"""
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
        """filepath est le chemin COMPLET"""
        context = f"File to write: {filename}\nRole: {session.file_roles.get(filename, '')}\nCurrent snapshot:\n{session.snapshot()}\nWrite complete code now."

        for attempt in range(6):
            if attempt > 0:
                print(f"  🔁 Attempt {attempt}/6")

            messages = [
                {"role": "system", "content": CODER},
                {"role": "user", "content": context}
            ]

            reply = self.client.call(messages, label=f"CODER — {filename}", max_tokens=3000)
            tool = extract_tool_call(reply)

            if tool and tool.get("command") == "write_file":
                # On IGNORE ce que le LLM renvoie comme filename et on force le filepath complet
                return write_file(filepath, tool.get("content", ""), session.file_list)

        print(f"  ❌ Failed to write {filename}")
        return False