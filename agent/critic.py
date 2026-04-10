import os
from core.llm import LLMClient
from core.session import Session
from agent.prompts import CRITIC


class Critic:
    def __init__(self, client: LLMClient, config: dict):
        self.client = client
        self.config = config

    def review(self, session: Session) -> str:
        """Critic générique qui s'adapte à n'importe quel projet"""
        features = "\n".join(f"- {f}" for f in session.file_list)

        # Vérification fichiers manquants
        missing = [f for f in session.file_list 
                  if not os.path.exists(os.path.join(session.output_dir, f))]
        
        if missing:
            missing_str = "\n".join(f"  - {f}" for f in missing)
            extra = f"\n\nCRITICAL: The following files are missing on disk:\n{missing_str}"
        else:
            extra = "\n\nAll files listed in the spec exist on disk."

        snapshot = session.snapshot()

        user_prompt = (
            f"Project intent: {session.prompt}\n\n"
            f"Required files according to spec:\n{features}\n"
            f"Files present on disk: {', '.join(session.file_list)}\n"
            f"{extra}\n\n"
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