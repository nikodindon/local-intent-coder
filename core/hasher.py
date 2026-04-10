"""
Functional hasher — hashes the *execution output* of generated code,
not the source text.

This is the key insight from the mnemo research:
  - Source-level SHA256 breaks cross-machine (GPU vs CPU float16 divergence)
  - Execution output SHA256 is hardware-independent for deterministic code

For browser artifacts (HTML/JS), execution hashing is not yet implemented.
For Python artifacts, we run the entry point in a subprocess and hash stdout.
"""

import hashlib
import subprocess
import sys
import os


class FunctionalHasher:
    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    def hash_file(self, path: str) -> str:
        """SHA256 of raw file contents (source-level hash)."""
        with open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    def hash_directory(self, directory: str, extensions: list[str] | None = None) -> str:
        """
        SHA256 of all files in a directory (sorted, concatenated).
        Used as a stable fingerprint for the full artifact.
        """
        extensions = extensions or [".html", ".js", ".css", ".py"]
        h = hashlib.sha256()
        for root, _, files in sorted(os.walk(directory)):
            for fname in sorted(files):
                if any(fname.endswith(ext) for ext in extensions):
                    path = os.path.join(root, fname)
                    h.update(fname.encode())
                    with open(path, "rb") as f:
                        h.update(f.read())
        return h.hexdigest()

    def hash_execution(self, script_path: str, args: list[str] | None = None) -> str | None:
        """
        Run a Python script in a subprocess and hash its stdout.
        Returns None if execution fails or times out.

        This is the cross-machine stable hash: two machines producing
        different source code that prints the same output will agree.
        """
        cmd = [sys.executable, script_path] + (args or [])
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            if result.returncode != 0:
                print(f"  ⚠️  Execution failed: {result.stderr[:200]}")
                return None
            return hashlib.sha256(result.stdout.encode()).hexdigest()
        except subprocess.TimeoutExpired:
            print(f"  ⚠️  Execution timed out after {self.timeout}s")
            return None
        except Exception as e:
            print(f"  ⚠️  Execution error: {e}")
            return None

    def verify(self, script_path: str, expected_hash: str, runs: int = 2) -> bool:
        """
        Run the script `runs` times and check that all outputs match
        the expected hash. This guards against non-deterministic code
        (e.g. scripts that call random() or datetime.now()).
        """
        hashes = set()
        for i in range(runs):
            h = self.hash_execution(script_path)
            if h is None:
                return False
            hashes.add(h)
        if len(hashes) > 1:
            print(f"  ⚠️  Non-deterministic output across {runs} runs")
            return False
        return list(hashes)[0] == expected_hash
