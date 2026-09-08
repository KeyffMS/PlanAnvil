from pathlib import Path
r=Path('.')
def replace(path,old,new):
 p=r/path;s=p.read_text();assert old in s,path;p.write_text(s.replace(old,new))
replace('README.md',
 '**Full baseline 2.3 qualification passed:** run [#25](https://github.com/KeyffMS/PlanAnvil/actions/runs/34060321283) reproduced C01–C16 on source commit `d0384f76bc4150d33bb8f51ef5981f3243b3cfb3`, with Codex CLI `0.153.4`, model `gpt-5.6-sol`, and Debian 13. C04 is informational; the other fifteen capabilities gate qualification. The complete sanitized evidence is committed under `capabilities/` and preserved unchanged under `qualifications/34060321283/`.\n\n**Release status remains candidate.** The old C08 positive trial proved its narrow unblock assertion but later timed out. Its finite replacement must finish in a new live `mode=c08` run and its evidence must be committed before production publication. C13 was reproduced through the explicit known-error-gated non-ephemeral fallback, not by proving ephemeral spawning works.',
 '**Full baseline 2.3 qualification and finite C08 closure passed:** run [#27](https://github.com/KeyffMS/PlanAnvil/actions/runs/34140846679) reproduced C01–C16 on source commit `a9cdcdc1e0cad70e88b60869e75e4166046dd306`, with Codex CLI `0.153.4`, model `gpt-5.6-sol`, and Debian 13. C04 is informational; the other fifteen capabilities gate qualification. The exact sanitized packages are committed under `capabilities/`; the original archive, summary and provenance are preserved under `qualifications/34140846679/`. Historical run #25 remains unchanged.\n\n**Qualification is complete for that tested configuration; signed publication is a separate step.** C08 now proves both the expected missing-checkpoint stop and a completed repaired recovery, without timeout. C09 and both C10 probes also completed without timeout. C13 was reproduced through the explicit known-error-gated, project-scoped non-ephemeral fallback; ephemeral spawning is not claimed as working. This evidence import does not create a production tag or GitHub Release.')
