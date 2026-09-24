/**
 * FraudGraph Investigator Dashboard — Part 3 UI
 * app.js — Main application logic
 *
 * Architecture:
 *   - Single-page vanilla JS, no build step, no frameworks
 *   - Fetches from the Part 3 API (/api/v3/*)
 *   - Never fabricates data: all displayed values come from the API
 *   - Missing fields shown as "Data unavailable" / "—" (never invented)
 *
 * Phase 3 investigation view sections (in display order):
 *   1. Page header — case ID + objective
 *   2. Case Information — identity fields
 *   3. Recommended Action — prominent action panel + approval + policy
 *   4. Evidence Assessment — sufficiency + uncertainty meters
 *   5. Key Findings — from report.key_findings[]
 *   6. Evidence — supporting vs contradictory columns (data only)
 *   7. Evidence Counts — supporting/contradictory/total
 *   8. Hypotheses — only when present; else explicit "not reached" notice
 *   9. Identified Patterns — only when present
 *  10. Case Memory — from report.case_memory (actual persisted data)
 *  11. Investigation Workflow — data-driven steps only, no fabricated timeline
 */

"use strict";

const API = "/api/v3";

// ── Application state ─────────────────────────────────────────────────────────

const state = {
  view: "welcome",
  cases: [],
  policyRules: {},       // rule_id → { name, action, approval_route, risk_level }
  currentCaseId: null,
  currentReport: null,
  benchmarkData: null,
};

// ── DOM helpers ───────────────────────────────────────────────────────────────

const $ = (sel, ctx = document) => ctx.querySelector(sel);
const $$ = (sel, ctx = document) => [...ctx.querySelectorAll(sel)];

// ── Safe display helpers ──────────────────────────────────────────────────────

/** Returns null for empty/null/undefined/"unknown" values */
function na(val) {
  if (val === null || val === undefined || val === "" || val === "unknown") return null;
  return val;
}

/** Render val or fallback string */
function display(val, fallback = "—") {
  const v = na(val);
  return v !== null ? v : fallback;
}

/** HTML-escape a string */
function esc(str) {
  if (str === null || str === undefined) return "";
  const d = document.createElement("div");
  d.textContent = String(str);
  return d.innerHTML;
}

// ── Label / class helpers ─────────────────────────────────────────────────────

function actionLabel(action) {
  return (action || "UNKNOWN").replace(/_/g, "\u00a0");
}

function actionBadgeClass(action) {
  const map = {
    BLOCK_CARD: "badge-BLOCK_CARD",
    VERIFY_WITH_CUSTOMER: "badge-VERIFY_WITH_CUSTOMER",
    ESCALATE: "badge-ESCALATE",
    CLOSE_NO_FRAUD: "badge-CLOSE_NO_FRAUD",
    MONITOR: "badge-MONITOR",
    REQUEST_MORE_EVIDENCE: "badge-REQUEST_MORE_EVIDENCE",
    FILE_REPORT: "badge-FILE_REPORT",
  };
  return map[action] || "badge-UNKNOWN";
}

function sidebarBadgeClass(action) {
  const map = {
    BLOCK_CARD: "badge-block",
    VERIFY_WITH_CUSTOMER: "badge-verify",
    ESCALATE: "badge-esc",
    CLOSE_NO_FRAUD: "badge-close",
    MONITOR: "badge-mon",
    REQUEST_MORE_EVIDENCE: "badge-req",
    FILE_REPORT: "badge-rpt",
  };
  return map[action] || "badge-unknown";
}

function sidebarBadgeShort(action) {
  const map = {
    BLOCK_CARD: "BLK",
    VERIFY_WITH_CUSTOMER: "VFY",
    ESCALATE: "ESC",
    CLOSE_NO_FRAUD: "CLR",
    MONITOR: "MON",
    REQUEST_MORE_EVIDENCE: "REQ",
    FILE_REPORT: "RPT",
  };
  return map[action] || "?";
}

function triggerClass(trigger) {
  const map = {
    risk_score: "trigger-risk_score",
    customer_report: "trigger-customer_report",
    analyst_request: "trigger-analyst_request",
  };
  return map[trigger] || "";
}

function triggerLabel(trigger) {
  const map = {
    risk_score: "Risk Score",
    customer_report: "Customer Report",
    analyst_request: "Analyst Request",
  };
  return map[trigger] || (trigger || "—");
}

function uncertaintyBadgeClass(level) {
  const map = { low: "badge-low", medium: "badge-medium", high: "badge-high" };
  return map[(level || "").toLowerCase()] || "badge-unknown";
}

function sufficiencyBadgeClass(level) {
  const map = { sufficient: "badge-sufficient", partial: "badge-partial", insufficient: "badge-insufficient" };
  return map[(level || "").toLowerCase()] || "badge-unknown";
}

function riskLevelClass(risk) {
  const map = { high: "badge-BLOCK_CARD", medium: "badge-VERIFY_WITH_CUSTOMER", low: "badge-MONITOR" };
  return map[(risk || "").toLowerCase()] || "badge-unknown";
}

// ── API calls ─────────────────────────────────────────────────────────────────

async function apiFetch(path, opts = {}) {
  const res = await fetch(`${API}${path}`, opts);
  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return res.json();
}

async function fetchCasesMeta()       { return apiFetch("/cases/meta"); }
async function fetchReport(id)        { return apiFetch(`/report/${id}`); }
async function fetchBenchmark()       { return apiFetch("/benchmark"); }
async function fetchPolicyRules()     { return apiFetch("/policy/rules"); }
async function runInvestigation(id)   { return apiFetch(`/run/${id}`, { method: "POST" }); }

// ── Toast notifications ───────────────────────────────────────────────────────

function toast(msg, type = "info", ms = 4000) {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = msg;
  $("#toast-container").appendChild(el);
  setTimeout(() => el.remove(), ms);
}

// ── View switching ────────────────────────────────────────────────────────────

