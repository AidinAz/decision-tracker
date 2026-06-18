# Architecture

This file describes the current Decision Tracker architecture after adding package installation, static viewer publishing, Git-aware validation, and historical backfill support.

## Existing Diagram Review

The original diagrams still apply at a high level:

- developers write Decision Records under `decisions/`
- the `dt` CLI validates records and generates exports
- the viewer loads generated JSON artifacts

They were incomplete for the current implementation because they did not include:

- `dt init`
- `dt discover`
- `dt backfill`
- `dt build-site`
- packaged viewer/workflow assets
- GitHub Pages deployment
- reconstruction metadata for historical decisions
- Git checks for `git:commit:<sha>` references

## System Context

```mermaid
flowchart LR
  User["User / ML engineer"] -->|installs| Package["decision-tracker package"]
  Package -->|provides| CLI["dt CLI"]
  Package -->|ships| ViewerAssets["packaged viewer assets"]
  Package -->|ships| WorkflowTemplate["GitHub Pages workflow template"]

  CLI -->|creates/edits| DR["Decision Records<br/>decisions/DR-XXXX-*.md"]
  CLI -->|reads local history| Git["Local Git repository"]
  CLI -->|writes| Exports["Generated exports<br/>index.json<br/>graph.json<br/>artifacts.json<br/>metrics.csv<br/>report.md"]
  CLI -->|builds| Site["_site static viewer"]

  Site -->|contains| Viewer["Read-only browser viewer"]
  Site -->|contains| SiteData["data/*.json, report.html, validation.txt"]
  GitHubActions["GitHub Actions"] -->|runs validate/report/build-site| CLI
  GitHubActions -->|publishes| Pages["GitHub Pages"]
```

## Command Map

```mermaid
flowchart TB
  Start["Existing or new ML repo"] --> Init["dt init"]
  Init --> Scaffold["Create decisions/, docs/, .gitignore, Pages workflow"]

  Scaffold --> New["dt new"]
  Scaffold --> Discover["dt discover"]
  Scaffold --> Backfill["dt backfill"]

  New --> DR["Proposed Decision Record"]
  Discover --> Evidence["Printed candidate evidence only"]
  Evidence --> Backfill
  Backfill --> BackfilledDR["Proposed backfilled Decision Record<br/>with reconstruction metadata"]

  DR --> Validate["dt validate --all"]
  BackfilledDR --> Validate
  Validate --> Report["dt report"]
  Report --> BuildSite["dt build-site"]
  BuildSite --> Viewer["_site viewer / GitHub Pages"]
```

## Data Model

```mermaid
erDiagram
  DECISION_RECORD ||--o{ LINK : contains
  DECISION_RECORD ||--o| MODEL_SPEC : "when type=model"
  DECISION_RECORD ||--o| EVAL_SPEC : "when type=evaluation_protocol"
  DECISION_RECORD ||--o| RECONSTRUCTION : "when backfilled"
  LINK }o--|| ARTIFACT_OR_DECISION : references

  DECISION_RECORD {
    string id
    string title
    string status
    string type
    string stage
    string date
    string owner
    string template_version
  }

  LINK {
    string id
    string rel
    string artifact_kind
    string ref
    string label
  }

  MODEL_SPEC {
    string objective
    string model_family
    string input
    string output
    string primary_metric
    string acceptance_criteria
  }

  EVAL_SPEC {
    string dataset_ref
    string protocol
    list metrics
    object baseline
  }

  RECONSTRUCTION {
    string mode
    string original_decision_date
    string evidence_confidence
    list evidence_sources
    list known_gaps
  }

  ARTIFACT_OR_DECISION {
    string ref
    string kind
  }
```

## Decision Lifecycle

```mermaid
stateDiagram-v2
  [*] --> Proposed: dt new or dt backfill
  Proposed --> Accepted: human review + evidence complete
  Proposed --> Rejected: decision not adopted
  Accepted --> Superseded: newer DR links rel=supersedes
  Accepted --> Deprecated: no longer recommended
  Superseded --> [*]
  Rejected --> [*]
  Deprecated --> [*]
```

## Forward Capture Sequence

```mermaid
sequenceDiagram
  participant U as User
  participant CLI as dt CLI
  participant FS as Filesystem
  participant V as Validator

  U->>CLI: dt init
  CLI->>FS: create decisions/, docs/, workflow, .gitignore
  CLI-->>U: Created scaffold files

  U->>CLI: dt new --title ... --stage ... --type ...
  CLI->>FS: scan existing DR IDs
  CLI->>FS: write DR-XXXX-title.md
  CLI-->>U: Created decisions/DR-XXXX-title.md

  U->>CLI: dt validate --all
  CLI->>FS: read decisions/DR-*.md
  CLI->>V: validate YAML, headings, templates, links
  V-->>CLI: OK / FAIL / WARN
  CLI-->>U: validation output
```