replace('README.md','python tools/release_check.py --candidate\n```','python tools/release_check.py --candidate\n# On a clean checkout containing the reviewed live evidence:\npython tools/release_check.py\n```')
status='''# Qualification status

## Current reviewed full result

**Live qualification is complete for the tested configuration.** Owner-initiated
full run #27 (`34140846679`) passed baseline 2.3 C01-C16 on executed source
`a9cdcdc1e0cad70e88b60869e75e4166046dd306`, Codex CLI 0.153.4,
model `gpt-5.6-sol`, Debian GNU/Linux 13. C04 is informational; fifteen
capabilities are required. The full run reports `release_gate_passed=true`.
All model-backed trials ran on the authenticated self-hosted runner.

The original archive, exact summary and verified provenance are preserved in
`qualifications/34140846679/`. `qualifications/index.json.current_run` points to
that run. Current `capabilities/C01` through `C16` are exact archive copies,
not rewritten observations or a combination of partial runs. The executed source
SHA remains the original SHA, never the later evidence-import commit.

## C08 closure and recovery regressions

C08 completed its finite stop/repair protocol in the same canonical run:

- Without a checkpoint: one completed pressure command, an actual automatic
  PreCompact `continue=false`, expected process exit 1 after 10.643 seconds,
  no PostCompact and no timeout.
- After the outer harness created a real valid checkpoint: pressure, one
  automatic PreCompact/PostCompact cycle, SessionStart(source=compact), finish
  reconciliation and positive structured completion; exit 0 after 36.265 seconds,
  no timeout. All nine positive protocol checks passed.

C09 completed all three reconciliations and two ordered automatic recovery
cycles with exit 0 in 60.679 seconds. Both independent C10 context-delivery
probes completed with exact recovery values and exit 0. Process cleanup and
checkpoint/source immutability checks passed for the recovery probes.

There are no recorded `timeout=true` values in the current actual evidence.
This is not a guarantee of future model behavior or support for untested
Codex/model/operating-system combinations.

## Retained compatibility limitation

C13 passed using the explicitly allowed project-scoped non-ephemeral fallback
after the recognized ephemeral parent-thread failure. Agent and SubagentStart
hook remained project-scoped; child context, cleanup and authentication
invariants passed. Ephemeral spawning is not claimed as working.

## Integrity and publication boundary

The archive contains 166 manifest-listed files plus the manifest, including
three hidden fixture files. All SHA-256 checks, per-capability package validation
and source identities were verified before import. The qualified .agents/.codex
product bytes, runtime implementations, permission policy and release guards
are unchanged by this evidence/documentation update.

On a clean checkout, run `python tools/validate_capabilities.py` and
`python tools/release_check.py` without `--candidate`. The latter requires the
complete full-run archive, exact packages, unchanged qualified product bytes
and finite C08 completion. Freshly materialized unexecuted templates still start
BLOCKED and cannot inherit the archived success.

No additional live run is required merely to record these same results or
update documentation. Requalify when relevant product/runtime inputs change.
Production publication remains a separate owner-authorized verified signed
annotated tag and release workflow, as described in `RELEASE.md`. No production
tag or release is created by the evidence import.

## Preserved history

Run #25 (`34060321283`, source `d0384f76bc4150d33bb8f51ef5981f3243b3cfb3`)
passed the older narrow assertions but its positive C08 trial later timed out.
Its original archive, summary, provenance and caveat remain unchanged under
`qualifications/34060321283/`; it is not the current publication evidence.

PR #34 merged the finite C08 repair. Automated run #26 (`34109662176`) was
rejected by the local initiating-actor policy before Codex. It provides no live
result. The owner-initiated #27 completed without changing or bypassing that
policy. PR #35 clarified the requirement for one complete full archive.

## Verification layers and audit index

Unit/process tests and real-CLI loopback conformance check implementation and
protocol behavior. Only the authenticated self-hosted run supplies live-model
evidence. The archived full result does not imply execution of every possible
application plan; PlanAnvil generates and validates plans, never implements them.

- `CODEX_CAPABILITY_QUALIFICATION_2026-08-28.md`: historical prerequisite-limited attempt.
- `CODEX_QUALIFICATION_EXECUTION_AUDIT_2026-09-05.md`: C13 argv and C10 worktree discovery.
- `CODEX_RECOVERY_DELIVERY_AUDIT_2026-09-05.md`: context delivery and diagnostics.
- `CODEX_C09_FINITE_RECOVERY_AUDIT_2026-09-06.md`: finite C09 repair.
- `CODEX_C08_CLOSURE_AUDIT_2026-09-07.md`: finite C08 implementation.

Older harness modules remain active v7 dependencies, not separate supported
entry points. They must not be removed as cosmetic cleanup.
'''
(r/'docs/QUALIFICATION_STATUS.md').write_text(status)
replace('docs/CODEX_SANDBOX_RUNBOOK.md',
 'Full run #25 is archived and passed baseline 2.3 on Codex CLI 0.153.4. The finite C08 stop/repair replacement is merged. Publication now requires a successful new full run and import of its complete evidence. `QUALIFICATION_STATUS.md` is the current status; this runbook describes both full requalification and targeted checks.',
 'Full run #27 is reviewed and archived: baseline 2.3 C01-C16 and finite C08 stop/repair passed on Codex CLI 0.153.4. Its complete evidence is recorded in the repository; no new run is needed just to import it. Historical #25 remains unchanged. `QUALIFICATION_STATUS.md` records the tested configuration, limitations and publication boundary. This runbook describes future full requalification and targeted checks.')
replace('docs/CODEX_SANDBOX_RUNBOOK.md','Use **mode=full** for the next publication-closing C01-C16 sequence.', 'Use **mode=full** when a new publication-closing C01-C16 qualification is needed.')
replace('docs/CODEX_SANDBOX_RUNBOOK.md',
 'Start a NEW **PlanAnvil Codex qualification -> Run workflow -> main -> full** from an account allowed by the local runner\'s initiating-actor policy. Automated run #26 (`34109662176`) was rejected by that policy before any Codex trial; do not rerun it or relax the allowlist. The repair is on main, but that rejected launch provides no model-backed result.',
 'For requalification, start a NEW **PlanAnvil Codex qualification -> Run workflow -> main -> full** from an account allowed by the local runner\'s initiating-actor policy. Automated run #26 (`34109662176`) was rejected before any Codex trial. Owner-initiated #27 then passed; do not rerun the rejected launch or relax the allowlist.')
replace('docs/CODEX_SANDBOX_RUNBOOK.md',
 'Full capability qualification and publication closure are separate. Preserve the original #25 archive unchanged. For publication, review and commit a new successful full-run archive whose C08 has finite completion evidence, along with its exact C01-C16 packages and actual executed source SHA. Update `qualifications/index.json` to that full run as described in `RELEASE.md`. Never replace the full-run index with a partial-mode index or splice a targeted result into an older archive.',
 'Full capability qualification and signed publication are separate. Current full run #27 supplies finite C08 completion and exact C01-C16 packages; `qualifications/index.json` identifies it. Preserve both #25 and #27 archives unchanged. Any future qualification must be imported as one complete source-bound full archive as described in `RELEASE.md`. Never replace the full-run index with a partial-mode index or splice a targeted result into an older archive.')
