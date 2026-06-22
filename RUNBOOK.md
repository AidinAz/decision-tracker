# Decision Tracker Runbook

## What This Project Is

Decision Tracker is a small CLI-based system for recording important ML workflow decisions as Markdown files in the repository, validating those records against project rules, and generating deterministic exports for reporting and for a read-only viewer.

The project is designed for thesis-style evaluation work where the priorities are:

- low-friction decision capture
- traceability between decisions and supporting artifacts
- deterministic, reproducible reporting
- no external integrations or network dependencies

This is not a workflow platform. It does not manage issues, experiments, or revisions itself. It records references to them.

## Core Idea

Every important decision is stored as a Decision Record in [`decisions/`](decisions/).

A Decision Record:

- has YAML front matter
- has required Markdown sections
- can link to evidence and implementation artifacts
- can supersede older decisions

The CLI reads those records and produces:

- `decisions/index.json`
- `decisions/graph.json`
- `decisions/artifacts.json`
- `reports/metrics.csv`
- `reports/report.md`

Those outputs are deterministic. If the input records do not change, the generated outputs should not change.

## Repository Map

- [`src/dt/cli.py`](src/dt/cli.py): thin Typer entrypoint and command option declarations
- `src/dt/commands.py`: command handlers
- `src/dt/validation.py`, `src/dt/reporting.py`, `src/dt/templates.py`: core validation, report generation, and template rules
- [`decisions/`](decisions/): current project Decision Records
- [`docs/`](docs/): supporting notes referenced by records
- [`fixtures/decisions`](fixtures/decisions): canonical sample Decision Records
- [`fixtures/expected`](fixtures/expected): golden expected outputs
- [`tests`](tests): regression and behavior tests
- `src/dt/assets/viewer/`: packaged viewer assets emitted by `dt build-site`

## Decision Record Model

Each record is a Markdown file named like:

- `decisions/DR-0001-short-title.md`

Each file must contain:

1. YAML front matter between `---` markers
2. These required headings exactly once:
   - `## Context`
   - `## Decision`
   - `## Rationale`
   - `## Alternatives`
   - `## Consequences`

### Required YAML Fields

- `id`
- `title`
- `status`
- `type`
- `stage`
- `date`
- `owner`
- `stakeholders`
- `template_version`
- `links`

### Frozen Enums

`status`

- `proposed`
- `accepted`
- `rejected`
- `superseded`
- `deprecated`

`type`

- `generic`
- `model`
- `evaluation_protocol`

`stage`

- `data`
- `training`
- `evaluation`
- `deployment`
- `monitoring`

`rel`

- `implements`
- `evaluated_by`
- `supported_by`
- `supersedes`

`artifact_kind`

- `code`
- `data`
- `experiment_run`
- `document`
- `issue`

## Templates

There are three decision types.

### `generic`

Use this for decisions that do not need a specialized schema.

Requires:

- base YAML fields
- required headings

### `model`

Use this for model-selection or model-definition decisions.

Requires `model_spec`:

```yaml
model_spec:
  objective: "Text classification"
  model_family: "Transformer encoder"
  input: "Tokenized text"
  output: "Class label"
  primary_metric: "F1"
  acceptance_criteria: "F1 >= 0.75 on fixed eval protocol"
```

Optionally, a model record can also capture training and hyperparameter decisions:

```yaml
model_spec:
  training_config:
    tuning_method: "random_search"
    search_space:
      learning_rate: "1e-5, 3e-5, 5e-5"
      batch_size: "16, 32"
      weight_decay: "0.0, 0.01"
    selected_hyperparameters:
      learning_rate: "3e-5"
      batch_size: "16"
      weight_decay: "0.01"
    stopping_rule: "Early stopping on validation F1 with patience 3"
    selection_rule: "Choose highest validation F1, then confirm once on held-out test"
    compute_environment: "Single GPU, fixed seed"
```

Use `training_config` when the decision is about how the model is trained, not only what model family is selected. The block is optional, but if you include it, `tuning_method`, `selected_hyperparameters`, and `selection_rule` must be filled.

`search_space` values are intentionally flexible. A hyperparameter can be documented as a string, a YAML list, or a nested object depending on what is clearest for the tuning method.

When the record is not `proposed`, it must also have:

- one `implements` link to `code`
- one `supported_by` link to `document` or `issue`

### `evaluation_protocol`

Use this for evaluation methodology decisions.

Requires `eval_spec`:

