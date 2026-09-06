"""C10 value-flow checks. Never retain proof values or model/hook text."""
from __future__ import annotations

import hashlib
import re
from typing import Any

PREFIX = "C10_RECOVERY_ECHO="


def echo_diagnostics(payload: dict[str, Any], proof: str) -> dict[str, Any]:
    observations = payload.get("observations")
    strings = [x for x in observations if isinstance(x, str)] if isinstance(observations, list) else []
    expected = PREFIX + proof
    exact = any(s.strip() == expected for s in strings)
    candidates = [m for s in strings for m in re.findall(r"C10_RECOVERY_ECHO=([^\s`\"'<>]*)", s)]

    def contains(value: Any) -> bool:
        if isinstance(value, str):
            return proof in value
        if isinstance(value, list):
            return any(contains(x) for x in value)
        if isinstance(value, dict):
            return any(contains(x) for x in value.values())
        return False

    present = any(proof in s for s in strings)
    return {
        "observations_is_array": isinstance(observations, list),
        "exact_observation": exact,
        "expected_value_in_observations": present,
        "expected_value_elsewhere": contains({k: v for k, v in payload.items() if k != "observations"}),
        "echo_prefix_observed": any(PREFIX in s for s in strings),
        "candidate_count": len(candidates),
        "candidate_lengths": [len(x) for x in candidates[:8]],
        "matching_candidate_count": sum(x == proof for x in candidates),
        "classification": (
            "exact" if exact else "expected_value_wrong_format" if present
            else "different_value" if candidates else "no_echo"
        ),
    }


def proxy_source(proof: str) -> str:
    # A one-way digest is embedded before bootstrap, not the secret itself.
    # The proxy forwards the PRODUCT stdout/stderr and exit code unchanged.
    digest = hashlib.sha256(proof.encode("utf-8")).hexdigest()
    return _PROXY.replace("__EXPECTED_DIGEST__", digest)


_PROXY = r'''from __future__ import annotations
import hashlib, json, subprocess, sys
from pathlib import Path
import re

expected_digest = "__EXPECTED_DIGEST__"
event_name, script_name = sys.argv[1], sys.argv[2]
raw = sys.stdin.read()
root = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip())
completed = subprocess.run([sys.executable, str(root / ".codex/hooks" / script_name)],
    input=raw, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
try:
    event = json.loads(raw)
except (ValueError, TypeError):
    event = {}
try:
    parsed = json.loads(completed.stdout)
    parsed_valid = isinstance(parsed, dict)
except (ValueError, TypeError):
    parsed = {}
    parsed_valid = False
record = {"event": event_name, "returncode": completed.returncode,
          "product_stdout_is_json": parsed_valid,
          "product_stderr_present": bool(completed.stderr)}
if isinstance(event, dict) and isinstance(event.get("source"), str) and event["source"] in {"startup", "resume", "clear", "compact"}:
    record["source"] = event["source"]
if isinstance(parsed, dict):
    record["system_message_present"] = bool(parsed.get("systemMessage"))
    if "continue" in parsed:
        record["continue"] = parsed["continue"] is not False
    output = parsed.get("hookSpecificOutput")
    if isinstance(output, dict):
        text = output.get("additionalContext")
        text = text if isinstance(text, str) else ""
        candidates = re.findall(r"evidence/c10-recovery-([0-9a-f]{32})\.json", text)
        record.update({"additional_context": bool(text), "context_chars": len(text),
            "recovery_target_count": len(candidates),
            "recovery_target_matches_expected": len(candidates) == 1 and
                hashlib.sha256(candidates[0].encode("utf-8")).hexdigest() == expected_digest,
            "output_event_matches_input": isinstance(event, dict) and
                output.get("hookEventName") == event.get("hook_event_name") == event_name})
try:
    log = root / ".pursue/qualification-hook-events.jsonl"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
except Exception:
    pass
sys.stdout.write(completed.stdout)
sys.stderr.write(completed.stderr)
raise SystemExit(completed.returncode)
'''
