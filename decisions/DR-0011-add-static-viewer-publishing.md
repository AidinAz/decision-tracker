---
id: DR-0011
title: "Add static viewer publishing"
status: accepted
type: generic
stage: deployment
date: "2026-06-14"
owner: "ahmet"
stakeholders: ["ML engineer", "supervisor"]
template_version: "1.0"
links:
  - id: "L-0001"
    rel: supported_by
    artifact_kind: document
    ref: "path:viewer/README.md"
    label: "Viewer publishing notes"
    note: ""
  - id: "L-0002"
    rel: supported_by
    artifact_kind: document
    ref: "path:RUNBOOK.md"
    label: "Site build workflow"
    note: ""
---

## Context
The viewer is a static read-only interface over generated Decision Tracker exports.

Because the project is Git-native, the viewer should be publishable from repository state whenever Decision Records or viewer code change.

## Decision
Add a GitHub Actions-based publishing path for the static viewer.

Pull requests validate the repository, regenerate reports, and build a clean `_site/` artifact without deploying.

Pushes to `main` perform the same build and then deploy `_site/` to GitHub Pages.

## Rationale
Publishing the viewer from CI keeps the inspection interface synchronized with accepted repository history.

Using a clean `_site/` artifact avoids exposing unnecessary repository files and keeps the public site backend-free.

Warnings are captured but do not block publishing because warning-only checks such as missing local Git commits are advisory and may vary across clones.

## Alternatives
1) Publish the entire repository as a Pages site
2) Introduce Reflex or another backend-driven viewer
3) Deploy from every branch
4) Block deployment on warnings

## Consequences
- The viewer can be shared as a static GitHub Pages artifact.
- Validation failures block deployment.
- Validation warnings are preserved in the published artifact for inspection.
- The published viewer remains static and does not require runtime GitHub API calls.