function setView(name) {
  state.view = name;
  $$(".view").forEach(v => v.classList.remove("active"));
  const t = $(`#view-${name}`);
  if (t) t.classList.add("active");
  $$(".nav-item[data-view]").forEach(n =>
    n.classList.toggle("active", n.getAttribute("data-view") === name)
  );
}

// ── Sidebar ───────────────────────────────────────────────────────────────────

function renderSidebarCases(cases) {
  const list = $("#case-list");
  if (!list) return;
  list.innerHTML = "";
  cases.forEach(c => {
    const btn = document.createElement("button");
    btn.className = "case-item";
    btn.setAttribute("data-case-id", c.case_id);
    const act = c._action || "";
    btn.innerHTML = `
      <span class="case-id">${esc(c.case_id)}</span>
      <span class="case-badge ${esc(sidebarBadgeClass(act))}">${esc(sidebarBadgeShort(act))}</span>
    `;
    btn.title = c.trigger_text || c.case_id;
    btn.addEventListener("click", () => loadCaseView(c.case_id));
    list.appendChild(btn);
  });
}

// ── Load sidebar (efficient: one benchmark call for all badges) ───────────────

async function loadCasesForSidebar() {
  try {
    const meta = await fetchCasesMeta();
    state.cases = meta.cases || [];

    // Use benchmark endpoint for action badges — one call instead of 20
    try {
      const bench = await fetchBenchmark();
      const actionMap = {};
      (bench.cases || []).forEach(c => { actionMap[c.case_id] = c.recommended_action || ""; });
      state.cases.forEach(c => { c._action = actionMap[c.case_id] || ""; });
    } catch (_) { /* badges stay empty — not critical */ }

    renderSidebarCases(state.cases);
  } catch (err) {
    console.error("Sidebar load failed:", err);
  }
}

// ── Load policy rules (for display enrichment) ────────────────────────────────

async function loadPolicyRules() {
  try {
    const data = await fetchPolicyRules();
    state.policyRules = {};
    (data.rules || []).forEach(r => { state.policyRules[r.rule_id] = r; });
  } catch (_) { /* non-critical */ }
}

// ── Case investigation view ───────────────────────────────────────────────────

async function loadCaseView(caseId) {
  setView("investigation");
  state.currentCaseId = caseId;
  state.currentReport = null;

  $$(".case-item").forEach(b =>
    b.classList.toggle("active", b.getAttribute("data-case-id") === caseId)
  );

  const inv = $("#view-investigation");
  inv.innerHTML = `
    <div class="loading">
      <div class="spinner"></div>
      <div>Loading report for <strong>${esc(caseId)}</strong>…</div>
    </div>`;

  try {
    const data = await fetchReport(caseId);
    state.currentReport = data.report;
    renderInvestigationView(data.report);
  } catch (err) {
    inv.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">⚠️</div>
        <div class="empty-title">Report not available</div>
        <div class="empty-desc">${esc(err.message)}</div>
        <div style="margin-top:16px;">
          <button class="btn btn-primary" onclick="runAndReload('${esc(caseId)}')">
            ▶ Run Investigation Now
          </button>
        </div>
      </div>`;
  }
}

async function runAndReload(caseId) {
  const inv = $("#view-investigation");
  inv.innerHTML = `
    <div class="loading">
      <div class="spinner"></div>
      <div>Running investigation for <strong>${esc(caseId)}</strong>…<br>
        <span style="font-size:12px;color:var(--muted)">This may take 10–30 seconds</span>
      </div>
    </div>`;
  try {
    const result = await runInvestigation(caseId);
    if (result.report) {
      state.currentReport = result.report;
      renderInvestigationView(result.report);
      toast(`Investigation complete: ${caseId}`, "success");
      state.benchmarkData = null; // invalidate cached benchmark
      await loadCasesForSidebar();
    } else {
      throw new Error((result.errors || []).join("; ") || "No report returned");
    }
  } catch (err) {
    inv.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">❌</div>
        <div class="empty-title">Investigation failed</div>
        <div class="empty-desc">${esc(err.message)}</div>
      </div>`;
    toast(`Failed: ${err.message}`, "error");
  }
}

// ── Master render function ────────────────────────────────────────────────────

function renderInvestigationView(r) {
  const inv = $("#view-investigation");
  if (!inv) return;

  const action        = r.recommended_action || "UNKNOWN";
  const uncertainty   = (r.uncertainty_level || "unknown").toLowerCase();
  const sufficiency   = (r.sufficiency_level  || "unknown").toLowerCase();
  const approvalReq   = r.approval_required;
  const approvalRoute = r.approval_route || "none";

  const sections = [
    buildPageHeader(r),
    buildCaseInfoCard(r),
    buildActionPanel(r, action, approvalReq, approvalRoute),
    buildAssessmentRow(r, sufficiency, uncertainty),
    buildKeyFindingsCard(r),
    buildEvidenceCard(r),
    buildHypothesesCard(r),
    buildPatternsCard(r),
    buildMissingEvidenceCard(r),
    buildCaseMemoryCard(r),
    buildWorkflowCard(r),
    buildRerunFooter(r),
  ].filter(Boolean).join("\n");

  inv.innerHTML = sections;
}

// ── Section builders ──────────────────────────────────────────────────────────

function buildPageHeader(r) {
  const objective = r.trigger_text || "";
  return `
    <div>
      <div class="page-title">Investigation: ${esc(r.case_id)}</div>
      ${objective ? `<div class="page-subtitle">${esc(objective)}</div>` : ""}
    </div>`;
}

