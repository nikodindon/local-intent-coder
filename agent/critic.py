import os
from core.llm import LLMClient
from core.session import Session
from agent.prompts import CRITIC


class Critic:
    def __init__(self, client: LLMClient, config: dict):
        self.client = client
        self.config = config

    def review(self, session: Session) -> str:
        """Review the project and return blocking issues only."""
        features = "\n".join(f"- {f}" for f in session.file_list)

        # Check for missing files
        missing = [f for f in session.file_list
                  if not os.path.exists(os.path.join(session.output_dir, f))]

        if missing:
            missing_str = "\n".join(f"  - {f}" for f in missing)
            extra = f"\n\nCRITICAL: The following files are missing on disk:\n{missing_str}"
        else:
            extra = "\n\nAll files listed in the spec exist on disk."

        snapshot = session.snapshot()

        # Add critic history to avoid repetition
        history_context = ""
        if session.critic_history:
            history_context = "\n\nPrevious review cycles already covered these issues (do NOT repeat):\n"
            for i, past_review in enumerate(session.critic_history[-2:], 1):  # Only show last 2
                if past_review.strip() and "ALL_COMPLETE" not in past_review.upper():
                    history_context += f"\nCycle {i}:\n{past_review[:300]}"

        user_prompt = (
            f"Project intent: {session.prompt}\n\n"
            f"Required files according to spec:\n{features}\n"
            f"Files present on disk: {', '.join(session.file_list)}\n"
            f"{extra}\n"
            f"{history_context}\n"
            f"Here is the current state of the project:\n{snapshot}\n\n"
            "You are a strict code reviewer.\n"
            "Analyze if the project fulfills the original user intent and is functional.\n"
            "List ONLY the blocking issues that prevent the project from working as intended.\n"
            "Be concrete and specific (mention file + problem).\n"
            "If the project is reasonably complete and works according to the intent, reply with exactly:\n"
            "ALL_COMPLETE"
        )

        messages = [
            {"role": "system", "content": CRITIC},
            {"role": "user", "content": user_prompt},
        ]

        output = self.client.call(messages, label="CRITIC", max_tokens=900)
        session.critic_history.append(output.strip())
        return output.strip()

    @staticmethod
    def is_complete(critic_output: str) -> bool:
        return "ALL_COMPLETE" in critic_output.upper()

    @staticmethod
    def is_repetitive(session: Session, threshold: int = 2) -> bool:
        """Detect if the critic is stuck in a loop."""
        if len(session.critic_history) < threshold + 1:
            return False
        
        # Check if last N reviews are identical
        recent = session.critic_history[-(threshold + 1):]
        return len(set(recent)) == 1 and recent[0].strip() != ""