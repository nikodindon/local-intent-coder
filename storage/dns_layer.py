"""
DNS layer — optional seed storage via Cloudflare DNS TXT records.

Ported from mnemo. Stores the compressed intent (prompt + model + hash)
as a DNS TXT record. Retrieval reconstructs the artifact on demand.

This module is OPTIONAL. The core agent loop does not depend on it.
To use it, provide Cloudflare credentials in config.json:

    {
        "cloudflare_api_token": "...",
        "cloudflare_zone_id": "...",
        "cloudflare_domain": "yourdomain.example.com"
    }

A seed looks like:
    {
        "prompt": "create a playable Tetris clone...",
        "model": "qwen2.5-coder-7b",
        "functional_hash": "sha256...",
        "artifact_hash": "sha256...",
        "cycle_count": 7
    }

Compressed with zlib + base64, it typically fits in a single TXT record (~300 bytes).
"""

import base64
import json
import zlib

import requests


CHUNK_SIZE = 255  # DNS TXT record max length per string


class DNSLayer:
    def __init__(self, config: dict):
        self.token = config.get("cloudflare_api_token")
        self.zone_id = config.get("cloudflare_zone_id")
        self.domain = config.get("cloudflare_domain")

        if not all([self.token, self.zone_id, self.domain]):
            raise ValueError(
                "DNS layer requires cloudflare_api_token, cloudflare_zone_id, "
                "and cloudflare_domain in config.json"
            )

        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }
        self.api = f"https://api.cloudflare.com/client/v4/zones/{self.zone_id}/dns_records"

    # ─── Compression ──────────────────────────────────────────────────────────

    @staticmethod
    def compress(data: dict) -> str:
        raw = json.dumps(data, separators=(",", ":")).encode()
        compressed = zlib.compress(raw, level=9)
        return base64.b64encode(compressed).decode()

    @staticmethod
    def decompress(encoded: str) -> dict:
        compressed = base64.b64decode(encoded)
        raw = zlib.decompress(compressed)
        return json.loads(raw)

    # ─── DNS operations ───────────────────────────────────────────────────────

    def _list_records(self, name: str) -> list[dict]:
        r = requests.get(self.api, headers=self.headers, params={"name": name})
        r.raise_for_status()
        return r.json().get("result", [])

    def _delete_record(self, record_id: str):
        requests.delete(f"{self.api}/{record_id}", headers=self.headers)

    def _create_record(self, name: str, content: str):
        payload = {"type": "TXT", "name": name, "content": content, "ttl": 300}
        r = requests.post(self.api, headers=self.headers, json=payload)
        r.raise_for_status()

    # ─── Public API ───────────────────────────────────────────────────────────

    def store_seed(self, key: str, seed: dict) -> str:
        """
        Compress and store a seed under `key.self.domain`.
        Clears any existing records for that key first.
        Returns the compressed seed string.
        """
        name = f"{key}.{self.domain}"
        encoded = self.compress(seed)

        # Clear existing records
        for rec in self._list_records(name):
            self._delete_record(rec["id"])

        # Store in chunks if needed (DNS TXT limit: 255 chars per string)
        chunks = [encoded[i:i + CHUNK_SIZE] for i in range(0, len(encoded), CHUNK_SIZE)]
        for i, chunk in enumerate(chunks):
            chunk_name = f"{key}-{i}.{self.domain}" if i > 0 else name
            self._create_record(chunk_name, chunk)

        print(f"  ✅ Seed stored: {name} ({len(encoded)} bytes, {len(chunks)} chunk(s))")
        return encoded

    def retrieve_seed(self, key: str) -> dict | None:
        """
        Retrieve and decompress a seed stored under `key.self.domain`.
        Assembles chunks in order.
        """
        base_name = f"{key}.{self.domain}"
        encoded = ""

        # Chunk 0 (base record)
        records = self._list_records(base_name)
        if not records:
            print(f"  ⚠️  No seed found for: {base_name}")
            return None
        encoded += records[0]["content"]

        # Additional chunks
        i = 1
        while True:
            chunk_name = f"{key}-{i}.{self.domain}"
            records = self._list_records(chunk_name)
            if not records:
                break
            encoded += records[0]["content"]
            i += 1

        try:
            return self.decompress(encoded)
        except Exception as e:
            print(f"  ❌ Decompression error: {e}")
            return None

    def list_seeds(self) -> list[str]:
        """List all TXT records under the configured domain."""
        r = requests.get(
            self.api,
            headers=self.headers,
            params={"type": "TXT", "per_page": 100},
        )
        r.raise_for_status()
        return [rec["name"] for rec in r.json().get("result", [])]
