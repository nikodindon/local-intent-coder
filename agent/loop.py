"""
Agent loop — orchestrates the Coder → Critic → Executor → Planner cycle.

Phase 0 (design):    Designer adds visual guidelines to the spec.
Phase 1 (creation):  generate any missing files.
Phase 2 (repair):    Critic reviews, Planner plans, Coder fixes — until
                     ALL_COMPLETE or max_cycles is reached.
Phase 3 (execution): Executor runs tests, catches runtime bugs Critic misses.
Phase 4 (visual):    Designer audits rendered styles, triggers CSS fix loop.
"""

import os
import time
from datetime import datetime

from core.llm import LLMClient
from core.session import Session
from core.executor import Executor
from agent.architect import Architect
from agent.coder import Coder
from agent.critic import Critic
from agent.planner import Planner
from agent.designer import Designer


def _timestamp():
    """Return current time as HH:MM:SS."""
    return datetime.now().strftime("%H:%M:%S")


def _header(text: str):
    sep = "═" * 66
    print(f"\n{sep}")
    print(f"  {text}  [{_timestamp()}]")
    print(sep)


def _section(text: str):
    sep = "─" * 66
    print(f"\n{sep}\n  {text}  [{_timestamp()}]\n{sep}")


class AgentLoop:
    def __init__(self, client: LLMClient, config: dict, session: Session):
        self.client = client
        self.config = config
        self.session = session
        self.coder = Coder(client, config)
        self.critic = Critic(client, config)
        self.planner = Planner(client, config)
        self.executor = Executor(session.output_dir, verbose=True)
        self.designer = Designer(client, config)

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
        phase_start = time.time()
        for fname in self.session.file_list:
            if fname not in missing:
                continue
            file_start = time.time()
            filepath = os.path.join(os.path.abspath(self.session.output_dir), fname)
            _section(f"Creating {fname}")
            self.coder.write(fname, filepath, self.session)
            elapsed = time.time() - file_start
            print(f"\n  ⏱️  {fname} generated in {elapsed:.1f}s")
            # Save session after each file in case of crash
            self.session.save()
        phase_elapsed = time.time() - phase_start
        print(f"\n  ⏱️  Phase 1 complete in {phase_elapsed:.1f}s")

    def _phase_repair(self, max_cycles: int, max_visual_cycles: int = 3) -> bool:
        """
        Run the Critic → Planner → Coder cycle until complete or exhausted.
        Then Phase 3: Executor tests. Then Phase 4: Designer visual audit.
        Returns True if all phases confirmed completion.
        """
        _header("PHASE 2 — REPAIR LOOP (Critic → Planner → Coder)")
        phase_start = time.time()

        for cycle in range(max_cycles):
            cycle_start = time.time()
            _section(f"🔁 Cycle {cycle + 1} / {max_cycles}")
            self.session.cycles_run += 1

            # Critic
            critic_start = time.time()
            critic_out = self.critic.review(self.session)
            critic_time = time.time() - critic_start
            print(f"\n  ⏱️  Critic review: {critic_time:.1f}s")

            if Critic.is_complete(critic_out):
                print("\n  🎉 Critic says: ALL_COMPLETE")

                # Phase 3: Execute and test
                _header("PHASE 3 — EXECUTION TESTS")
                test_start = time.time()
                test_report = self.executor.run_tests(self.session.spec_md)
                test_time = time.time() - test_start
                print(f"\n  ⏱️  Executor tests: {test_time:.1f}s")

                if not test_report.passed:
                    # Tests failed - feed back to Planner
                    print(f"\n  ❌ {len(test_report.failures)} execution test(s) failed")
                    failures = test_report.failure_reasons()

                    # Create a fix plan from failures via Planner
                    critic_failure_report = "Execution test failures:\n" + "\n".join(f"- {f}" for f in failures[:3])
                    plan = self.planner.plan(critic_failure_report, self.session)

                    if plan:
                        for step in plan:
                            filename = os.path.basename(step["filename"])
                            filepath = os.path.join(os.path.abspath(self.session.output_dir), filename)
                            reason = step.get("reason", "Fix execution test failures")
                            _section(f"Fixing {filename}")
                            self.coder.write(filename, filepath, self.session, reason=reason)
                    else:
                        print("  ⚠️  No valid plan produced, stopping.")
                        return False

                    continue  # back to Critic for another cycle

                # Phase 3 passed — now Phase 4: Visual audit
                _header("PHASE 4 — VISUAL DESIGN AUDIT")
                visual_start = time.time()
                visual_result = self.designer.audit_styles(self.session.spec_md, self.session.output_dir)
                visual_time = time.time() - visual_start
                print(f"\n  ⏱️  Designer audit: {visual_time:.1f}s")

                if visual_result["passed"]:
                    print(f"\n  🎨 Designer scores: {visual_result['score']}/10 — VISUALLY_COMPLETE")
                    self.session.completed = True
                    return True
                else:
                    print(f"\n  🎨 Designer scores: {visual_result['score']}/10 — NEEDS VISUAL FIXES")
                    if visual_result["issues"]:
                        print("  Issues:")
                        for issue in visual_result["issues"]:
                            print(f"    - {issue}")

                    # Feed visual issues to Planner for CSS fix
                    visual_report = "Visual design issues:\n" + "\n".join(f"- {i}" for i in visual_result["issues"][:3])
                    plan = self.planner.plan(visual_report, self.session)

                    if plan and max_visual_cycles > 0:
                        for step in plan:
                            filename = os.path.basename(step["filename"])
                            filepath = os.path.join(os.path.abspath(self.session.output_dir), filename)
                            reason = step.get("reason", "Fix visual design issues")
                            _section(f"Fixing {filename}")
                            self.coder.write(filename, filepath, self.session, reason=reason)

                        # Recurse with one fewer visual cycle remaining
                        return self._phase_repair(max_cycles, max_visual_cycles - 1)
                    else:
                        print("  ⚠️  No valid plan or visual cycle limit reached, stopping.")
                        self.session.completed = True  # functional at least
                        return True

            # Check if Critic is stuck in a loop
            if Critic.is_repetitive(self.session):
                print("\n  ⚠️  Critic is repeating itself, stopping loop")
                print("  📝 Manual review recommended")
                self.session.completed = False
                return False

            # Planner
            planner_start = time.time()
            plan = self.planner.plan(critic_out, self.session)
            planner_time = time.time() - planner_start
            print(f"\n  ⏱️  Planner: {planner_time:.1f}s")

            if not plan:
                print("  No valid plan produced, stopping.")
                return False

            # Coder — execute each action
            for step in plan:
                file_start = time.time()
                filename = os.path.basename(step["filename"])
                filepath = os.path.join(os.path.abspath(self.session.output_dir), filename)
                reason = step.get("reason", "Fix issues found by the Critic.")
                _section(f"Fixing {filename}")
                self.coder.write(filename, filepath, self.session, reason=reason)
                file_time = time.time() - file_start
                print(f"\n  ⏱️  {filename} fixed in {file_time:.1f}s")

            cycle_time = time.time() - cycle_start
            print(f"\n  ⏱️  Cycle {cycle + 1} complete in {cycle_time:.1f}s")
            # Save session after each cycle
            self.session.save()

        phase_elapsed = time.time() - phase_start
        print(f"\n  ⏱️  Phase 2 complete in {phase_elapsed:.1f}s")
        return False

    def run(self, max_cycles: int = 12) -> bool:
        """
        Full run: populate session from spec, create files, repair loop.
        Returns True if the project completed successfully.
        """
        _header("INTENT ENGINE — STARTING PIPELINE")
        print(f"\n  Prompt: {self.session.prompt}")
        print(f"  Output: {os.path.abspath(self.session.output_dir)}")
        
        self._populate_session_from_spec()

        self._phase_create()
        success = self._phase_repair(max_cycles)
        
        if success:
            _header("✅ PIPELINE COMPLETE")
        else:
            _header("⚠️  PIPELINE DID NOT COMPLETE")
            print(f"  Cycles run: {self.session.cycles_run}")
            print(f"  Files generated: {len(self.session.file_list) - len(self.session.missing_files())}/{len(self.session.file_list)}")

        return success