```yaml
eval_spec:
  dataset_ref: "dvc:3f2c9a1"
  protocol: "Stratified 70/30 split, seed=42"
  metrics:
    - name: "F1"
      threshold: ">= 0.75"
  baseline:
    ref: "decision:DR-0001"
    description: "Previous informal eval approach"
```

When the record is not `proposed`, it must also have:

- one `evaluated_by` link to `experiment_run` or `document`
- one dataset link with `artifact_kind: data` and `rel: supported_by` or `evaluated_by`

## Link Semantics

Links create the traceability graph.

Examples:

- `implements`: the decision is implemented by code or a commit
- `evaluated_by`: the decision is evaluated by an experiment run or report
- `supported_by`: the decision is supported by documentation, notes, issues, or dataset evidence
- `supersedes`: the new decision replaces an older decision

Decision-to-decision links use `ref: decision:DR-XXXX`. The tool infers that target as a decision node automatically.

## Allowed Reference Formats

Examples of valid refs:

- `git:commit:bb22cc3`
- `git:ref:main`
- `github:pr:14`
- `github:issue:52`
- `url:https://example.com/report`
- `dvc:3f2c9a1`
- `checksum:sha256:abc123`
- `data:version:2026-03-14`
- `mlflow:run:f3a0b0d1b2c34e`
- `wandb:run:abc123`
- `run:offline-eval-01`
- `path:docs/model-selection-notes.md`
- `decision:DR-0004`

The CLI validates refs syntactically. For `git:commit:<sha>` refs, validation also checks whether the commit exists in the local Git repository when the command is run inside one. `GIT_COMMIT_NOT_FOUND` means Git ran and the commit is absent from local history; `GIT_COMMIT_CHECK_UNAVAILABLE` means a Git repository was detected but the commit check could not complete. For `path:` refs, validation warns if the local file is missing. These evidence checks are warning-only unless strict validation is enabled.

## Commands

You can use the project in two ways.

If `dt` is installed as a console script:

```bash
dt init
dt new --title "Adopt Transformer encoder as baseline model" --stage training --type model --owner ahmet
dt validate --all
dt report
dt build-site
```

If you are working directly from source without installation:

```bash
PYTHONPATH=src python3 -m dt.cli init
PYTHONPATH=src python3 -m dt.cli new --title "Adopt Transformer encoder as baseline model" --stage training --type model --owner ahmet
PYTHONPATH=src python3 -m dt.cli validate --all
PYTHONPATH=src python3 -m dt.cli report
PYTHONPATH=src python3 -m dt.cli build-site
```

All commands accept `--root PATH`. If you omit it, the CLI walks upward from the current directory, prefers the nearest ancestor containing `decisions/`, and falls back to the nearest `.git` ancestor. This means you can run `dt validate --all` or `dt report` from a subdirectory of the repository. Use `--root` in unusual nested layouts where multiple ancestors could look like project roots.

To link a new record to the current Git commit, add `--git-head`:

```bash
PYTHONPATH=src python3 -m dt.cli new \
  --title "Record current implementation decision" \
  --stage training \
  --type generic \
  --owner ahmet \
  --git-head
```

This writes a literal `git:commit:<sha>` link. It does not store `git:HEAD`, because `HEAD` changes over time and would make generated exports ambiguous.

### `dt new`

Creates a new Decision Record with the next available `DR-XXXX` id.

Example:

```bash
PYTHONPATH=src python3 -m dt.cli new \
  --title "Switch evaluation to stratified 70/30 split" \
  --stage evaluation \
  --type evaluation_protocol \
  --owner ahmet \
  --stakeholders "ML engineer,reviewer"
```

Result:

- creates a new file under `decisions/`
- fills in the correct template scaffold
- optionally adds the current Git commit as an `implements` code link when `--git-head` is used
- prints `Created decisions/DR-XXXX-...`

`dt new` expects an initialized project. Run `dt init` first, or pass `--root` pointing at a directory that already contains `decisions/`.

### `dt init`

Initializes Decision Tracker in a repository.

Example:

```bash
dt init
```

Creates:

- `decisions/.gitkeep`
- `docs/README.md`
- `.gitignore` entries for generated Decision Tracker outputs
- `.github/workflows/pages.yml`

Existing scaffold files are not overwritten unless `--force` is passed.

### `dt validate`

Validates one record or the full repository.

Examples:

```bash
PYTHONPATH=src python3 -m dt.cli validate --all
PYTHONPATH=src python3 -m dt.cli validate --id DR-0003
PYTHONPATH=src python3 -m dt.cli validate --all --strict
```

