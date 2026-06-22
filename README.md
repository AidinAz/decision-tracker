# Decision Tracker

Decision Tracker is a deterministic CLI for recording ML workflow decisions as Markdown files, validating them against project rules, and generating exports for reporting and a read-only viewer.

It is built around a simple idea:

- decisions live in the repository as files
- links capture traceability to code, data, runs, docs, and issues
- reports and JSON exports are generated locally
- outputs are byte-stable for the same repo state

For the full guide, see [RUNBOOK.md](RUNBOOK.md).

## Purpose

This project helps teams document decisions such as:

- why a model architecture was chosen
- how evaluation was standardized
- what evidence supports a threshold change
- which newer decision superseded an older one

The goal is not workflow automation. The goal is lightweight, Git-native decision traceability.

## Core Workflow

1. Create a Decision Record in `decisions/`
2. Fill in the required YAML and Markdown sections
3. Validate the repository
4. Generate deterministic exports and reports

## Commands

Install from this repository:

```bash
pipx install git+https://github.com/AhmetIsk/decision-tracker.git
```

After a PyPI release, the intended short install command is:

```bash
pipx install decision-tracker
```

The installable package is named `decision-tracker`; the CLI command is `dt`.

The scaffolded GitHub Pages workflow created by `dt init` currently installs from the pinned GitHub release tag `v0.1.0`. After the package is published to PyPI, that workflow can be simplified to `pip install decision-tracker`.

If `dt` is installed:

```bash
dt init
dt new --title "Adopt Transformer encoder as baseline model" --stage training --type model --owner ahmet
dt validate --all
dt list
dt report
dt build-site
```

If running directly from source:

```bash
PYTHONPATH=src python3 -m dt.cli init
PYTHONPATH=src python3 -m dt.cli new --title "Adopt Transformer encoder as baseline model" --stage training --type model --owner ahmet
PYTHONPATH=src python3 -m dt.cli validate --all
PYTHONPATH=src python3 -m dt.cli list
PYTHONPATH=src python3 -m dt.cli report
PYTHONPATH=src python3 -m dt.cli build-site
```

All commands accept `--root PATH`. If omitted, the CLI walks upward from the current directory, preferring the nearest `decisions/` ancestor and then falling back to the nearest `.git` ancestor. Use `--root` in unusual nested layouts. Run `dt init` before `dt new`; `new` refuses to create records in an uninitialized directory.

Use `--git-head` with `new` to add the current Git commit as a stable `git:commit:<sha>` link:

```bash
PYTHONPATH=src python3 -m dt.cli new --title "Record training implementation" --stage training --type generic --owner ahmet --git-head
```

Use `dt list` for a quick terminal inventory:

```bash
dt list --status accepted
dt list --type model --format json
```

Use strict validation in CI when warnings should block a merge:

```bash
dt validate --all --strict
```

Use `dt doctor` to check whether the current repository is initialized correctly:

```bash
dt doctor
```

## Decision Types

Supported types:

- `generic`
- `model`
- `evaluation_protocol`

`model` records require `model_spec`.

`model_spec` may also include an optional `training_config` block for fine-tuning and hyperparameter decisions. When present, it records the tuning method, selected hyperparameters, and selection rule in machine-readable YAML.

`evaluation_protocol` records require `eval_spec`.

All records require these headings:

- `## Context`
- `## Decision`
- `## Rationale`
- `## Alternatives`
- `## Consequences`

## Generated Outputs

Running `report` writes:

- `decisions/index.json`
- `decisions/graph.json`
- `decisions/artifacts.json`
- `reports/metrics.csv`
- `reports/report.md`

These outputs are intended for evaluation, inspection, and the read-only viewer.

## Viewer

The static viewer is packaged with the CLI and emitted by `dt build-site`. Users do not edit or serve viewer source files directly.

```bash
PYTHONPATH=src python3 -m dt.cli report
PYTHONPATH=src python3 -m dt.cli build-site --root .
python3 -m http.server 8000 --directory _site
```

Then visit:

```text
http://localhost:8000/
```

