import argparse
import os
import re
import sys
import io

from core.config import load_config
from core.llm import LLMClient
from core.session import Session
from agent.architect import Architect
from agent.designer import Designer
from agent.loop import AgentLoop


class TeeOutput:
    """Write to both stdout and a log file."""
    def __init__(self, filepath):
        self.file = open(filepath, 'w', encoding='utf-8', errors='replace')
        self.stdout = sys.stdout
    
    def write(self, text):
        self.stdout.write(text)
        self.file.write(text)
        self.file.flush()
    
    def flush(self):
        self.stdout.flush()
        self.file.flush()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt", type=str)
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--max_cycles", type=int, default=12)
    parser.add_argument("--log", type=str, default=None,
                        help="Log file path (tail with: Get-Content -Wait <path>)")
    parser.add_argument("--no-timeout", action="store_true",
                        help="Disable shell timeout (use with --no-timeout for long runs)")
    args = parser.parse_args()
    
    # Setup log file if requested
    if args.log:
        os.makedirs(os.path.dirname(os.path.abspath(args.log)), exist_ok=True)
        sys.stdout = TeeOutput(args.log)
        print(f"📝 Logging to: {args.log}")
        print(f"💡 Tail in PowerShell: Get-Content -Wait {args.log}")
        print()

    if args.no_timeout and sys.platform == "win32":
        # Re-launch with an infinite shell timeout on Windows
        import ctypes
        ctypes.windll.kernel32.SetConsoleTitleW("Intent Engine (no timeout)")
        # Re-run ourselves; the caller is expected to use no timeout on the relaunch
        print("  ⏳ Running without timeout — this may take a while.\n")

    config = load_config("config.json")
    output_dir = args.output or os.path.join("output", re.sub(r"[^\w\s-]", "", args.prompt.lower()).replace(" ", "-")[:60])
    os.makedirs(output_dir, exist_ok=True)

    print(f"Output directory: {os.path.abspath(output_dir)}\n")

    client = LLMClient(config)
    session = Session(prompt=args.prompt, output_dir=output_dir, config=config)

    architect = Architect(client, config)
    spec_md = architect.build_spec(args.prompt, output_dir)

    # Phase 0: Designer enriches spec with visual guidelines
    designer_pre = Designer(client, config)
    spec_md = designer_pre.enrich_spec(spec_md)

    session.spec_md = spec_md

    with open(os.path.join(output_dir, "spec.md"), "w", encoding="utf-8") as f:
        f.write(spec_md)

    # Parse spec to get file list and roles
    parsed = Architect.parse_spec(spec_md)
    session.file_list = parsed["file_list"]
    session.file_roles = parsed["file_roles"]

    if not session.file_list:
        print("  ⚠️  No files found in spec. Check the Architect output.")
        return

    print(f"  Files from spec: {', '.join(session.file_list)}\n")

    loop = AgentLoop(client, config, session)

    try:
        completed = loop.run(max_cycles=args.max_cycles)
        session.completed = completed
    except Exception as e:
        print(f"\n⚠️  Error during pipeline execution: {e}")
        session.completed = False
    finally:
        # Always save session state, even if an error occurred
        session.save()

    # Check for any generated artifact (not just index.html)
    artifact_files = [f for f in session.file_list if os.path.exists(os.path.join(output_dir, f))]
    print("\n" + "="*60)
    if completed or artifact_files:
        primary = next((f for f in artifact_files if f.endswith((".html", ".py"))), artifact_files[0] if artifact_files else None)
        if primary:
            print(f"✅ Success! Files generated. Open: {os.path.join(os.path.abspath(output_dir), primary)}")
        else:
            print(f"✅ Success! {len(artifact_files)} file(s) generated in {os.path.abspath(output_dir)}")
        
        # Print metrics
        metrics = session.metrics()
        print(f"\n📊 Metrics:")
        print(f"   Files generated: {metrics['files_generated']}/{len(session.file_list)}")
        print(f"   Total artifact size: {metrics['total_artifact_size_bytes']:,} bytes")
        print(f"   Cycles run: {metrics['cycles_run']}")
        print(f"   Completed: {metrics['completed']}")
    else:
        print("❌ Project did not complete within the cycle limit.")
        metrics = session.metrics()
        print(f"\n📊 Metrics:")
        print(f"   Files generated: {metrics['files_generated']}/{len(session.file_list)}")
        print(f"   Cycles run: {metrics['cycles_run']}")
    print("="*60)


if __name__ == "__main__":
    main()