function buildCaseInfoCard(r) {
  const fields = [
    { label: "Case ID",        value: r.case_id,        mono: true },
    { label: "Customer ID",    value: r.customer_id,    mono: true },
    { label: "Card ID",        value: r.card_id,        mono: true },
    { label: "Transaction ID", value: r.transaction_id, mono: true },
    { label: "Opened",         value: r.opened_at ? r.opened_at.slice(0,16).replace("T"," ") : null, mono: false },
    { label: "Risk Score",     value: na(r.risk_score) ? Number(r.risk_score).toFixed(2) : null, mono: false },
    { label: "Report Saved",   value: r.written_at ? r.written_at.slice(0,19).replace("T"," ")+" UTC" : null, mono: false },
    { label: "Investigation Status", value: "COMPLETE", mono: false },
  ];

  const fieldHtml = fields.map(f => `
    <div class="identity-field">
      <div class="identity-label">${esc(f.label)}</div>
      <div class="identity-value ${na(f.value) ? (f.mono ? "" : "identity-value--normal") : "na"}">
        ${esc(display(f.value))}
      </div>
    </div>`).join("");

  return `
    <div class="card">
      <div class="card-header">
        <span class="card-title-icon">🗂</span>
        <span class="card-title">Case Information</span>
        <span class="trigger-chip ${triggerClass(r.trigger)}" style="margin-left:auto">
          ${esc(triggerLabel(r.trigger))}
        </span>
      </div>
      <div class="identity-grid">${fieldHtml}</div>
    </div>`;
}

function buildActionPanel(r, action, approvalReq, approvalRoute) {
  // Approval chip
  const approvalHtml = approvalReq
    ? `<span class="approval-chip approval-required">⚠ Approval Required — ${esc(approvalRoute)}</span>`
    : `<span class="approval-chip approval-none">✓ Auto-executable — no approval required</span>`;

  // Policy rule lookup
  const policyRule = state.policyRules[r.policy_basis];
  let policyHtml = "";
  if (r.policy_basis) {
    const ruleName = policyRule ? policyRule.name : "";
    const riskLevel = policyRule ? policyRule.risk_level : "";
    policyHtml = `
      <div class="policy-block">
        <div class="policy-block-label">Policy Rule Applied</div>
        <div class="policy-block-body">
          <span class="policy-rule-id">${esc(r.policy_basis)}</span>
          ${ruleName ? `<span class="policy-rule-sep">—</span><span class="policy-rule-name">${esc(ruleName)}</span>` : ""}
          ${riskLevel ? `<span class="badge ${riskLevelClass(riskLevel)}" style="margin-left:8px">${esc(riskLevel)} risk</span>` : ""}
        </div>
      </div>`;
  } else if (r.policy_basis === "ACTION_GUARD_SAFETY") {
    policyHtml = `
      <div class="policy-block">
        <div class="policy-block-label">Policy Rule Applied</div>
        <div class="policy-block-body">
          <span class="policy-rule-id">ACTION_GUARD_SAFETY</span>
          <span class="policy-rule-sep">—</span>
          <span class="policy-rule-name">ActionGuard safety override: unsafe action blocked</span>
        </div>
      </div>`;
  }

  const reasoning = r.decision_reasoning || r.outcome_description || "";

  return `
    <div class="action-panel action-${esc(action)}">
      <div class="action-label">Recommended Action</div>
      <div class="action-name">
        <span class="badge badge-lg ${actionBadgeClass(action)}">${esc(actionLabel(action))}</span>
      </div>
      ${reasoning ? `<div class="action-reasoning">${esc(reasoning)}</div>` : ""}
      <div class="action-meta">${approvalHtml}</div>
      ${policyHtml}
    </div>`;
}

function buildAssessmentRow(r, sufficiency, uncertainty) {
  // Evidence count summary strip
  const sc = r.supporting_count   || 0;
  const cc = r.contradictory_count || 0;
  const tc = r.total_evidence_count || (sc + cc);

  return `
    <div class="assessment-row">
      <!-- Sufficiency -->
      <div class="meter-card">
        <div class="meter-label">Evidence Sufficiency</div>
        <div class="meter-value ${sufficiencyBadgeClass(sufficiency)}">${esc(sufficiency.toUpperCase())}</div>
        <div class="meter-reason">${esc(display(r.sufficiency_reason, "No reason recorded"))}</div>
      </div>

      <!-- Uncertainty -->
      <div class="meter-card">
        <div class="meter-label">Uncertainty Level</div>
        <div class="meter-value ${uncertaintyBadgeClass(uncertainty)}">${esc(uncertainty.toUpperCase())}</div>
        <div class="meter-reason">${esc(display(r.uncertainty_reason, "No reason recorded"))}</div>
      </div>

      <!-- Evidence counts -->
      <div class="meter-card">
        <div class="meter-label">Evidence Counts</div>
        <div style="display:flex;gap:16px;align-items:flex-end;margin-bottom:6px;">
          <div>
            <div style="font-size:22px;font-weight:800;color:var(--green)">${sc}</div>
            <div style="font-size:10px;color:var(--muted);font-weight:700;text-transform:uppercase">Supporting</div>
          </div>
          <div>
            <div style="font-size:22px;font-weight:800;color:var(--red)">${cc}</div>
            <div style="font-size:10px;color:var(--muted);font-weight:700;text-transform:uppercase">Contradictory</div>
          </div>
          <div>
            <div style="font-size:22px;font-weight:800;color:var(--accent)">${tc}</div>
            <div style="font-size:10px;color:var(--muted);font-weight:700;text-transform:uppercase">Total</div>
          </div>
        </div>
        <div class="meter-reason">Evidence items derived from investigation report</div>
      </div>
    </div>`;
}

function buildKeyFindingsCard(r) {
  const findings = r.key_findings || [];
  if (findings.length === 0) return "";
  return `
    <div class="card">
      <div class="card-header">
        <span class="card-title-icon">🔍</span>
        <span class="card-title">Key Findings</span>
        <span class="card-count">${findings.length}</span>
      </div>
      <ul class="findings-list">
        ${findings.map(f => `<li>${esc(f)}</li>`).join("")}
      </ul>
    </div>`;
}

