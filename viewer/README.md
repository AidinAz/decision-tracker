# Viewer

This is a static read-only viewer for generated Decision Tracker exports.

## Inputs
- decisions/index.json
- decisions/graph.json
- decisions/artifacts.json

When built for GitHub Pages with `dt build-site`, the same viewer reads from:

- data/index.json
- data/graph.json
- data/artifacts.json
- data/report.md
- data/metrics.csv
- data/validation.txt
- data/site-meta.json

The published site also includes `report.html`, a printable audit report rendered from the generated data files. The raw Markdown, CSV, JSON, and validation log remain linked from the report.

## Screens
- List: filter by stage/type/status
- Detail: render sections and group links by relationship type
- Graph: render nodes/edges with labels

## Run

Generate exports first:

```bash
PYTHONPATH=src python3 -m dt.cli report
```

Serve the repository root:

```bash
python3 -m http.server 8000
```

Open:

```text
http://localhost:8000/viewer/
```

The viewer uses browser `fetch`, so serving over HTTP is more reliable than opening `viewer/index.html` directly from the filesystem.

## Build Published Site

```bash
PYTHONPATH=src python3 -m dt.cli build-site --root .
python3 -m http.server 8000 --directory _site
```

Open:

```text
http://localhost:8000/
```

## Forbidden (MVP)
- editing
- saving
- authentication/user accounts
- any network calls to GitHub/MLflow/etc.