replace('docs/RELEASE.md',
 'For the current C08 closure, use a NEW `mode=full` run on main, initiated by an account allowed by the self-hosted runner. The production validator requires a single complete full-run archive containing the finite C08 proof. A successful `c08` or `recovery` diagnostic is useful but its partial archive cannot replace that full run. See `docs/QUALIFICATION_STATUS.md` for the merged repair and the automated launch rejected before testing.',
 'Current full run #27 (`34140846679`) passed and its exact reviewed evidence is committed, including finite C08 stop/repair completion. No further live run is required merely to record this result. The production validator still requires one complete full-run archive; a `c08` or `recovery` diagnostic cannot replace it. See `docs/QUALIFICATION_STATUS.md` for provenance, tested scope and the retained C13 fallback limitation.')
replace('docs/RELEASE.md','## Qualification closure (2026-09-07)','## Qualification closure (reviewed 2026-09-08)')
replace('docs/RELEASE.md',
 'negative-stop/positive-completion evidence. The old C08 timeout keeps production\nblocked until the new complete full-run result is committed. Candidate checks\nintentionally remain usable before that result exists.',
 'negative-stop/positive-completion evidence. Full #27 now supplies that proof;\nthe old #25 timeout remains recorded as history. Candidate checks still do not\nsubstitute for strict production validation. Run `python tools/release_check.py`\non the clean evidence-import commit before any signed publication.')
replace('docs/RELEASE.md',
 'After the complete new full-run evidence is imported and CI is green, preparation\nis complete; the signed annotated production tag remains a separate authorized\npublication. No unsigned or lightweight tag may substitute for the required\nverified signature.',
 'The complete #27 evidence is imported. After strict validation and green CI on\nthe evidence-import commit, qualification preparation is complete; a signed\nannotated production tag remains a separate authorized publication. This import\ndoes not create a tag or release. No unsigned or lightweight tag may substitute\nfor the required verified signature.')
replace('CHANGELOG.md', '## [Unreleased]\n', '''## [Unreleased]

### Qualification closure — 2026-09-07

- full self-hosted run #27 (`34140846679`) reproduced all C01-C16 on executed source `a9cdcdc1e0cad70e88b60869e75e4166046dd306`, Codex CLI 0.153.4, `gpt-5.6-sol`, Debian 13;
- finite C08 now proves the intended missing-checkpoint stop and completed repaired recovery without timeout; C09/C10 regressions passed;
- preserve the exact full archive and provenance, update current capability evidence, and retain historical #25 unchanged;
- C13 retains the documented project-scoped, known-error-gated non-ephemeral fallback; no new transport claim or product/runtime/security change;
- qualification is recorded; signed production publication remains a separate action.
''')
p=r/'tests/test_qualification_closure.py'
s=p.read_text(); marker='    def copy_repo(self, tmp):'
assert marker in s
s=s.replace(marker, '''    def test_reviewed_current_full_archive_closes_evidence_gate(self):
        # Read real committed evidence; no synthetic result or CLI simulation.
        self.assertEqual(closure.closure_blockers(ROOT), [])
        index = json.loads((ROOT / 'qualifications/index.json').read_text())
        self.assertEqual(index['c08_closure'], 'REPRODUCED')
        folder = ROOT / 'qualifications' / index['current_run']
        provenance = json.loads((folder / 'provenance.json').read_text())
        self.assertEqual(provenance['qualification_mode'], 'full')
        with zipfile.ZipFile(folder / 'evidence-artifact.zip') as z:
            summary_bytes = z.read('qualification-summary.json')
            self.assertEqual((folder / 'qualification-summary.json').read_bytes(), summary_bytes)
            summary = json.loads(summary_bytes)
            self.assertEqual(summary['github_actions_run'], index['current_run'])
            self.assertEqual(summary['source_commit'], provenance['source_commit'])
            self.assertTrue(summary['release_gate_passed'])
            self.assertEqual(summary['required_not_reproduced'], [])

    def test_current_package_change_is_not_accepted_as_archived_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = self.copy_repo(tmp)
            path = root / 'capabilities/C09/actual.sanitized.json'
            # Even a JSON-preserving edit is not the original source-bound record.
            with path.open('ab') as stream:
                stream.write(b'\\n')
            self.assertTrue(any('current capability differs from archived run' in error
                                for error in closure.closure_blockers(root)))

'''+marker)
p.write_text(s)
print('Docs and evidence regression tests updated; no runtime code changed.')