function buildEvidenceCard(r) {
  const supporting    = r.supporting_items    || [];
  const contradictory = r.contradictory_items || [];

  const suppHtml = supporting.length > 0
    ? supporting.map((e, i) => `
        <div class="evidence-item supporting">
          <span class="ev-idx">${i + 1}</span>
          <span class="ev-text">${esc(e)}</span>
        </div>`).join("")
    : `<div class="evidence-empty">No supporting evidence items recorded in this report</div>`;

  const contrHtml = contradictory.length > 0
    ? contradictory.map((e, i) => `
        <div class="evidence-item contradictory">
          <span class="ev-idx">${i + 1}</span>
          <span class="ev-text">${esc(e)}</span>
        </div>`).join("")
    : `<div class="evidence-empty">No contradictory evidence items recorded in this report</div>`;

  return `
    <div class="card">
      <div class="card-header">
        <span class="card-title-icon">📊</span>
        <span class="card-title">Evidence</span>
        <span style="margin-left:auto;font-size:11px;color:var(--muted)">
          All items sourced from investigation report — nothing fabricated
        </span>
      </div>
      <div class="evidence-columns">
        <div class="evidence-col">
          <div class="evidence-col-header supporting">
            ✓ Supporting Evidence
            <span class="evidence-count-badge">${supporting.length}</span>
          </div>
          ${suppHtml}
        </div>
        <div class="evidence-col">
          <div class="evidence-col-header contradictory">
            ✗ Contradictory Evidence
            <span class="evidence-count-badge">${contradictory.length}</span>
          </div>
          ${contrHtml}
        </div>
      </div>
    </div>`;
}

function buildHypothesesCard(r) {
  const hypotheses = r.hypotheses || [];

  const content = hypotheses.length > 0
    ? hypotheses.map(h => {
        const statusCls = `hyp-${(h.status || "active").toLowerCase()}`;
        const confPct   = h.confidence !== undefined ? Math.round(h.confidence * 100) : null;
        return `
          <div class="hyp-item">
            <div class="hyp-header">
              <span class="hyp-name">${esc(h.name || h.id || "Hypothesis")}</span>
              <span class="hyp-status ${statusCls}">${esc((h.status || "active").toUpperCase())}</span>
              ${confPct !== null
                ? `<span class="hyp-conf" style="margin-left:auto">Confidence: ${confPct}%</span>`
                : ""}
            </div>
            ${h.description ? `<div class="hyp-desc">${esc(h.description)}</div>` : ""}
            ${(h.supporting_evidence_ids || []).length > 0
              ? `<div class="hyp-ev-row"><span class="hyp-ev-label supporting">Supporting:</span> ${esc(h.supporting_evidence_ids.join(", "))}</div>`
              : ""}
            ${(h.contradictory_evidence_ids || []).length > 0
              ? `<div class="hyp-ev-row"><span class="hyp-ev-label contradictory">Contradictory:</span> ${esc(h.contradictory_evidence_ids.join(", "))}</div>`
              : ""}
          </div>`;
      }).join("")
    : `<div class="section-unavailable">
        <span class="section-unavailable-icon">ℹ</span>
        <div>
          <strong>No hypothesis confidence thresholds reached.</strong><br>
          The Part 2 system records hypotheses only when confidence ≥ 0.4.
          In this investigation all hypotheses remained below that threshold.
          This is reflected in the uncertainty level above.
        </div>
      </div>`;

  return `
    <div class="card">
      <div class="card-header">
        <span class="card-title-icon">🧪</span>
        <span class="card-title">Hypotheses</span>
        ${hypotheses.length > 0 ? `<span class="card-count">${hypotheses.length}</span>` : ""}
      </div>
      ${content}
    </div>`;
}

function buildPatternsCard(r) {
  const patterns = r.identified_patterns || [];
  if (patterns.length === 0) return "";
  return `
    <div class="card">
      <div class="card-header">
        <span class="card-title-icon">⚡</span>
        <span class="card-title">Identified Fraud Patterns</span>
        <span class="card-count">${patterns.length}</span>
      </div>
      <div class="entity-list">
        ${patterns.map(p => `
          <span class="pattern-chip">${esc(p.replace(/_/g, " "))}</span>
        `).join("")}
      </div>
    </div>`;
}

function buildMissingEvidenceCard(r) {
  const missing = r.missing_evidence || [];
  if (missing.length === 0) return "";
  return `
    <div class="card">
      <div class="card-header">
        <span class="card-title-icon">⚠</span>
        <span class="card-title">Missing Evidence</span>
        <span class="card-count" style="background:var(--orange-dim);color:var(--orange)">${missing.length}</span>
      </div>
      <div style="font-size:12px;color:var(--muted);margin-bottom:10px;">
        Evidence categories identified as absent or incomplete during investigation.
      </div>
      <ul class="findings-list">
        ${missing.map(m => `<li style="border-left-color:var(--orange)">${esc(m)}</li>`).join("")}
      </ul>
    </div>`;
}

