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

If `dt` is installed:

```bash
dt new --title "Adopt Transformer encoder as baseline model" --stage training --type model --owner ahmet
dt validate --all
dt report
```

If running directly from source:

```bash
PYTHONPATH=src python3 -m dt.cli new --title "Adopt Transformer encoder as baseline model" --stage training --type model --owner ahmet
PYTHONPATH=src python3 -m dt.cli validate --all
PYTHONPATH=src python3 -m dt.cli report
```

All commands accept `--root PATH`. If omitted, the CLI walks upward from the current directory to find `decisions/` or `.git`, so commands also work from repository subdirectories.

Use `--git-head` with `new` to add the current Git commit as a stable `git:commit:<sha>` link:

```bash
PYTHONPATH=src python3 -m dt.cli new --title "Record training implementation" --stage training --type generic --owner ahmet --git-head
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

The static viewer lives in [`viewer/`](viewer/). Generate exports, serve the repository root, and open `/viewer/`:

```bash
PYTHONPATH=src python3 -m dt.cli report
python3 -m http.server 8000
```

Then visit:

```text
http://localhost:8000/viewer/
```

Build the clean static site artifact for GitHub Pages:

```bash
PYTHONPATH=src python3 scripts/build_site.py --root .
```

This creates `_site/` with the viewer and generated data under `_site/data/`. The GitHub Actions workflow validates and builds this artifact for pull requests, and deploys it to GitHub Pages on pushes to `main`.

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

## Validation

Validation checks:

- required YAML fields
- enum correctness
- required headings
- empty sections
- template-specific required fields
- template-specific minimum links
- missing local Git commits for `git:commit:<sha>` refs, when validation runs inside a Git repository
- superseded cross-record consistency
- ref format validity

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
- [viewer/README.md](viewer/README.md): viewer usage notes
- [docs/](docs/): supporting notes linked from Decision Records
- [fixtures/decisions](fixtures/decisions): sample records used by tests

## New Here?

Start with:

1. [README.md](README.md)
2. [RUNBOOK.md](RUNBOOK.md)
3. the sample records in [`fixtures/decisions`](fixtures/decisions)

That is enough to understand how to create, validate, and report decisions in this repository.