## Historical Backfill Sequence

```mermaid
sequenceDiagram
  participant U as User
  participant CLI as dt CLI
  participant Git as Local Git
  participant FS as Filesystem
  participant V as Validator

  U->>CLI: dt discover --since 2024-01-01
  CLI->>Git: git log --pretty=format:%H %s
  CLI->>CLI: keyword match + infer stage/type
  CLI-->>U: candidate evidence list

  U->>CLI: dt backfill
  CLI->>U: prompt for title, type, stage, evidence, gaps
  U-->>CLI: confirmed reconstruction data
  CLI->>CLI: map evidence refs to typed links
  CLI->>FS: write proposed DR with reconstruction block
  CLI-->>U: Created decisions/DR-XXXX-title.md

  U->>CLI: dt validate --all
  CLI->>V: validate DR and reconstruction metadata
  V-->>CLI: OK / FAIL / WARN
  CLI-->>U: validation output
```

## Report And Viewer Build Sequence

```mermaid
sequenceDiagram
  participant U as User
  participant CLI as dt CLI
  participant FS as Filesystem
  participant Viewer as Viewer Assets
  participant Site as _site

  U->>CLI: dt report
  CLI->>FS: read decisions/DR-*.md
  CLI->>CLI: pre-validate all records
  CLI->>CLI: compute metrics, graph, artifact index
  CLI->>FS: write decisions/*.json and reports/*
  CLI-->>U: Generated reports and exports

  U->>CLI: dt build-site
  CLI->>Site: preflight output safety and writability
  CLI->>CLI: validate + report
  CLI->>Viewer: load packaged app.js/styles.css/index.html
  CLI->>Site: write static viewer and data/
  CLI-->>U: Built static viewer site at _site
```

`dt build-site` intentionally runs validation and report generation before copying viewer assets, because the published site should reflect the same validated exports as local reporting. Before those steps, it checks that the requested site output path is safe and writable. It refuses to replace the project root, ancestors of the project root, unknown non-empty directories, and symlinked output paths unless `--force` is explicitly used.

## GitHub Pages Publishing Sequence

```mermaid
sequenceDiagram
  participant Dev as Developer
  participant GH as GitHub
  participant Actions as GitHub Actions
  participant CLI as dt CLI
  participant Pages as GitHub Pages

  Dev->>GH: push to main
  GH->>Actions: trigger Publish viewer workflow
  Actions->>CLI: dt validate --all
  Actions->>CLI: dt report
  Actions->>CLI: dt build-site --root .
  CLI-->>Actions: _site artifact
  Actions->>Pages: deploy _site
  Pages-->>Dev: published read-only viewer
```

## Backfill Trust Boundary

```mermaid
flowchart LR
  CommitHistory["Commit history"] -->|weak signal| Discover["dt discover"]
  Docs["Docs / notes"] -->|manual evidence refs| Backfill["dt backfill"]
  Issues["Issues / PR refs"] -->|manual evidence refs| Backfill
  Discover -->|suggestions only| Human["Human review"]
  Human -->|confirms context, rationale, gaps| Backfill
  Backfill --> Proposed["Proposed backfilled DR"]
  Proposed -->|validate + review| Accepted["Accepted DR"]

  CommitHistory -. "not proof of rationale" .-> Human
```

## Generated Artifacts

```mermaid
flowchart TB
  DR["decisions/DR-*.md"] --> Report["dt report"]
  Report --> Index["decisions/index.json<br/>viewer list/detail data"]
  Report --> Graph["decisions/graph.json<br/>traceability graph"]
  Report --> Artifacts["decisions/artifacts.json<br/>artifact lookup"]
  Report --> Metrics["reports/metrics.csv<br/>scoring and smells"]
  Report --> Markdown["reports/report.md<br/>audit summary"]

  Index --> BuildSite["dt build-site"]
  Graph --> BuildSite
  Artifacts --> BuildSite
  Metrics --> BuildSite
  Markdown --> BuildSite
  BuildSite --> Static["_site/"]
```

`_site/` includes a non-dot marker file named `__DT_SITE__`. The marker lets later builds recognize the directory as generated and safe to replace without publishing a hidden dotfile through GitHub Pages.