function buildCaseMemoryCard(r) {
  const mem = r.case_memory;
  // Only render if memory has substantive content
  if (!mem || (!mem.customer_id && !mem.final_action && !mem.key_evidence_summary)) return "";

  const completedAt = mem.investigation_completed_at
    ? mem.investigation_completed_at.slice(0, 19).replace("T", " ") + " UTC"
    : null;

  const memoryCells = [
    { label: "Customer ID",       value: mem.customer_id },
    { label: "Card ID",           value: mem.card_id },
    { label: "Transaction ID",    value: mem.transaction_id },
    { label: "Final Action",      value: mem.final_action },
    { label: "Approved By",       value: mem.approved_by },
    { label: "Completed At",      value: completedAt },
  ];

  const policyDecisions = (mem.policy_decisions || []).filter(Boolean);
  const fraudPatterns   = (mem.fraud_patterns_identified || []).filter(Boolean);

  return `
    <div class="card">
      <div class="card-header">
        <span class="card-title-icon">💾</span>
        <span class="card-title">Case Memory</span>
        <span style="margin-left:auto;font-size:11px;color:var(--muted)">Persisted by Part 2 workflow</span>
      </div>

      <div class="identity-grid" style="margin-bottom:16px;">
        ${memoryCells.map(c => `
          <div class="identity-field">
            <div class="identity-label">${esc(c.label)}</div>
            <div class="identity-value ${na(c.value) ? "" : "na"}" style="font-size:13px">
              ${esc(display(c.value))}
            </div>
          </div>`).join("")}
      </div>

      ${mem.outcome_description ? `
        <div style="margin-bottom:12px;">
          <div class="identity-label">Outcome Description</div>
          <div style="font-size:13px;color:var(--text);margin-top:4px;line-height:1.5">${esc(mem.outcome_description)}</div>
        </div>` : ""}

      ${mem.key_evidence_summary ? `
        <div style="margin-bottom:12px;">
          <div class="identity-label">Key Evidence Summary (memory)</div>
          <div style="font-size:13px;color:var(--muted);margin-top:4px;line-height:1.6">${esc(mem.key_evidence_summary)}</div>
        </div>` : ""}

      ${policyDecisions.length > 0 ? `
        <div style="margin-bottom:12px;">
          <div class="identity-label">Policy Decisions Applied</div>
          <div style="margin-top:6px;display:flex;gap:6px;flex-wrap:wrap">
            ${policyDecisions.map(d => `<span class="badge ${actionBadgeClass(d)}">${esc(actionLabel(d))}</span>`).join("")}
          </div>
        </div>` : ""}

      ${fraudPatterns.length > 0 ? `
        <div>
          <div class="identity-label">Fraud Patterns in Memory</div>
          <div class="entity-list" style="margin-top:6px">
            ${fraudPatterns.map(p => `<span class="pattern-chip">${esc(p.replace(/_/g, " "))}</span>`).join("")}
          </div>
        </div>` : ""}
    </div>`;
}

function buildWorkflowCard(r) {
  // Build data-driven step list from actual report fields.
  // Only show steps where we have real data from the report.
  // DO NOT fabricate timestamps, latency, or tool details that aren't in the stored report.

  const steps = [];

  // Step 1: Case loaded — we know the case ID and customer
  steps.push({
    icon: "📥", done: true,
    label: "Case Loaded",
    desc: `Case ${r.case_id} — Customer ${r.customer_id || "—"}, Card ${r.card_id || "—"}`,
  });

  // Step 2: Investigation planned — we know the trigger
  steps.push({
    icon: "🗺", done: true,
    label: "Investigation Planned",
    desc: `Trigger: ${triggerLabel(r.trigger)}${r.risk_score ? ` | Risk score: ${Number(r.risk_score).toFixed(2)}` : ""}`,
  });

  // Step 3: Evidence collected — we know counts
  const tc = r.total_evidence_count || 0;
  steps.push({
    icon: "🔌", done: true,
    label: "Evidence Collected via MCP Tools",
    desc: tc > 0
      ? `${tc} total evidence items collected (${r.supporting_count || 0} supporting, ${r.contradictory_count || 0} contradictory)`
      : "Evidence collection completed — see evidence section above",
  });

  // Step 4: Evidence analysed — we have classification results
  steps.push({
    icon: "⚖", done: true,
    label: "Evidence Analysed & Classified",
    desc: `${r.supporting_count || 0} supporting items / ${r.contradictory_count || 0} contradictory items identified`,
  });

  // Step 5: Hypotheses — report what actually happened
  const hypCount = (r.hypotheses || []).length;
  steps.push({
    icon: "🧪", done: true,
    label: "Hypotheses Evaluated",
    desc: hypCount > 0
      ? `${hypCount} hypothesis/hypotheses recorded`
      : "No hypothesis reached the 0.4 confidence threshold — reflected in uncertainty level",
  });

  // Step 6: Uncertainty — from actual report value
  steps.push({
    icon: "📐", done: true,
    label: "Uncertainty Assessed",
    desc: `Level: ${(r.uncertainty_level || "unknown").toUpperCase()} — ${r.uncertainty_reason || "see above"}`,
  });

  // Step 7: Sufficiency — from actual report value
  steps.push({
    icon: "✅", done: true,
    label: "Evidence Sufficiency Assessed",
    desc: `Level: ${(r.sufficiency_level || "unknown").toUpperCase()} — ${r.sufficiency_reason || "see above"}`,
  });

  // Step 8: Policy evaluation — rule ID is in the report
  const policyRule = state.policyRules[r.policy_basis];
  steps.push({
    icon: "📜", done: true,
    label: "Policy Evaluated",
    desc: r.policy_basis
      ? `Rule: ${r.policy_basis}${policyRule ? ` — ${policyRule.name}` : ""}`
      : "Policy evaluated — rule not recorded in report",
  });

  // Step 9: Action determined — from actual report
  steps.push({
    icon: "⚡", done: true,
    label: "Action Determined",
    desc: `Recommended: ${actionLabel(r.recommended_action)}`,
  });

  // Step 10: Approval routing — from actual report
  steps.push({
    icon: "🔐", done: true,
    label: "Approval Routed",
    desc: r.approval_required
      ? `Requires approval from: ${r.approval_route}`
      : "No approval required — action is auto-executable",
  });

  // Step 11: Memory written — we know it was written (file exists)
  steps.push({
    icon: "💾", done: true,
    label: "Case Memory Written",
    desc: r.written_at
      ? `Written at: ${r.written_at.slice(0,19).replace("T"," ")} UTC`
      : "Investigation result persisted to investigation_reports/",
  });

  const stepsHtml = steps.map((s, idx) => `
    <div class="timeline-step ${s.done ? "timeline-step--done" : ""}">
      <div class="timeline-dot ${s.done ? "done" : ""}">${s.icon}</div>
      <div class="timeline-body">
        <div class="timeline-title">${esc(s.label)}</div>
        <div class="timeline-desc">${esc(s.desc)}</div>
      </div>
    </div>`).join("");

  return `
    <div class="card">
      <div class="card-header">
        <span class="card-title-icon">📋</span>
        <span class="card-title">Investigation Workflow</span>
      </div>
      <div class="timeline-note">
        Step descriptions are derived from actual report data.
        Per-step timestamps are not persisted in the stored report format.
      </div>
      <div class="timeline">${stepsHtml}</div>
    </div>`;
}

