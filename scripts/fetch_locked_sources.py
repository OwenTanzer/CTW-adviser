"""Fetch exactly the locked source files for a reproducible inspection build."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.parse import quote
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]


def main():
    destination = Path(sys.argv[1]).resolve()
    lock = json.loads((ROOT / 'source_lock.json').read_text(encoding='utf-8'))
    repository = lock['source_repository'].removeprefix('https://github.com/').rstrip('/')
    base = f"https://raw.githubusercontent.com/{repository}/{lock['source_commit']}/"

    def fetch(entry):
        target = (destination / entry['path']).resolve()
        if not target.is_relative_to(destination):
            raise ValueError(f"Unsafe source path: {entry['path']}")
        for attempt in range(4):
            try:
                with urlopen(base + quote(entry['path'], safe='/'), timeout=90) as response:
                    data = response.read()
                if len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
                    raise ValueError(f"Locked source mismatch: {entry['path']}")
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                return
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(fetch, lock['files']))
    print(f"Fetched and verified {len(lock['files'])} files at {lock['source_commit']}")


if __name__ == '__main__':
    main()
