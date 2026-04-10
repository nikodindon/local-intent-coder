import argparse
import os
import re

from core.config import load_config
from core.llm import LLMClient
from core.session import Session
from agent.architect import Architect
from agent.loop import AgentLoop


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt", type=str)
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--max_cycles", type=int, default=3)
    args = parser.parse_args()

    config = load_config("config.json")
    output_dir = args.output or os.path.join("output", re.sub(r"[^\w\s-]", "", args.prompt.lower()).replace(" ", "-")[:60])
    os.makedirs(output_dir, exist_ok=True)

    print(f"Output directory: {os.path.abspath(output_dir)}\n")

    client = LLMClient(config)
    session = Session(prompt=args.prompt, output_dir=output_dir, config=config)

    architect = Architect(client, config)
    spec_md = architect.build_spec(args.prompt, output_dir)
    session.spec_md = spec_md

    with open(os.path.join(output_dir, "spec.md"), "w", encoding="utf-8") as f:
        f.write(spec_md)

    session.file_list = ["index.html", "styles.css", "tetris.js"]
    session.file_roles = {"index.html": "HTML", "styles.css": "CSS", "tetris.js": "Game logic"}

    loop = AgentLoop(client, config, session)

    print("Creating files in correct folder...\n")
    for fname in session.file_list:
        full_path = os.path.join(output_dir, fname)
        print(f"→ {fname}")
        loop.coder.write(fname, full_path, session)

    print("\nStarting repair loop...\n")
    loop._phase_repair(max_cycles=args.max_cycles)

    index_path = os.path.join(output_dir, "index.html")
    print("\n" + "="*60)
    if os.path.exists(index_path):
        print(f"✅ Success! Open: {os.path.abspath(index_path)}")
    else:
        print("Files still not in output folder.")
    print("="*60)


if __name__ == "__main__":
    main()