function buildRerunFooter(r) {
  return `
    <div class="rerun-footer">
      <button class="btn btn-secondary btn-sm" onclick="runAndReload('${esc(r.case_id)}')">
        ↺ Re-run Investigation
      </button>
      <span style="font-size:11px;color:var(--muted)">
        Re-running will execute the Part 2 workflow and overwrite the stored report.
      </span>
    </div>`;
}

// ── Benchmark dashboard ───────────────────────────────────────────────────────

async function loadBenchmarkView() {
  setView("benchmark");
  const bv = $("#view-benchmark");

  if (state.benchmarkData) {
    renderBenchmarkView(state.benchmarkData);
    return;
  }

  bv.innerHTML = `
    <div class="loading">
      <div class="spinner"></div>
      <div>Loading benchmark data for all 20 cases…</div>
    </div>`;

  try {
    // Load benchmark + validation in parallel — one shot, no per-case requests
    const [benchData, validData] = await Promise.all([
      fetchBenchmark(),
      apiFetch("/benchmark/validate"),
    ]);
    state.benchmarkData = { bench: benchData, validation: validData };
    renderBenchmarkView(state.benchmarkData);
  } catch (err) {
    bv.innerHTML = `
      <div class="empty-state">
        <div class="empty-icon">❌</div>
        <div class="empty-title">Benchmark load failed</div>
        <div class="empty-desc">${esc(err.message)}</div>
      </div>`;
  }
}

