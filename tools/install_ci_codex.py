"""Install an official, hash-verified pinned CLI into a disposable hosted CI dir.

Only the explicit conformance CI job calls this networked helper. Local product
and harness unit tests do not need Codex, credentials, network, or installation.
"""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile
from urllib.request import Request, urlopen

TAG = "rust-v0.153.4"
ASSETS = ("codex-x86_64-unknown-linux-musl.tar.gz",)


def fetch(url):
    with urlopen(Request(url, headers={"User-Agent": "PlanAnvil-CI-conformance"}), timeout=120) as response:
        return response.read()


def main():
    target = Path(sys.argv[1]).resolve()
    target.mkdir(parents=True, exist_ok=True)
    release = json.loads(fetch("https://api.github.com/repos/openai/codex/releases/tags/" + TAG))
    if release["tag_name"] != TAG or release["draft"] or release["prerelease"]:
        raise ValueError("Unexpected Codex release metadata")
    for name in ASSETS:
        asset = next(a for a in release["assets"] if a["name"] == name)
        url = "https://github.com/openai/codex/releases/download/" + TAG + "/" + name
        if asset["browser_download_url"] != url:
            raise ValueError("Unexpected binary origin")
        data = fetch(url)
        if asset["digest"] != "sha256:" + hashlib.sha256(data).hexdigest():
            raise ValueError("Codex release asset digest mismatch")
        with tarfile.open(fileobj=io.BytesIO(data)) as archive:
            members = [m for m in archive.getmembers() if m.isfile()]
            if len(members) != 1:
                raise ValueError("Expected exactly one executable")
            stream = archive.extractfile(members[0])
            if stream is None:
                raise ValueError("Missing release executable")
            output = target / ("codex" if name.startswith("codex-") else "bwrap")
            output.write_bytes(stream.read())
            output.chmod(0o755)
        print(name + " " + asset["digest"])


if __name__ == "__main__":
    main()