This creates `_site/` with the viewer and generated data under `_site/data/`. The GitHub Actions workflow validates and builds this artifact for pull requests, and deploys it to GitHub Pages on pushes to `main`.

For safety, `build-site` refuses to replace an arbitrary non-empty output directory. Use the default `_site/` output or pass `--force` only when you intentionally want to replace a custom site output directory.

## Examples

Example decision refs:

- `git:commit:bb22cc3`
- `dvc:3f2c9a1`
- `mlflow:run:f3a0b0d1b2c34e`
- `path:docs/model-selection-notes.md`
- `decision:DR-0004`

Example use cases:

- record why a Transformer baseline was adopted
- capture a fixed evaluation split and dataset version
- propose a new threshold before evidence exists
- supersede an older rule with a better-structured decision

## Backfilling Existing Projects

Decision Tracker can also be added to an existing repository after important decisions already happened.

Recommended workflow:

```bash
dt init
dt discover --since 2024-01-01
dt backfill
dt validate --all
dt report
dt build-site
```

`dt discover` scans local Git commit messages and prints possible decision evidence. It is not automatic decision extraction, and it does not write files.

`dt backfill` guides historical reconstruction and creates a normal `proposed` Decision Record with a `reconstruction` block. Use `reconstruction.known_gaps` when evidence is incomplete. Commit history should be treated as evidence, not proof of the original rationale.

Backfilled records also include a review checklist. Unchecked checklist items produce a warning so reviewers can see what still needs confirmation.

Use normal validation while reconstruction is in progress; use `dt validate --strict` after TODOs and checklist items are completed or intentionally accepted by review.

Decision Records may optionally include review metadata:

```yaml
review:
  status: pending
  reviewed_by: []
  reviewed_date: "unknown"
  notes: ""
```

## Use In Another Repository

In another ML project:

```bash
pipx install git+https://github.com/AhmetIsk/decision-tracker.git
cd my-ml-project
dt init
dt new --title "Choose baseline model" --stage training --type model --owner alice --git-head
dt validate --all
dt report
dt build-site
```

`dt init` creates the minimal repository scaffold:

- `decisions/.gitkeep`
- `docs/README.md`
- `.gitignore` entries for generated Decision Tracker outputs
- `.github/workflows/pages.yml`

It does not copy this repository's example decisions into the target project.

## Validation

Validation checks:

- required YAML fields
- enum correctness
- required headings
- empty sections
- template-specific required fields
- template-specific minimum links
- missing local Git commits for `git:commit:<sha>` refs, when validation runs inside a Git repository
- unavailable Git commit checks, when a Git repository is detected but commit lookup cannot complete
- missing local files for `path:` refs, as warning-only evidence checks
- superseded cross-record consistency
- ref format validity

Warnings remain advisory by default. Use `dt validate --strict` or `dt validate --fail-on-warn` when warnings should fail CI.

Common failure codes include:

- `ID_FORMAT_INVALID`
- `TEMPLATE_FIELD_MISSING`
- `LINK_INVALID_FORMAT`
- `MIN_LINKS_NOT_MET`
- `SUPERSEDED_INCONSISTENT`

## Verification

Run tests:

```bash
python3 -m pytest -q
```

Validate decisions:

```bash
PYTHONPATH=src python3 -m dt.cli validate --all
```

Generate reports:

```bash
PYTHONPATH=src python3 -m dt.cli report
```

## Important Documents

- [RUNBOOK.md](RUNBOOK.md): detailed user guide
- [ARCHITECTURE.md](ARCHITECTURE.md): system architecture, command flow, data model, publishing flow, and backfill/discover diagrams
- [docs/user-scenarios.md](docs/user-scenarios.md): use cases and Mermaid diagrams
- [docs/](docs/): supporting notes linked from Decision Records
- [fixtures/decisions](fixtures/decisions): sample records used by tests

## New Here?

Start with:

1. [README.md](README.md)
2. [RUNBOOK.md](RUNBOOK.md)
3. the sample records in [`fixtures/decisions`](fixtures/decisions)

That is enough to understand how to create, validate, and report decisions in this repository.