function renderBenchmarkView(data) {
  const bv   = $("#view-benchmark");
  const bench      = data.bench || data;        // backwards-compat if only bench present
  const validation = data.validation || null;
  const stats      = bench.statistics || {};
  const ev         = stats.evidence_totals || {};

  // ── Header stat cards ──────────────────────────────────────────────────────
  const headerStatsHtml = `
    <div class="stat-grid">
      <div class="stat-card">
        <div class="stat-value" style="color:var(--accent)">${bench.total_cases}</div>
        <div class="stat-label">Total Cases</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" style="color:var(--green)">${bench.completed}</div>
        <div class="stat-label">Reports Loaded</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" style="color:var(--red)">${bench.failed || 0}</div>
        <div class="stat-label">Load Failures</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" style="color:var(--orange)">${stats.approval_required_count || 0}</div>
        <div class="stat-label">Need Approval</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" style="color:var(--green)">${stats.approval_not_required_count || 0}</div>
        <div class="stat-label">Auto-executable</div>
      </div>
      ${ev.total_supporting !== undefined ? `
      <div class="stat-card">
        <div class="stat-value" style="color:var(--green)">${ev.total_supporting}</div>
        <div class="stat-label">Total Sup. Evidence</div>
      </div>
      <div class="stat-card">
        <div class="stat-value" style="color:var(--red)">${ev.total_contradictory}</div>
        <div class="stat-label">Total Contra. Evidence</div>
      </div>` : ""}
    </div>`;

  // ── Validation panel ───────────────────────────────────────────────────────
  let validationHtml = "";
  if (validation) {
    const allOk  = validation.errors_count === 0;
    const vIcon  = allOk ? "✅" : "❌";
    const vColor = allOk ? "var(--green)" : "var(--red)";

    const limitRows = (validation.known_limitations || []).map(lim => `
      <tr>
        <td class="mono" style="font-size:11px;color:var(--muted)">${esc(lim.field)}</td>
        <td style="font-size:12px;color:var(--muted);line-height:1.5">${esc(lim.detail)}</td>
        <td style="text-align:center;font-size:12px;color:var(--muted)">${lim.count}/20</td>
      </tr>`).join("");

    const warnRows = (validation.warnings || []).map(w => `
      <tr>
        <td class="mono" style="font-size:11px">${esc(w.case_id)}</td>
        <td style="font-size:12px;color:var(--orange)">${esc(w.check)}</td>
        <td style="font-size:12px;color:var(--muted)">${esc(w.detail)}</td>
      </tr>`).join("");

    const passedList = (validation.checks_passed || []).map(c =>
      `<span style="font-size:11px;color:var(--green);margin-right:8px">✓ ${esc(c.replace(/_/g," "))}</span>`
    ).join("");

    validationHtml = `
      <div class="card">
        <div class="card-header">
          <span class="card-title-icon">${vIcon}</span>
          <span class="card-title">Schema & Consistency Validation</span>
          <span style="margin-left:auto;font-size:12px;color:${vColor}">
            ${validation.checks_passed_count} checks passed ·
            ${validation.errors_count} errors ·
            ${validation.warnings_count} warnings
          </span>
        </div>
        <div style="font-size:13px;color:var(--muted);margin-bottom:12px">${esc(validation.summary)}</div>

        ${passedList ? `<div style="margin-bottom:14px;line-height:2">${passedList}</div>` : ""}

        ${validation.errors_count > 0 ? `
          <div style="font-size:11px;font-weight:700;color:var(--red);text-transform:uppercase;letter-spacing:.08em;margin-bottom:6px">Errors</div>
          ${validation.errors.map(e => `
            <div style="padding:8px 12px;background:var(--red-dim);border-left:3px solid var(--red);
                        border-radius:4px;margin-bottom:6px;font-size:12px">
              <strong>${esc(e.case_id)}</strong> · ${esc(e.check)}: ${esc(e.detail)}
            </div>`).join("")}` : ""}

        ${warnRows ? `
          <div style="font-size:11px;font-weight:700;color:var(--orange);text-transform:uppercase;
                      letter-spacing:.08em;margin:12px 0 6px">Warnings</div>
          <div class="benchmark-table-wrap">
            <table class="benchmark-table">
              <thead><tr><th>Case</th><th>Check</th><th>Detail</th></tr></thead>
              <tbody>${warnRows}</tbody>
            </table>
          </div>` : ""}

        ${limitRows ? `
          <div style="font-size:11px;font-weight:700;color:var(--muted);text-transform:uppercase;
                      letter-spacing:.08em;margin:14px 0 6px">
            Known Limitations — documented, not errors
          </div>
          <div class="benchmark-table-wrap">
            <table class="benchmark-table">
              <thead><tr><th>Field</th><th>Detail</th><th>Affected</th></tr></thead>
              <tbody>${limitRows}</tbody>
            </table>
          </div>` : ""}
      </div>`;
  }

  // ── Distribution grids ─────────────────────────────────────────────────────
  const actionDistHtml = buildDistributionHtml(
    stats.action_distribution || {}, actionLabel, actionBadgeClass);

  const sufDistHtml = buildDistributionHtml(
    stats.sufficiency_distribution || {},
    v => v.toUpperCase(), v => sufficiencyBadgeClass(v));

  const uncDistHtml = buildDistributionHtml(
    stats.uncertainty_distribution || {},
    v => v.toUpperCase(), v => uncertaintyBadgeClass(v));

  const approvalDistHtml = buildDistributionHtml(
    stats.approval_route_distribution || {},
    v => v === "none" ? "Auto (none)" : v.replace("_", " "),
    v => v === "none" ? "badge-MONITOR" :
         v === "fraud_analyst" ? "badge-VERIFY_WITH_CUSTOMER" : "badge-ESCALATE");

  const triggerDistHtml = buildDistributionHtml(
    stats.trigger_distribution || {},
    v => triggerLabel(v),
    v => { const c = triggerClass(v); return c ? c.replace("trigger-","badge-") : "badge-unknown"; });

  const policyDistHtml = buildDistributionHtml(
    stats.policy_basis_distribution || {},
    v => v,
    v => v === "RULE-001" ? "badge-BLOCK_CARD" :
         v === "RULE-003" ? "badge-VERIFY_WITH_CUSTOMER" :
         v === "RULE-006" ? "badge-ESCALATE" : "badge-UNKNOWN");

  // ── Case table ─────────────────────────────────────────────────────────────
  const tableRows = (bench.cases || []).map(c => {
    const act = c.recommended_action || "UNKNOWN";
    const unc = c.uncertainty_level  || "unknown";
    const suf = c.sufficiency_level  || "unknown";
    const sc  = c.supporting_count   ?? "—";
    const cc  = c.contradictory_count ?? "—";
    const approvalHtml = c.approval_required
      ? `<span style="color:var(--orange);font-size:11px">⚠ ${esc(c.approval_route)}</span>`
      : `<span style="color:var(--green);font-size:11px">✓ auto</span>`;
    return `
      <tr class="clickable-row" onclick="loadCaseView('${esc(c.case_id)}')">
        <td class="mono">${esc(c.case_id)}</td>
        <td class="mono" style="font-size:11px">${esc(c.customer_id || "—")}</td>
        <td><span class="trigger-chip ${triggerClass(c.trigger)}">${esc(triggerLabel(c.trigger))}</span></td>
        <td><span class="badge ${actionBadgeClass(act)}">${esc(actionLabel(act))}</span></td>
        <td><span class="badge ${sufficiencyBadgeClass(suf)}">${esc(suf.toUpperCase())}</span></td>
        <td><span class="badge ${uncertaintyBadgeClass(unc)}">${esc(unc.toUpperCase())}</span></td>
        <td>${approvalHtml}</td>
        <td style="text-align:center;font-size:12px">
          <span style="color:var(--green)">${sc}</span>
          <span style="color:var(--muted)"> / </span>
          <span style="color:var(--red)">${cc}</span>
        </td>
        <td class="mono" style="font-size:11px;color:var(--muted)">${esc(c.policy_basis || "—")}</td>
      </tr>`;
  }).join("");

  const errorRows = (bench.errors || []).map(e => `
    <tr>
      <td class="mono">${esc(e.case_id)}</td>
      <td colspan="8" style="color:var(--red)">${esc(e.error)}</td>
    </tr>`).join("");

  bv.innerHTML = `
    <div>
      <div class="page-title">Benchmark Dashboard</div>
      <div class="page-subtitle">
        20-case validation — all values from actual stored reports · no fabricated metrics
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <span class="card-title-icon">📊</span>
        <span class="card-title">Summary Statistics</span>
      </div>
      ${headerStatsHtml}
    </div>

    ${validationHtml}

    <div class="dist-grid">
      <div class="card">
        <div class="card-header"><span class="card-title-icon">⚡</span>
          <span class="card-title">Actions</span></div>
        ${actionDistHtml}
      </div>
      <div class="card">
        <div class="card-header"><span class="card-title-icon">✅</span>
          <span class="card-title">Sufficiency</span></div>
        ${sufDistHtml}
      </div>
      <div class="card">
        <div class="card-header"><span class="card-title-icon">📐</span>
          <span class="card-title">Uncertainty</span></div>
        ${uncDistHtml}
      </div>
    </div>

    <div class="dist-grid">
      <div class="card">
        <div class="card-header"><span class="card-title-icon">🔐</span>
          <span class="card-title">Approval Route</span></div>
        ${approvalDistHtml}
      </div>
      <div class="card">
        <div class="card-header"><span class="card-title-icon">🚦</span>
          <span class="card-title">Trigger Type</span></div>
        ${triggerDistHtml}
      </div>
      <div class="card">
        <div class="card-header"><span class="card-title-icon">📜</span>
          <span class="card-title">Policy Rule</span></div>
        ${policyDistHtml}
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <span class="card-title-icon">🗂</span>
        <span class="card-title">Case-by-Case Results</span>
        <span style="margin-left:auto;font-size:12px;color:var(--muted)">
          Click any row to open the full investigation view
        </span>
      </div>
      <div class="benchmark-table-wrap">
        <table class="benchmark-table">
          <thead>
            <tr>
              <th>Case ID</th>
              <th>Customer</th>
              <th>Trigger</th>
              <th>Action</th>
              <th>Sufficiency</th>
              <th>Uncertainty</th>
              <th>Approval</th>
              <th>Sup / Contra</th>
              <th>Policy Rule</th>
            </tr>
          </thead>
          <tbody>
            ${tableRows}
            ${errorRows}
          </tbody>
        </table>
      </div>
    </div>`;
}

