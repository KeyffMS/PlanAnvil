from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
from pathlib import Path

import live_codex_qualification_harness_v7 as v7

base = v7.base
SCOPE = ("C09", "C10", "C13")


def selected_summary(results: dict[str, str]) -> dict:
    """A successful targeted run is never a successful full release gate."""
    missing = [cid for cid in SCOPE if results.get(cid) != "REPRODUCED"]
    return {
        "scope": list(SCOPE),
        "diagnostic_only": True,
        "results": {cid: results.get(cid, "BLOCKED") for cid in SCOPE},
        "selected_not_reproduced": missing,
        "selected_gate_passed": not missing,
        "release_gate_passed": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the existing C09/C10/C13 live runtimes only")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-c13-non-ephemeral-fallback", action="store_true", required=True)
    args = parser.parse_args(argv)
    root = args.root.resolve()
    output = args.output.resolve()
    if output == root or output in root.parents or output.is_relative_to(root):
        raise base.QualificationError("Evidence output must be separate from the qualification repository")

    v7.prior._prepare_controller_root(root, args.source_commit)
    version = base.codex_version()
    os_name = base.os_label()
    date = dt.date.today().isoformat()
    runtime_root = root / ".qualification-runtime"
    shutil.rmtree(runtime_root, ignore_errors=True)
    runtime_root.mkdir()
    exclude = root / ".git" / "info" / "exclude"
    with exclude.open("a", encoding="utf-8") as handle:
        handle.write("\n.qualification-runtime/\n")

    old_fallback = v7.v6.ALLOW_NON_EPHEMERAL_FALLBACK
    results: dict[str, str] = {}
    try:
        schemas = base.write_schemas(runtime_root / "schemas")
        v7._install()
        v7.v6.ALLOW_NON_EPHEMERAL_FALLBACK = args.allow_c13_non_ephemeral_fallback
        for cid in SCOPE:
            print(f"=== {cid}: targeted live qualification ===", flush=True)
            try:
                result, _required = v7.v6.capability_runtime(
                    root=root, runtime_root=runtime_root, capability_id=cid,
                    schemas=schemas, version=version, os_name=os_name,
                    source_commit=args.source_commit, date=date,
                )
                if result not in {"REPRODUCED", "FAILED", "BLOCKED"}:
                    raise base.QualificationError("Capability runtime returned an invalid classification")
            except Exception as exc:
                # Same evidence contract as full. Continue to the other selected
                # capabilities; an incomplete probe never becomes a release pass.
                blocker = base.sanitize_text(f"{type(exc).__name__}: {exc}")
                base.write_evidence(
                    root=root, capability_id=cid, result="BLOCKED", expected_met=False,
                    observations=["Targeted qualification controller did not complete this capability."],
                    blocker=blocker, summary=f"{cid} blocked by qualification controller error.",
                    trials=[], fixture_commit=None, version=version, os_name=os_name,
                    source_commit=args.source_commit, date=date,
                )
                base.local_commit(root, cid)
                result = "BLOCKED"
            results[cid] = result
            print(f"{cid}: {result}", flush=True)

        # finalize_index considers ALL required capabilities, not merely SCOPE.
        base.finalize_index(root, date=date, source_commit=args.source_commit,
                            run_id=args.run_id, results=results)
        summary = {
            "schema_version": "1.0", "date": date,
            "source_commit": args.source_commit, "github_actions_run": args.run_id,
            "codex_version": version, "model": base.MODEL, "os": os_name,
            **selected_summary(results),
        }
        base.stage_artifact(root, output, summary)
        print(json.dumps(summary, indent=2, sort_keys=True), flush=True)
        return 0 if summary["selected_gate_passed"] else 2
    finally:
        v7.v6.ALLOW_NON_EPHEMERAL_FALLBACK = old_fallback
        shutil.rmtree(runtime_root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
