"""
Agent loop — orchestrates the Coder → Critic → Planner cycle.

Phase 1 (creation): generate any missing files.
Phase 2 (repair):   Critic reviews, Planner plans, Coder fixes — until
                    ALL_COMPLETE or max_cycles is reached.
"""

import os

from core.llm import LLMClient
from core.session import Session
from agent.architect import Architect
from agent.coder import Coder
from agent.critic import Critic
from agent.planner import Planner


def _header(text: str):
    print("\n" + "═" * 66)
    print(f"  {text}")
    print("═" * 66)


def _section(text: str):
    print(f"\n{'─' * 66}\n  {text}\n{'─' * 66}")


class AgentLoop:
    def __init__(self, client: LLMClient, config: dict, session: Session):
        self.client = client
        self.config = config
        self.session = session
        self.coder = Coder(client, config)
        self.critic = Critic(client, config)
        self.planner = Planner(client, config)

    def _populate_session_from_spec(self):
        """Parse the spec and update session.file_list and session.file_roles."""
        parsed = Architect.parse_spec(self.session.spec_md)
        self.session.file_list = parsed["file_list"]
        self.session.file_roles = parsed["file_roles"]

        if not self.session.file_list:
            print("  ⚠️  No files found in spec. Check the Architect output.")
        else:
            print(f"  Files to generate: {', '.join(self.session.file_list)}")

    def _phase_create(self):
        """Generate all files that don't exist yet."""
        missing = self.session.missing_files()
        if not missing:
            print("  All files already exist, skipping creation phase.")
            return

        _header("PHASE 1 — FILE CREATION")
        for fname in self.session.file_list:
            if fname not in missing:
                continue
            filepath = os.path.join(os.path.abspath(self.session.output_dir), fname)
            _section(f"Creating {fname}")
            self.coder.write(fname, filepath, self.session)

    def _phase_repair(self, max_cycles: int) -> bool:
        """
        Run the Critic → Planner → Coder cycle until complete or exhausted.
        Returns True if the Critic confirmed completion.
        """
        _header("PHASE 2 — REPAIR LOOP (Critic → Planner → Coder)")

        for cycle in range(max_cycles):
            _section(f"🔁 Cycle {cycle + 1} / {max_cycles}")
            self.session.cycles_run += 1

            # Critic
            critic_out = self.critic.review(self.session)

            if Critic.is_complete(critic_out):
                print("\n  🎉 Critic says: ALL_COMPLETE")
                self.session.completed = True
                return True

            # Planner
            plan = self.planner.plan(critic_out, self.session)
            if not plan:
                print("  No valid plan produced, stopping.")
                return False

            # Coder — execute each action
            for step in plan:
                filename = os.path.basename(step["filename"])
                filepath = os.path.join(os.path.abspath(self.session.output_dir), filename)
                reason = step.get("reason", "Fix issues found by the Critic.")
                _section(f"Fixing {filename}")
                self.coder.write(filename, filepath, self.session, reason=reason)

        return False

    def run(self, max_cycles: int = 12) -> bool:
        """
        Full run: populate session from spec, create files, repair loop.
        Returns True if the project completed successfully.
        """
        self._populate_session_from_spec()

        self._phase_create()
        success = self._phase_repair(max_cycles)

        return success
