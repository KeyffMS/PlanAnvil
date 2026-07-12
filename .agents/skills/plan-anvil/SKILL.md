---
name: plan-anvil
description: Generate and validate a rigorous, test-driven implementation plan in an isolated Git worktree. Use only when explicitly invoked as $plan-anvil. Never implement or execute the generated plan.
---

# PlanAnvil

Create an auditable implementation contract, commit planning artifacts only, report the result, and stop.

## Boundary

- Never modify product code or product tests.
- Never execute a generated stage or start the later executor.
- Never stash, reset, clean, deploy, migrate, restart services, switch a live system, or push or merge the base branch.
- Keep the source worktree unchanged. Treat canonical files and Git as durable state, not conversation memory.
- Do not continue into implementation after approval in the same run.

## Workflow

1. Read every applicable repository instruction and `references/lifecycle.md`. Current official Codex documentation has higher authority than bundled references.
2. Start the deterministic bootstrap controller:

   ```text
   python .agents/skills/plan-anvil/scripts/plan_anvil.py start \
     --source "$PWD" \
     --goal "<exact user goal>" \
     --codex-version "<actual or unknown>" \
     --model "<actual or unknown>" \
     --permission-mode "<actual or unknown>" \
     --project-trust <TRUSTED|UNTRUSTED|UNKNOWN> \
     --hook-mode <HOOKS_TRUSTED|HOOKS_DISABLED|HOOKS_UNTRUSTED|HOOKS_UNAVAILABLE>
   ```

   This performs read-only preflight, a real reversible Git ref/branch/worktree/index/commit probe, planning-worktree isolation, profiling, run scaffolding, and durable bootstrap evidence. On any non-ready result, preserve evidence, report the exact blocker, and stop.
3. Continue only in the returned planning worktree and run root. Fully read and hash all applicable instruction files, resolve their scope and precedence, and write the instruction map with `map_instructions.py`. A remaining critical conflict blocks the run.
4. Analyze the goal from repository evidence. Record immutable `evidence/analysis.md` and `.json` with `record_analysis.py`. A critical unknown blocks readiness; non-critical ambiguity requires an evidence-backed interpretation and verification method.
5. Using the templates and references, author `PLAN.md`, stable stage briefs, acceptance criteria, risks, controls, rollback, recovery, approvals, and complete traceability. Write requirements for a separate later execution run, not executable product changes. Seal the contract with `seal_artifacts.py`.
6. Run `validate_all.py --phase pre-review`. Do not proceed unless profiles, schemas, privacy, source immutability, instruction coverage, plan structure, traceability, risks, and the planning-branch diff all pass.
7. Build the immutable review bundle with `prepare_review_bundle.py`. Dispatch a fresh read-only reviewer without planner reasoning, record its single blind result with `record_blind_review.py`, then run `compare_review.py`. Any failed or stale review blocks readiness.
8. Run `commit_plan.py`. It repeats the final gates, writes the final report, commits only allowlisted planning/control artifacts, preserves the source worktree, and never pushes.
9. Report status, planning branch, commit SHA, plan path, assumptions, unknowns, review result, and the separate execution-run prompt. State: `No implementation was executed. Start a separate Codex run using the execution prompt in PLAN.md.` Then stop.

## Decision policy

Ask the user only when the unresolved decision materially changes business scope, public behavior, architecture, irreversible behavior, security/privacy/legal policy, live switching, base integration, or critical acceptance and rollback evidence. Derive and record all other implementation-planning decisions from the strongest available evidence.

## References

- `references/lifecycle.md` — state order, Git isolation, ownership, and blockers
- `references/plan-contract.md` — required plan and stage content
- `references/artifact-contract.md` — canonical state, schemas, privacy, and path safety
- `references/review-and-stop.md` — validation, blind review, commit, and hard stop
- `references/execution-contract.md` — contract for the separate later implementation run
