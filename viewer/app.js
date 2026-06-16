const state = {
  artifacts: new Map(),
  decisions: [],
  focusSelected: false,
  graph: { edges: [], nodes: [] },
  selectedId: null,
};

const config = {
  dataBase: window.DT_VIEWER_CONFIG?.dataBase || "../decisions",
  metaPath: window.DT_VIEWER_CONFIG?.metaPath || "",
  reportPath: window.DT_VIEWER_CONFIG?.reportPath || "../reports/report.md",
  validationPath: window.DT_VIEWER_CONFIG?.validationPath || "",
};

const els = {
  artifactSummary: document.querySelector("#summary-artifacts"),
  decisionList: document.querySelector("#decision-list"),
  detailContent: document.querySelector("#detail-content"),
  detailEmpty: document.querySelector("#detail-empty"),
  focusSelected: document.querySelector("#focus-selected"),
  graphCanvas: document.querySelector("#graph-canvas"),
  graphFocus: document.querySelector("#graph-focus"),
  linkSummary: document.querySelector("#summary-links"),
  reportLink: document.querySelector("#report-link"),
  search: document.querySelector("#search"),
  siteCommit: document.querySelector("#site-commit"),
  stageFilter: document.querySelector("#stage-filter"),
  statusFilter: document.querySelector("#status-filter"),
  totalSummary: document.querySelector("#summary-total"),
  traceTable: document.querySelector("#trace-table"),
  typeFilter: document.querySelector("#type-filter"),
  validationMenu: document.querySelector("#validation-menu"),
  validationPopover: document.querySelector("#validation-popover"),
  validationRawLink: document.querySelector("#validation-raw-link"),
  validationToggle: document.querySelector("#validation-toggle"),
  validationWarnings: document.querySelector("#validation-warnings"),
};

const sectionOrder = ["Context", "Decision", "Rationale", "Alternatives", "Consequences"];
const relOrder = ["implements", "evaluated_by", "supported_by", "supersedes"];
const relClass = {
  evaluated_by: "rel-evaluated_by",
  implements: "rel-implements",
  supported_by: "rel-supported_by",
  supersedes: "rel-supersedes",
};

async function loadJson(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`${path} returned ${response.status}`);
  }
  return response.json();
}

async function loadOptionalJson(path) {
  if (!path) return null;
  try {
    return await loadJson(path);
  } catch {
    return null;
  }
}

