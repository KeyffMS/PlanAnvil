# PlanAnvil — OpenAI Codex Compliance Record

> **Verification date:** 2026-07-12  
> **Scope:** documentation contract for the first production-ready PlanAnvil implementation  
> **Rule:** only current official OpenAI documentation is authoritative for Codex behavior.

## 1. Official sources

| Area | Official source | Contract decision |
|---|---|---|
| Skills | https://developers.openai.com/codex/skills/ | Use `.agents/skills/plan-anvil/`; disable implicit invocation |
| Hooks | https://developers.openai.com/codex/hooks/ | Project hooks live beside active `.codex` config; trust is required; hooks are defense in depth |
| Subagents | https://developers.openai.com/codex/subagents/ | Project custom agents live in `.codex/agents/`; `agents.max_depth = 1` is the documented flat-topology setting |
| Project instructions | https://developers.openai.com/codex/guides/agents-md/ | Map `AGENTS.override.md`, `AGENTS.md`, configured fallbacks, precedence, and size limits |
| Configuration reference | https://developers.openai.com/codex/config-reference/ | Validate every used key and supported value |
| Git worktrees | https://developers.openai.com/codex/environments/git-worktrees/ | Worktrees share Git metadata and isolate checked-out files; PlanAnvil performs its own Git capability probe |
| Sandboxing and approvals | https://developers.openai.com/codex/sandbox/ | Do not assume workspace file permission implies `.git` metadata permission |
| GPT-5.6 guidance | https://developers.openai.com/api/docs/guides/prompt-guidance-gpt-5p6 | Keep prompts explicit, scoped, and evidence-driven |

Redirects from `developers.openai.com` to the current official ChatGPT Learn documentation remain official OpenAI sources.

## 2. Confirmed active decisions

### 2.1 Skill location and activation

Official documentation states that repository skills are discovered under `.agents/skills` from the current working directory up to the repository root.

The skill therefore uses:

```text
.agents/skills/plan-anvil/
```

The skill metadata uses:

```yaml
policy:
  allow_implicit_invocation: false
```

Explicit `$plan-anvil` invocation remains available.

### 2.2 Hooks

Official documentation confirms:

- project hooks may be defined in `<repo>/.codex/hooks.json` or inline in `<repo>/.codex/config.toml`;
- project `.codex` configuration must be trusted;
- non-managed command hooks require review and trust of the current definition;
- `PreToolUse` covers supported Bash, `apply_patch`, and MCP paths but does not cover every equivalent tool path;
- `SubagentStart` may add context, but `continue: false` does not stop the subagent;
- hook commands need Windows overrides where commands differ.

PlanAnvil therefore treats hooks as optional defense in depth and requires deterministic postcondition checks in every hook mode.

### 2.3 Custom agents and depth

Official documentation states:

- project custom agents live under `.codex/agents/`;
- each agent defines `name`, `description`, and `developer_instructions`;
- `agents.max_depth` defaults to `1`;
- depth `1` allows direct children and prevents deeper descendants.

PlanAnvil therefore:

- defines only planning-time profiler and reviewer agents in its own project integration;
- recommends depth `1` in the generated future execution contract;
- audits actual agent evidence as an additional correctness control;
- does not claim that depth `1` is ineffective.

### 2.4 Project instructions and truncation

Official documentation confirms:

- `AGENTS.override.md` has precedence in a directory;
- `AGENTS.md` and configured fallback names participate in discovery;
- `project_doc_max_bytes` limits loaded project instructions;
- the documented default combined limit is 32 KiB at verification time.

PlanAnvil explicitly reads and hashes complete instruction files rather than relying only on automatic context loading.

### 2.5 Worktrees and Git permissions

Official worktree documentation confirms that linked worktrees have separate checked-out files and share Git metadata.

The documentation does not guarantee that a particular Codex permission mode can write all required `.git` metadata. PlanAnvil therefore performs a safe, reversible Git probe that tests the operations it will actually use.

## 3. Resolved documentation conflicts

### 3.1 Generator versus executor

Previous documentation mixed features implemented by PlanAnvil with requirements written into the later execution plan.

Resolution:

- PlanAnvil implements only plan generation and validation;
- Jim, Jenny, implementation agents, integration branches, and live testing exist only in the generated execution contract;
- planning-time agents have separate names and responsibilities.

This preserves the original product idea.

### 3.2 Profile creation before planning isolation

Previous ordering required profile creation before the planning worktree while also forbidding source-worktree changes.

Resolution:

```text
preflight
→ Git capability probe
→ planning worktree
→ profiles
```

Both profiles are created inside the planning worktree.

### 3.3 Markdown-only state

Previous documentation listed Markdown state files without a deterministic parsing contract.

Resolution:

- machine state is versioned JSON;
- human contracts and reports remain Markdown;
- stage Markdown has restricted frontmatter or a JSON sidecar.

### 3.4 Ref-only Git probe

Previous documentation tested only temporary ref writes while later requiring branches, worktrees, index changes, and commits.

Resolution: the probe now tests every required Git operation and reports identity, signing, hook, worktree, and base-resolution failures separately.

## 4. Runtime variance and unresolved evidence

### 4.1 Historical C03 observation

The previous capability baseline claimed that a grandchild agent started with `agents.max_depth = 1`.

This conflicts with current official documentation, which states that depth `1` prevents children from spawning deeper descendants.

Current treatment:

```text
OBSERVED_UNREPRODUCED
CONTRADICTED_BY_CURRENT_DOCUMENTATION
NOT_AN_ACTIVE_ARCHITECTURE_ASSUMPTION
```

The observation may be retained as a regression test target, but it must not be represented as current expected behavior until reproduced with:

- exact Codex version;
- exact config;
- exact prompt;
- full sanitized event evidence;
- fixture repository commit;
- operating system and model slug.

Actual tree auditing remains useful as defense in depth, but not because the contract asserts that `max_depth = 1` is broken.

### 4.2 Capability tests without retained evidence

A prose summary without commands, fixtures, and results is not reproducible evidence.

Historical findings may guide test creation, but active claims require committed sanitized evidence or current official documentation.

## 5. Unsupported active behaviors

The first implementation does not claim:

- that a hook intercepts every write path;
- that `SubagentStart` can block startup;
- that untrusted project hooks execute;
- that custom-agent labels alone enforce permissions;
- that PlanAnvil can elevate its own sandbox or Git permissions;
- that Codex worktrees always start on an attached branch;
- that a conversational checkpoint is durable;
- that automatic compaction can be blocked indefinitely without usability failure;
- that the generator can safely execute the generated plan in the same run;
- that PlanAnvil integrates with Superpowers.

## 6. Required compatibility review

Before each release:

1. review every official URL above;
2. record verification date;
3. record Codex version used for capability tests;
4. record model slugs;
5. rerun critical tests;
6. compare all used config keys and hook fields with current docs;
7. update or remove contradicted behavior;
8. ensure no unresolved contradiction affects an active requirement.

A change in official documentation invalidates the relevant compatibility record until reviewed.

## 7. Compliance checklist

- [x] Native repository skill path specified
- [x] Implicit invocation disabled
- [x] Generator/executor boundary explicit
- [x] Project hook location and trust documented
- [x] Hook enforcement limitations documented
- [x] `SubagentStart` treated as context/audit only
- [x] Project custom-agent location documented
- [x] Current `max_depth = 1` behavior represented accurately
- [x] Instruction precedence and truncation documented
- [x] Git permission behavior capability-tested rather than assumed
- [x] Machine state formats defined
- [x] Unsupported behaviors removed from active contract
- [ ] Production implementation and committed capability fixtures completed
