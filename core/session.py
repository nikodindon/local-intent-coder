"""
Session — holds all state for a single Intent Engine run.

Persisted to session.json in the output directory so a run can be
inspected or resumed after the fact.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime


@dataclass
class Session:
    prompt: str
    output_dir: str
    config: dict

    # Set by Architect
    spec_md: str = ""
    file_list: list[str] = field(default_factory=list)
    file_roles: dict[str, str] = field(default_factory=dict)

    # Set by loop
    cycles_run: int = 0
    completed: bool = False
    started_at: str = field(default_factory=lambda: datetime.now().isoformat())
    finished_at: str = ""

    # History of Critic outputs (one per cycle)
    critic_history: list[str] = field(default_factory=list)

    def snapshot(self, limit: int | None = None) -> str:
        """
        Return a text snapshot of all generated files.
        Each file is shown with its content (truncated if limit is set).
        """
        limit = limit or self.config.get("snapshot_limit", 2000)
        parts = []
        for fname in self.file_list:
            path = os.path.join(self.output_dir, fname)
            if os.path.exists(path):
                with open(path, encoding="utf-8") as f:
                    content = f.read()
                if len(content) > limit:
                    content = content[:limit] + f"\n... [truncated at {limit} chars]"
                parts.append(f"=== {fname} ===\n{content}")
            else:
                parts.append(f"=== {fname} === [MISSING]")
        return "\n\n".join(parts)

    def missing_files(self) -> list[str]:
        return [
            f for f in self.file_list
            if not os.path.exists(os.path.join(self.output_dir, f))
        ]

    def save(self):
        path = os.path.join(self.output_dir, "session.json")
        data = asdict(self)
        data.pop("config", None)  # don't store secrets
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"  Session saved: {path}")