async function loadOptionalText(path) {
  if (!path) return "";
  try {
    const response = await fetch(path);
    if (!response.ok) return "";
    return response.text();
  } catch {
    return "";
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function dataPath(name) {
  return `${config.dataBase.replace(/\/$/, "")}/${name}`;
}

function uniqueSorted(values) {
  return [...new Set(values.filter(Boolean))].sort((a, b) => a.localeCompare(b));
}

function populateFilter(select, values, label) {
  select.innerHTML = [
    `<option value="">All ${label}</option>`,
    ...values.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`),
  ].join("");
}

function decisionNodeId(decision) {
  return `decision:${decision.id}`;
}

function linksForDecision(decision) {
  if (Array.isArray(decision.links)) {
    return decision.links;
  }
  return state.graph.edges
    .filter((edge) => edge.source === decisionNodeId(decision))
    .map((edge) => ({
      artifact_kind: edge.artifact_kind,
      label: edge.label,
      ref: state.artifacts.get(edge.target)?.ref || edge.target,
      rel: edge.rel,
      target: edge.target,
    }));
}

function filteredDecisions() {
  const query = els.search.value.trim().toLowerCase();
  const stage = els.stageFilter.value;
  const type = els.typeFilter.value;
  const status = els.statusFilter.value;

  return state.decisions.filter((decision) => {
    const sectionText = Object.values(decision.sections || {}).join(" ").toLowerCase();
    const linkText = linksForDecision(decision)
      .map((link) => `${link.label || ""} ${link.ref || ""} ${link.rel || ""} ${link.artifact_kind || ""}`)
      .join(" ")
      .toLowerCase();
    const matchesQuery =
      !query ||
      decision.id.toLowerCase().includes(query) ||
      decision.title.toLowerCase().includes(query) ||
      decision.owner.toLowerCase().includes(query) ||
      sectionText.includes(query) ||
      linkText.includes(query);
    return (
      matchesQuery &&
      (!stage || decision.stage === stage) &&
      (!type || decision.type === type) &&
      (!status || decision.status === status)
    );
  });
}

function renderList() {
  const decisions = filteredDecisions();
  if (!decisions.length) {
    els.decisionList.innerHTML = `<div class="empty">No matching decisions.</div>`;
    return;
  }

  els.decisionList.innerHTML = decisions
    .map((decision) => {
      const active = state.selectedId === decision.id ? " is-active" : "";
      return `
        <button class="decision-button${active}" data-id="${escapeHtml(decision.id)}" type="button">
          <span class="decision-title">${escapeHtml(decision.id)} · ${escapeHtml(decision.title)}</span>
          <span class="meta-row">
            <span class="pill status-${escapeHtml(decision.status)}">${escapeHtml(decision.status)}</span>
            <span class="pill">${escapeHtml(decision.type)}</span>
            <span class="pill">${escapeHtml(decision.stage)}</span>
            <span class="pill">${decision.link_count} links</span>
          </span>
          <span class="score-row">
            <span class="score">C ${decision.scores.completeness}</span>
            <span class="score">N ${decision.scores.connectedness}</span>
            <span class="score">I ${decision.scores.inclusiveness}</span>
            <span class="score">T ${decision.scores.traceability}</span>
          </span>
        </button>
      `;
    })
    .join("");
}

function renderDetail(decision) {
  if (!decision) {
    els.detailContent.hidden = true;
    els.detailEmpty.hidden = false;
    return;
  }

  const links = linksForDecision(decision);
  const groupedLinks = relOrder
    .map((rel) => [rel, links.filter((link) => link.rel === rel)])
    .filter(([, items]) => items.length);

  els.detailEmpty.hidden = true;
  els.detailContent.hidden = false;
  els.detailContent.innerHTML = `
    <header class="detail-header">
      <h2>${escapeHtml(decision.id)} · ${escapeHtml(decision.title)}</h2>
      <div class="meta-row">
        <span class="pill status-${escapeHtml(decision.status)}">${escapeHtml(decision.status)}</span>
        <span class="pill">${escapeHtml(decision.type)}</span>
        <span class="pill">${escapeHtml(decision.stage)}</span>
        <span class="pill">${escapeHtml(decision.date)}</span>
        <span class="pill">owner: ${escapeHtml(decision.owner)}</span>
      </div>
      <div class="meta-row">
        ${decision.stakeholders.map((item) => `<span class="pill">${escapeHtml(item)}</span>`).join("")}
      </div>
    </header>
    <div class="section-stack">
      ${sectionOrder
        .map(
          (heading) => `
            <section class="dr-section">
              <h3>${escapeHtml(heading)}</h3>
              ${renderSectionBody(decision.sections?.[heading] || "")}
            </section>
          `,
        )
        .join("")}
    </div>
    <div class="link-groups">
      <h3>Links</h3>
      ${
        groupedLinks.length
          ? groupedLinks
              .map(
                ([rel, items]) => `
                  <section class="link-group">
                    <h3>${escapeHtml(rel)}</h3>
                    <div class="link-items">
                      ${items.map(renderLinkItem).join("")}
                    </div>
                  </section>
                `,
              )
              .join("")
          : `<p>No links recorded.</p>`
      }
    </div>
  `;
}

function renderSectionBody(value) {
  const lines = String(value || "").split("\n");
  const chunks = [];
  let listType = null;
  let listItems = [];
  let paragraph = [];

  function flushList() {
    if (!listItems.length) return;
    const tag = listType === "ol" ? "ol" : "ul";
    chunks.push(`<${tag}>${listItems.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}</${tag}>`);
    listItems = [];
    listType = null;
  }

  function flushParagraph() {
    const text = paragraph.join(" ").trim();
    if (text) {
      chunks.push(`<p>${escapeHtml(text)}</p>`);
    }
    paragraph = [];
  }

  lines.forEach((line) => {
    const trimmed = line.trim();
    const bullet = trimmed.match(/^[-*]\s+(.+)$/);
    const numbered = trimmed.match(/^\d+[.)]\s+(.+)$/);
    if (!trimmed) {
      flushParagraph();
      flushList();
      return;
    }
    if (bullet || numbered) {
      flushParagraph();
      const nextListType = numbered ? "ol" : "ul";
      if (listType && listType !== nextListType) {
        flushList();
      }
      listType = nextListType;
      listItems.push((bullet || numbered)[1]);
      return;
    }
    flushList();
    paragraph.push(trimmed);
  });

  flushParagraph();
  flushList();
  return chunks.length ? chunks.join("") : "<p></p>";
}

function renderLinkItem(link) {
  const artifact = state.artifacts.get(link.target);
  const ref = artifact?.ref || link.ref || link.target;
  const kind = artifact?.artifact_kind || link.artifact_kind || "decision";
  return `
    <div class="link-item" data-kind="${escapeHtml(kind)}">
      <div class="link-label">${escapeHtml(link.label || ref)}</div>
      <div class="link-meta">
        <span class="pill">${escapeHtml(kind)}</span>
        <span class="pill">${escapeHtml(link.rel)}</span>
      </div>
      <p class="ref">${escapeHtml(ref)}</p>
    </div>
  `;
}

function activeGraphIds(activeNodeId, activeTargets) {
  if (!state.focusSelected || !activeNodeId) {
    return null;
  }
  return new Set([activeNodeId, ...activeTargets]);
}

function renderTraceTable(decision) {
  if (!decision) {
    els.traceTable.innerHTML = `<div class="empty-inline">Select a decision to inspect its trace links.</div>`;
    return;
  }

  const links = linksForDecision(decision);
  if (!links.length) {
    els.traceTable.innerHTML = `<div class="empty-inline">No trace links recorded for ${escapeHtml(decision.id)}.</div>`;
    return;
  }

  els.traceTable.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Relationship</th>
          <th>Kind</th>
          <th>Label</th>
          <th>Reference</th>
        </tr>
      </thead>
      <tbody>
        ${links
          .map((link) => {
            const artifact = state.artifacts.get(link.target);
            const ref = artifact?.ref || link.ref || link.target;
            const kind = artifact?.artifact_kind || link.artifact_kind || "decision";
            return `
              <tr>
                <td><span class="rel-pill ${relClass[link.rel] || ""}">${escapeHtml(link.rel)}</span></td>
                <td>${escapeHtml(kind)}</td>
                <td>${escapeHtml(link.label || ref)}</td>
                <td><code>${escapeHtml(ref)}</code></td>
              </tr>
            `;
          })
          .join("")}
      </tbody>
    </table>
  `;
}

function renderValidationWarnings(validationText) {
  const warnings = validationText.split("\n").filter((line) => line.startsWith("WARN "));
  if (!warnings.length) {
    els.validationToggle.textContent = "Validation OK";
    els.validationWarnings.innerHTML = `<div class="empty-inline">No validation warnings.</div>`;
    return;
  }

  els.validationToggle.textContent = `Validation (${warnings.length} warnings)`;
  els.validationWarnings.innerHTML = warnings
    .map((warning) => `<div class="warning-line">${escapeHtml(warning)}</div>`)
    .join("");
}

function renderGraph() {
  const width = 1120;
  const decisionNodes = state.graph.nodes.filter((node) => node.kind === "decision");
  const artifactNodes = state.graph.nodes.filter((node) => node.kind === "artifact");
  const rowGap = 62;
  const artifactGap = 54;
  const height = Math.max(430, 72 + Math.max(decisionNodes.length * rowGap, artifactNodes.length * artifactGap));
  const positions = new Map();

  decisionNodes.forEach((node, index) => {
    positions.set(node.id, { x: 70, y: 34 + index * rowGap });
  });
  artifactNodes.forEach((node, index) => {
    positions.set(node.id, { x: 720, y: 26 + index * artifactGap });
  });

  const activeNodeId = state.selectedId ? `decision:${state.selectedId}` : "";
  const activeTargets = new Set(
    state.graph.edges.filter((edge) => edge.source === activeNodeId).map((edge) => edge.target),
  );
  const visibleIds = activeGraphIds(activeNodeId, activeTargets);

  const edgeLabelCounts = new Map();
  const edges = state.graph.edges
    .map((edge, index) => {
      if (visibleIds && (!visibleIds.has(edge.source) || !visibleIds.has(edge.target))) {
        return "";
      }
      const source = positions.get(edge.source);
      const target = positions.get(edge.target);
      if (!source || !target) return "";
      const active = edge.source === activeNodeId || activeTargets.has(edge.target);
      const relName = relClass[edge.rel] || "";
      const labelKey = `${edge.source}->${edge.target}`;
      const labelIndex = edgeLabelCounts.get(labelKey) || 0;
      edgeLabelCounts.set(labelKey, labelIndex + 1);
      const labelOffset = ((index % 5) - 2) * 12 + labelIndex * 16;
      const labelX = (source.x + target.x) / 2 + 82;
      const labelY = (source.y + target.y) / 2 + 13 + labelOffset;
      return `
        <path class="edge ${relName}" d="M ${source.x + 260} ${source.y + 18} C ${source.x + 420} ${source.y + 18}, ${target.x - 160} ${target.y + 18}, ${target.x} ${target.y + 18}" opacity="${active ? "1" : "0.16"}">
          <title>${escapeHtml(edge.rel)} · ${escapeHtml(edge.label || edge.target)}</title>
        </path>
        <text class="edge-label ${active ? "is-visible" : ""}" x="${labelX}" y="${labelY}">${escapeHtml(edge.rel)}</text>
      `;
    })
    .join("");

  const nodes = state.graph.nodes
    .map((node) => {
      const position = positions.get(node.id);
      if (!position) return "";
      if (visibleIds && !visibleIds.has(node.id)) return "";
      const isActive = node.id === activeNodeId || activeTargets.has(node.id);
      const nodeClass = `node is-${node.kind}${isActive ? " is-active" : ""}`;
      const label = node.label.length > 38 ? `${node.label.slice(0, 35)}...` : node.label;
      const decisionId = node.kind === "decision" ? node.id.replace("decision:", "") : "";
      const clickAttrs = decisionId
        ? `tabindex="0" role="button" data-decision-id="${escapeHtml(decisionId)}"`
        : "";
      return `
        <g class="${nodeClass}" ${clickAttrs} transform="translate(${position.x}, ${position.y})">
          <title>${escapeHtml(node.label)}</title>
          <rect width="300" height="36" rx="6"></rect>
          <text x="12" y="23">${escapeHtml(label)}</text>
        </g>
      `;
    })
    .join("");

  els.graphCanvas.innerHTML = `
    <svg viewBox="0 0 ${width} ${height}" style="height: ${height}px" role="img" aria-label="Decision traceability graph">
      ${edges}
      ${nodes}
    </svg>
  `;
  els.graphFocus.textContent = state.selectedId
    ? `${state.focusSelected ? "Showing only" : "Focused on"} decision:${state.selectedId}`
    : "All decision and artifact links";
}

function selectDecision(id) {
  state.selectedId = id;
  const decision = state.decisions.find((item) => item.id === id);
  renderList();
  renderDetail(decision);
  renderGraph();
  renderTraceTable(decision);
}

function bindEvents() {
  [els.search, els.stageFilter, els.typeFilter, els.statusFilter].forEach((control) => {
    control.addEventListener("input", renderList);
  });

  els.focusSelected.addEventListener("change", () => {
    state.focusSelected = els.focusSelected.checked;
    renderGraph();
  });

  els.validationToggle.addEventListener("click", () => {
    const isOpen = !els.validationPopover.hidden;
    els.validationPopover.hidden = isOpen;
    els.validationToggle.setAttribute("aria-expanded", String(!isOpen));
  });

  document.addEventListener("click", (event) => {
    if (!els.validationMenu.hidden && !els.validationMenu.contains(event.target)) {
      els.validationPopover.hidden = true;
      els.validationToggle.setAttribute("aria-expanded", "false");
    }
  });

  els.decisionList.addEventListener("click", (event) => {
    const button = event.target.closest(".decision-button");
    if (!button) return;
    selectDecision(button.dataset.id);
  });

  els.graphCanvas.addEventListener("click", (event) => {
    const node = event.target.closest("[data-decision-id]");
    if (!node) return;
    selectDecision(node.dataset.decisionId);
  });

  els.graphCanvas.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    const node = event.target.closest("[data-decision-id]");
    if (!node) return;
    event.preventDefault();
    selectDecision(node.dataset.decisionId);
  });
}

async function init() {
  try {
    const [decisions, graph, artifacts] = await Promise.all([
      loadJson(dataPath("index.json")),
      loadJson(dataPath("graph.json")),
      loadJson(dataPath("artifacts.json")),
    ]);

    state.decisions = decisions;
    state.graph = graph;
    state.artifacts = new Map(artifacts.map((artifact) => [artifact.id, artifact]));

    if (config.reportPath) {
      els.reportLink.href = config.reportPath;
      els.reportLink.hidden = false;
    }
    if (config.validationPath) {
      els.validationRawLink.href = config.validationPath;
      els.validationMenu.hidden = false;
      const validationText = await loadOptionalText(config.validationPath);
      renderValidationWarnings(validationText);
    }

    const meta = await loadOptionalJson(config.metaPath);
    if (meta?.generated_from_commit) {
      els.siteCommit.textContent = `commit ${String(meta.generated_from_commit).slice(0, 7)}`;
      els.siteCommit.hidden = false;
    }

    populateFilter(els.stageFilter, uniqueSorted(decisions.map((decision) => decision.stage)), "stages");
    populateFilter(els.typeFilter, uniqueSorted(decisions.map((decision) => decision.type)), "types");
    populateFilter(els.statusFilter, uniqueSorted(decisions.map((decision) => decision.status)), "statuses");

    els.totalSummary.textContent = `${decisions.length} decisions`;
    els.linkSummary.textContent = `${graph.edges.length} links`;
    els.artifactSummary.textContent = `${artifacts.length} artifacts`;

    bindEvents();
    renderList();
    renderGraph();
    renderTraceTable(null);
    if (decisions.length) {
      selectDecision(decisions[0].id);
    }
  } catch (error) {
    document.body.insertAdjacentHTML(
      "afterbegin",
      `<div class="load-error">Unable to load viewer exports: ${escapeHtml(error.message)}</div>`,
    );
  }
}

init();