Possible output:

```text
OK DR-0003
FAIL DR-0007: TEMPLATE_FIELD_MISSING: model_spec.primary_metric must be a non-empty string [file: decisions/DR-0007-example.md]
WARN DR-0008: DECISION_REF_NON_SUPERSEDES: links[1] references a decision with rel=supported_by [file: decisions/DR-0008-example.md]
WARN DR-0009: TODO_SECTION: Section still contains TODO placeholder: ## Context [file: decisions/DR-0009-draft.md]
```

Exit codes:

- `0`: all selected records passed
- `3`: validation failures, or warnings when `--strict` / `--fail-on-warn` is used
- `2`: filesystem error such as missing `/decisions`

Warnings are advisory by default. Strict validation is useful in CI when TODO placeholders, missing local `path:` evidence, duplicate stakeholders, or missing local Git commits should block a merge.

### `dt list`

Prints a quick inventory without generating reports.

Examples:

```bash
dt list
dt list --status accepted
dt list --type model --format json
```

Default output is a table with ID, status, type, stage, date, owner, and title. JSON output is deterministic and useful for scripts.

### `dt doctor`

Checks whether the current repository is ready to use Decision Tracker.

Examples:

```bash
dt doctor
dt doctor --format json
```

The command checks package availability, Git availability, Git repo detection, `decisions/`, the Decision Tracker `.gitignore` block, generated-output ignore behavior, the scaffolded Pages workflow, and packaged viewer assets. It exits `2` only for setup failures.

### `dt report`

Builds the deterministic exports and metrics files.

Example:

```bash
PYTHONPATH=src python3 -m dt.cli report
```

Writes:

- `decisions/index.json`
- `decisions/graph.json`
- `decisions/artifacts.json`
- `reports/metrics.csv`
- `reports/report.md`

`dt report` removes stale generated JSON exports before writing the canonical `index.json`, `graph.json`, and `artifacts.json` files. If validation errors are found, it prints the failures and exits before writing new generated outputs. This prevents invalid or stale records from producing misleading metrics.

### `dt build-site`

Builds a static viewer site under `_site/` by default.

Example:

```bash
PYTHONPATH=src python3 -m dt.cli build-site --root .
```

The command refuses to replace an arbitrary non-empty `--site-dir` unless `--force` is passed. This prevents accidental deletion when a custom output path is mistyped.

### `dt discover`

Scans local Git commit messages for possible historical decision evidence.

Example:

```bash
dt discover --since 2024-01-01
```

Useful options:

- `--keywords`: comma-separated search terms
- `--limit`: maximum number of candidates
- `--since`: Git date expression passed to `git log`

`discover` is suggestion-only. It does not create Decision Records and should not be treated as automatic decision extraction. Commit messages can identify useful evidence, but they rarely contain complete rationale, alternatives, or stakeholder context.

### `dt backfill`

Guides reconstruction of a past decision and creates a normal `proposed` record.

Example:

```bash
dt backfill
```

Non-interactive example:

```bash
dt backfill \
  --title "Reconstruct baseline model choice" \
  --stage training \
  --type model \
  --owner ahmet \
  --original-decision-date unknown \
  --evidence "git:commit:abc1234,path:docs/model-notes.md" \
  --confidence medium \
  --known-gaps "Original meeting notes unavailable;Alternatives reconstructed later"
```

Backfilled records include:

```yaml
reconstruction:
  mode: backfill
  original_decision_date: "unknown"
  evidence_confidence: "medium"
  evidence_sources:
    - git:commit:abc1234
  known_gaps:
    - Original meeting notes unavailable
```

Keep backfilled records as `proposed` until a human reviews the reconstructed context, rationale, alternatives, consequences, and any template-specific fields. Use normal validation during reconstruction, then use `dt validate --strict` once TODO and checklist warnings are resolved or intentionally accepted by review.

## Typical Workflow

### Scenario 1: Adding a New Model Decision

You decide to adopt a new architecture for an ML baseline.

1. Create a record:

```bash
PYTHONPATH=src python3 -m dt.cli new \
  --title "Adopt Transformer encoder as baseline model" \
  --stage training \
  --type model \
  --owner ahmet \
  --stakeholders "ML engineer,supervisor"
```

2. Fill in:
   - `model_spec`
   - optional `model_spec.training_config` if the decision includes fine-tuning or hyperparameter choices
   - the required sections
   - one supporting document or issue link
   - one implementation code link

