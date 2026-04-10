"""
seed.py — CLI for the mnemo integration.

Store a completed artifact's seed in Cloudflare DNS and retrieve it later.
The seed is the compressed intent (prompt + model + hashes) — not the code.

Usage:
    # Store the seed of a completed run
    python seed.py store --key tetris-v1 --session output/tetris/session.json

    # Retrieve a seed and print it
    python seed.py get --key tetris-v1

    # Retrieve a seed and regenerate the artifact
    python seed.py reconstruct --key tetris-v1 --output output/tetris-reconstructed

    # List all seeds stored in DNS
    python seed.py list

Requires in config.json:
    cloudflare_api_token, cloudflare_zone_id, cloudflare_domain
"""

import argparse
import json
import os
import sys

from core.config import load_config
from core.hasher import FunctionalHasher
from storage.dns_layer import DNSLayer


def cmd_store(args, config):
    if not os.path.exists(args.session):
        print(f"  ❌ Session file not found: {args.session}")
        sys.exit(1)

    with open(args.session, encoding="utf-8") as f:
        session_data = json.load(f)

    output_dir = session_data.get("output_dir", "")
    hasher = FunctionalHasher()

    artifact_hash = None
    if os.path.isdir(output_dir):
        artifact_hash = hasher.hash_directory(output_dir)
        print(f"  Artifact hash: {artifact_hash[:16]}…")

    seed = {
        "prompt": session_data.get("prompt", ""),
        "model": config["model"],
        "artifact_hash": artifact_hash,
        "functional_hash": None,  # set this manually after phase 4 experiments
        "cycles_run": session_data.get("cycles_run", 0),
        "file_count": len(session_data.get("file_list", [])),
        "file_list": session_data.get("file_list", []),
        "completed": session_data.get("completed", False),
    }

    dns = DNSLayer(config)
    dns.store_seed(args.key, seed)

    print(f"\n  Seed stored under key: {args.key}")
    print(f"  Prompt : {seed['prompt'][:80]}{'…' if len(seed['prompt']) > 80 else ''}")
    print(f"  Files  : {seed['file_count']}")
    print(f"  Cycles : {seed['cycles_run']}")


def cmd_get(args, config):
    dns = DNSLayer(config)
    seed = dns.retrieve_seed(args.key)
    if seed is None:
        sys.exit(1)
    print(json.dumps(seed, indent=2, ensure_ascii=False))


def cmd_reconstruct(args, config):
    dns = DNSLayer(config)
    seed = dns.retrieve_seed(args.key)
    if seed is None:
        sys.exit(1)

    prompt = seed.get("prompt")
    if not prompt:
        print("  ❌ Seed has no prompt field.")
        sys.exit(1)

    print(f"\n  Reconstructing from seed: {args.key}")
    print(f"  Prompt : {prompt}")
    print(f"  Model  : {seed.get('model', config['model'])}")

    # Delegate to main.py
    os.system(
        f'python main.py "{prompt}" '
        f"--output {args.output} "
        f"--max_cycles {args.max_cycles}"
    )

    # Verify artifact hash if we have one
    expected = seed.get("artifact_hash")
    if expected and os.path.isdir(args.output):
        hasher = FunctionalHasher()
        actual = hasher.hash_directory(args.output)
        if actual == expected:
            print(f"\n  ✅ Artifact hash matches: {actual[:16]}…")
        else:
            print(f"\n  ⚠️  Hash mismatch!")
            print(f"     Expected : {expected[:16]}…")
            print(f"     Got      : {actual[:16]}…")
            print("     (This is expected cross-machine — see README Phase 5)")


def cmd_list(args, config):
    dns = DNSLayer(config)
    keys = dns.list_seeds()
    if not keys:
        print("  No seeds found.")
    else:
        print(f"  {len(keys)} record(s) in DNS:")
        for k in keys:
            print(f"    {k}")


def main():
    parser = argparse.ArgumentParser(
        description="Intent Engine — seed storage via Cloudflare DNS (mnemo integration)"
    )
    parser.add_argument("--config", default="config.json")
    sub = parser.add_subparsers(dest="command", required=True)

    # store
    p_store = sub.add_parser("store", help="Store a session's seed in DNS")
    p_store.add_argument("--key", required=True, help="DNS key (e.g. tetris-v1)")
    p_store.add_argument("--session", required=True, help="Path to session.json")

    # get
    p_get = sub.add_parser("get", help="Print a seed stored in DNS")
    p_get.add_argument("--key", required=True)

    # reconstruct
    p_rec = sub.add_parser("reconstruct", help="Retrieve seed and regenerate the artifact")
    p_rec.add_argument("--key", required=True)
    p_rec.add_argument("--output", required=True, help="Output directory for reconstruction")
    p_rec.add_argument("--max_cycles", type=int, default=12)

    # list
    sub.add_parser("list", help="List all seeds in DNS")

    args = parser.parse_args()
    config = load_config(args.config)

    dispatch = {
        "store": cmd_store,
        "get": cmd_get,
        "reconstruct": cmd_reconstruct,
        "list": cmd_list,
    }
    dispatch[args.command](args, config)


if __name__ == "__main__":
    main()
