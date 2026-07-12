# Plan and stage contract

`PLAN.md` records stable decisions and guardrails. Stage briefs contain execution detail. Plans describe what must be true, not speculative full implementations.

## PLAN.md required content

- identity and contract versions;
- original goal, outcome, and definition of done;
- generator stop boundary;
- separate execution-run prompt;
- scope and exclusions;
- assumptions, unknowns, confidence, and evidence;
- applicable instructions and conflict resolutions;
- system, component, data, and state-flow summaries;
- dependencies and change classification;
- stable stage index;
- requirement → stage → criterion → risk → control/test → evidence traceability;
- testing, Git, integration, production verification, rollback, recovery, resume, and approval rules;
- status, exactly one next action, and final report requirements.

Reject unsupported signatures, stale permanent line numbers, unverified deployment commands, placeholders, or instructions that continue implementation in the generator run.

## Stage rules

Each stage has a permanent ID such as `STAGE-03` or `STAGE-03A`, one outcome, scope, exclusions, affected paths or discovery procedure, `applicable_instructions` path/hash metadata, dependencies, conflicts, acceptance criteria, risks, controls, one modifier role at a time, independent verification, one coherent implementation commit, and one verified control checkpoint.

Split stages across independent domains, unrelated responsibilities, distinct risks, criteria, deployments, or rollback boundaries.

## Critical unknowns

Block readiness when expected behavior, critical evidence, public API behavior, migration behavior, rollback, irreversible actions, security/permissions, or production switching cannot be safely defined.

Every critical requirement must reach verifiable evidence. Any critical traceability gap blocks `PLAN_READY`.