3. Validate:

```bash
PYTHONPATH=src python3 -m dt.cli validate --id DR-0002
```

4. Generate reports:

```bash
PYTHONPATH=src python3 -m dt.cli report
```

### Scenario 2: Backfilling Decisions In An Existing Repository

You install Decision Tracker into a project that already has models, datasets, and evaluation rules.

1. Initialize the project:

```bash
dt init
```

2. Discover possible evidence:

```bash
dt discover --since 2024-01-01
```

3. Review the printed candidates manually. Treat them as evidence clues, not confirmed decisions.

4. Create a reconstructed draft:

```bash
dt backfill
```

5. Edit the generated record. Complete rationale, alternatives, consequences, and template-specific fields.

6. Validate and publish:

```bash
dt validate --all
dt report
dt build-site
```

Use `reconstruction.known_gaps` to make missing historical context explicit. This is important for auditability: a decision recorded at the time is not the same as a decision reconstructed later.

Backfilled records include a `## Backfill Review Checklist` section. Leave unchecked items visible while reconstruction is incomplete; validation emits `BACKFILL_CHECKLIST_INCOMPLETE` as a warning. Once a reviewer confirms the reconstructed date, confidence, rationale, alternatives, consequences, gaps, and status, mark the checklist items as checked.

After that review step, run `dt validate --strict` so any remaining advisory warnings are treated as blockers before publication.

Decision Records may also include optional review metadata:

```yaml
review:
  status: pending
  reviewed_by: []
  reviewed_date: "unknown"
  notes: ""
```

When present, review metadata is validated, exported to `index.json`, shown in the viewer detail panel, and summarized in reports.

### Scenario 3: Recording an Evaluation Protocol

You standardize evaluation around a fixed split and metric threshold.

The record should include:

- `eval_spec.dataset_ref`
- `eval_spec.protocol`
- at least one metric and threshold
- baseline reference and description
- dataset evidence link
- evaluation evidence link

Good example:

```yaml
type: evaluation_protocol
eval_spec:
  dataset_ref: "dvc:3f2c9a1"
  protocol: "Stratified 70/30 split, seed=42"
  metrics:
    - name: "F1"
      threshold: ">= 0.75"
  baseline:
    ref: "decision:DR-0001"
    description: "Previous informal eval approach"
links:
  - id: "L-0001"
    rel: supported_by
    artifact_kind: data
    ref: "dvc:3f2c9a1"
  - id: "L-0002"
    rel: evaluated_by
    artifact_kind: experiment_run
    ref: "mlflow:run:f3a0b0d1b2c34e"
```

If the record is `accepted` and one of those trace links is missing, validation should fail.

### Scenario 4: Proposing a Change Without Evidence Yet

You want to propose a new threshold but do not yet have supporting artifacts.

This is allowed if the status is `proposed`.

Example:

```yaml
status: proposed
type: evaluation_protocol
links: []
```

That record can still pass validation if the template fields and required sections are present.

### Scenario 5: Replacing an Older Decision

You want to supersede `DR-0004`.

In the new record:

```yaml
links:
  - id: "L-0001"
    rel: supersedes
    artifact_kind: document
    ref: "decision:DR-0004"
```

If `DR-0004` has `status: superseded`, validation expects that some other record points to it with a `supersedes` link. If not, `SUPERSEDED_INCONSISTENT` is raised.

## Understanding the Outputs

### `decisions/index.json`

A summary list of decisions with metadata and scores.

Use it for:

- list views
- filtering by status/type/stage
- quick decision inventory
- detail views with rendered Decision Record sections and grouped links

### `decisions/graph.json`

A graph export containing:

- nodes
- typed edges

Decision node ids look like:

- `decision:DR-0005`

Artifact node ids look like:

- `artifact:<sha256(ref)>`

This keeps node ids deterministic while preserving the original `ref` elsewhere.

### `decisions/artifacts.json`

A deduplicated artifact index.

Use it to:

- inspect all referenced external artifacts
- connect hashed graph node ids back to original refs

### `reports/metrics.csv`

A deterministic tabular export of counts, booleans, and quality scores.

Key score ideas:

- `score_completeness`: structure and required content
- `score_connectedness`: number and variety of links
- `score_inclusiveness`: stakeholder coverage
- `score_traceability`: gated by template-specific minimum trace links

### `reports/report.md`

A compact human-readable summary with:

- counts
- average scores
- simple smell indicators

## Common Validation Failures