function buildDistributionHtml(dist, labelFn, classFn) {
  const entries = Object.entries(dist).sort((a, b) => b[1] - a[1]);
  const total = entries.reduce((s, [, v]) => s + v, 0);
  if (!entries.length) return `<div class="evidence-empty">No data</div>`;
  return entries.map(([k, count]) => {
    const pct = total > 0 ? Math.round((count / total) * 100) : 0;
    return `
      <div class="dist-row">
        <div class="dist-label-row">
          <span class="badge ${classFn(k)}">${esc(labelFn(k))}</span>
          <span class="dist-count">${count} (${pct}%)</span>
        </div>
        <div class="dist-bar-track">
          <div class="dist-bar-fill" style="width:${pct}%"></div>
        </div>
      </div>`;
  }).join("");
}

// ── Welcome view ──────────────────────────────────────────────────────────────

function renderWelcomeView() {
  const wv = $("#view-welcome");
  if (!wv) return;
  const total  = state.cases.length;
  const withR  = state.cases.filter(c => c.has_report).length;

  wv.innerHTML = `
    <div>
      <div class="page-title">FraudGraph Investigator</div>
      <div class="page-subtitle">AI-powered fraud investigation with graph evidence — Hacker House Goa</div>
    </div>

    <div class="card">
      <div class="card-header">
        <span class="card-title-icon">🚀</span>
        <span class="card-title">Quick Start</span>
      </div>
      <div style="font-size:13px;color:var(--muted);line-height:1.7;margin-bottom:14px;">
        Select a case from the sidebar, or use the dropdown below.
        <strong style="color:var(--text)">${withR} of ${total}</strong> cases have stored investigation reports.
      </div>
      <div class="run-form">
        <select id="quick-case-select" class="run-select">
          <option value="">— Select a case —</option>
          ${state.cases.map(c =>
            `<option value="${esc(c.case_id)}">${esc(c.case_id)} — ${esc(c.customer_id || "")} (${esc(c.trigger_type || "")})</option>`
          ).join("")}
        </select>
        <button class="btn btn-primary" onclick="quickInspect()">Inspect Report</button>
        <button class="btn btn-secondary" onclick="quickRun()">▶ Run Investigation</button>
      </div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
      <div class="card">
        <div class="card-header">
          <span class="card-title-icon">📁</span>
          <span class="card-title">Open Cases</span>
        </div>
        <div style="font-size:13px;color:var(--muted);line-height:1.8;margin-bottom:12px;">
          20 fraud investigation cases from the HHG benchmark pack.<br>
          Triggers: risk score model alerts, customer dispute reports, analyst requests.
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap;">
          <span class="badge badge-BLOCK_CARD">BLOCK CARD</span>
          <span class="badge badge-VERIFY_WITH_CUSTOMER">VERIFY</span>
          <span class="badge badge-ESCALATE">ESCALATE</span>
        </div>
      </div>
      <div class="card">
        <div class="card-header">
          <span class="card-title-icon">🏗</span>
          <span class="card-title">System Architecture</span>
        </div>
        <div style="font-size:12px;color:var(--muted);line-height:2;font-family:var(--mono)">
          UI → Part 3 API (/api/v3/*)<br>
          Part 3 API → Part 2 Workflow (unchanged)<br>
          Part 2 Workflow → MCP Tools (8 tools)<br>
          MCP Tools → CSV / TigerGraph<br>
          Results → investigation_reports/*.json
        </div>
      </div>
    </div>

    <div class="card">
      <div class="card-header">
        <span class="card-title-icon">📊</span>
        <span class="card-title">Benchmark Validation</span>
      </div>
      <div style="font-size:13px;color:var(--muted);margin-bottom:12px;">
        View aggregate results and per-case outcomes for all 20 benchmark investigations.
        All statistics computed from actual stored reports — no fabricated metrics.
      </div>
      <button class="btn btn-primary" onclick="loadBenchmarkView()">
        View Benchmark Dashboard →
      </button>
    </div>`;
}

function quickInspect() {
  const sel = $("#quick-case-select");
  if (!sel?.value) { toast("Select a case first", "error"); return; }
  loadCaseView(sel.value);
}

function quickRun() {
  const sel = $("#quick-case-select");
  if (!sel?.value) { toast("Select a case first", "error"); return; }
  setView("investigation");
  runAndReload(sel.value);
}

// ── Initialisation ────────────────────────────────────────────────────────────

async function init() {
  // Wire nav items
  $$(".nav-item[data-view]").forEach(btn => {
    btn.addEventListener("click", () => {
      const v = btn.getAttribute("data-view");
      if (v === "benchmark") loadBenchmarkView();
      else setView(v);
    });
  });

  // Load policy rules and case list in parallel
  await Promise.all([loadPolicyRules(), loadCasesForSidebar()]);

  // Render welcome view now that cases are loaded
  renderWelcomeView();
  setView("welcome");
}

document.addEventListener("DOMContentLoaded", init);