### `ID_FORMAT_INVALID`

Cause:

- `id` is not `DR-XXXX`

Bad:

```yaml
id: DR-7
```

Good:

```yaml
id: DR-0007
```

### `TEMPLATE_FIELD_MISSING`

Cause:

- a `model` or `evaluation_protocol` record is missing required template fields

Example:

```text
FAIL DR-0007: TEMPLATE_FIELD_MISSING: model_spec.primary_metric must be a non-empty string [file: decisions/DR-0007-example.md]
```

### `LINK_INVALID_FORMAT`

Cause:

- a link ref does not match any allowed pattern

Bad:

```yaml
ref: "my-custom-reference"
```

Good:

```yaml
ref: "path:docs/model-selection-notes.md"
```

### `STAKEHOLDER_DUPLICATE`

Cause:

- the same stakeholder appears more than once, case-insensitively

This is a warning, not a failure. The metrics still deduplicate stakeholders.

### `HEADING_DUPLICATE`

Cause:

- one required heading appears more than once

### `SECTION_EMPTY`

Cause:

- a required section such as `Rationale` is blank

### `MIN_LINKS_NOT_MET`

Cause:

- a non-proposed record does not satisfy template-specific traceability minima

### `SUPERSEDED_INCONSISTENT`

Cause:

- a record is marked `superseded` but no other record points to it via `rel: supersedes`

## How Determinism Is Preserved

The generated outputs are intentionally stable.

The implementation enforces:

- sorting decisions by id
- sorting links by `(rel, artifact_kind, ref, label)`
- canonical JSON formatting
- newline at EOF
- stable CSV headers and row ordering
- 3-decimal score rounding with decimal `ROUND_HALF_UP` semantics

This matters because the project includes golden fixtures in [`fixtures/expected`](fixtures/expected), and the tests compare outputs byte-for-byte.

## How to Verify the Project

Run the test suite:

```bash
python3 -m pytest -q
```

Validate fixture decisions:

```bash
PYTHONPATH=src python3 -m dt.cli validate --all
```

Generate reports:

```bash
PYTHONPATH=src python3 -m dt.cli report
```

Compare generated outputs to expected fixtures if needed:

```bash
diff -u fixtures/expected/index.json decisions/index.json
diff -u fixtures/expected/graph.json decisions/graph.json
diff -u fixtures/expected/artifacts.json decisions/artifacts.json
diff -u fixtures/expected/metrics.csv reports/metrics.csv
diff -u fixtures/expected/report.md reports/report.md
```

## How to Use the Viewer

The viewer is a static read-only app packaged with the CLI. It loads the generated JSON exports and provides:

- a filterable decision list
- a detail view with Decision Record sections
- grouped links by relationship type
- a traceability graph

Generate exports, build the static site artifact, and serve `_site/`:

```bash
PYTHONPATH=src python3 -m dt.cli report
PYTHONPATH=src python3 -m dt.cli build-site --root .
python3 -m http.server 8000 --directory _site
```

Open:

```text
http://localhost:8000/
```

## How Static Publishing Works

The repository can build a clean static site artifact for GitHub Pages:

```bash
PYTHONPATH=src python3 -m dt.cli build-site --root .
```

This command:

- runs `dt validate --all`
- stops if validation has failures
- preserves validation warnings in `_site/data/validation.txt`
- runs `dt report`
- copies packaged viewer assets into `_site/`
- copies generated JSON, `report.md`, `metrics.csv`, and `site-meta.json` into `_site/data/`
- generates `_site/report.html` as a printable executive summary and audit report over the generated data

The published viewer loads from `_site/data/` instead of `decisions/`, so the public site does not need to expose the whole repository.

The GitHub Actions workflow builds the site for pull requests without deploying. Pushes to `main` build the same artifact and deploy it to GitHub Pages.

## Practical Advice for New Contributors

- Read the existing tests and fixture outputs before changing behavior.
- Do not casually add fields, enums, or output columns.
- Do not change export formatting unless the behavior change is intentional and covered by tests.
- When in doubt, inspect the fixture decisions first. They are the best working examples.
- If behavior changes, update tests and only update golden outputs when the new behavior is intentional.

## Quick Start

If you want the shortest usable path:

1. Create a decision with `dt new` or `PYTHONPATH=src python3 -m dt.cli new`
2. Fill in the generated file under `decisions/`
3. Run `validate`
4. Run `report`
5. Inspect `reports/report.md` and the JSON exports

That is the core loop of the project.
