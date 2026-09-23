"""
agent/evidence/extractor.py — Extract Evidence objects from ToolResult.

Every Evidence object produced here is fully traceable:
  evidence_id  → unique ID (EV-001, EV-002 …)
  source_type  → which of the 8 MCP tools produced it
  source_id    → the customer_id / transaction_id / case_id it came from
  claim        → human-readable factual statement
  value        → machine-readable scalar
  retrieval_method → exact tool name

The agent NEVER fabricates evidence. Every claim is sourced from an
actual ToolResult from Part 1.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from agent.state.models import Evidence, EvidenceSourceType
from agent.tools.adapters import ToolResult

log = logging.getLogger(__name__)

_COUNTER = 0  # global for unique IDs within a run


def _next_id() -> str:
    global _COUNTER
    _COUNTER += 1
    return f"EV-{_COUNTER:03d}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── Per-tool extractors ───────────────────────────────────────────────────────

def _extract_get_case(result: ToolResult) -> list[Evidence]:
    items: list[Evidence] = []
    case = result.case_data
    txn = result.transaction_data

    if not case:
        return items

    customer_id = case.get("customer_id", "unknown")
    case_id = case.get("case_id", "unknown")
    ts = _now()

    # Risk score
    risk = case.get("risk_score")
    if risk is not None and risk != "":
        try:
            risk_val = float(risk)
            items.append(Evidence(
                evidence_id=_next_id(),
                source_type=EvidenceSourceType.MCP_GET_CASE,
                source_id=case_id,
                claim=f"Case {case_id} has risk score {risk_val:.2f}",
                value=risk_val,
                timestamp=ts,
                relevance="Higher risk score indicates model flagged this as suspicious",
                retrieval_method="get_case",
            ))
        except (ValueError, TypeError):
            pass

    # Trigger type
    trigger = case.get("trigger_type", "")
    if trigger:
        items.append(Evidence(
            evidence_id=_next_id(),
            source_type=EvidenceSourceType.MCP_GET_CASE,
            source_id=case_id,
            claim=f"Case triggered by: {trigger}. Trigger text: {case.get('trigger_text', '')}",
            value=trigger,
            timestamp=ts,
            relevance="Trigger type indicates how this case was opened",
            retrieval_method="get_case",
        ))

    # Flagged transaction amount
    if txn:
        amt = txn.get("TransactionAmt") or txn.get("amount")
        if amt is not None:
            try:
                amt_val = float(amt)
                items.append(Evidence(
                    evidence_id=_next_id(),
                    source_type=EvidenceSourceType.MCP_GET_CASE,
                    source_id=case.get("flagged_txn_id", case_id),
                    claim=f"Flagged transaction amount is ${amt_val:.2f}",
                    value=amt_val,
                    timestamp=ts,
                    relevance="Transaction amount is relevant to exposure and fraud pattern",
                    retrieval_method="get_case",
                ))
            except (ValueError, TypeError):
                pass

        channel = txn.get("channel")
        if channel:
            items.append(Evidence(
                evidence_id=_next_id(),
                source_type=EvidenceSourceType.MCP_GET_CASE,
                source_id=case.get("flagged_txn_id", case_id),
                claim=f"Flagged transaction channel: {channel}",
                value=channel,
                timestamp=ts,
                relevance="Online channel increases card-not-present fraud risk",
                retrieval_method="get_case",
            ))

    return items


def _extract_get_customer_history(result: ToolResult) -> list[Evidence]:
    items: list[Evidence] = []
    data = result.customer_data
    if not data:
        return items

    customer_id = data.get("customer_id", "unknown")
    ts = _now()

    txn_count = data.get("transaction_count", 0)
    if txn_count:
        items.append(Evidence(
            evidence_id=_next_id(),
            source_type=EvidenceSourceType.MCP_CUSTOMER_HISTORY,
            source_id=customer_id,
            claim=f"Customer {customer_id} has {txn_count} total transactions",
            value=txn_count,
            timestamp=ts,
            relevance="Transaction volume establishes customer baseline",
            retrieval_method="get_customer_history",
        ))

    fraud_count = data.get("fraud_case_count", 0)
    items.append(Evidence(
        evidence_id=_next_id(),
        source_type=EvidenceSourceType.MCP_CUSTOMER_HISTORY,
        source_id=customer_id,
        claim=f"Customer {customer_id} has {fraud_count} prior confirmed fraud cases",
        value=fraud_count,
        timestamp=ts,
        relevance="Prior fraud history is a strong indicator of fraud risk",
        retrieval_method="get_customer_history",
    ))

    exposure = data.get("total_fraud_exposure_usd", 0.0)
    if exposure:
        items.append(Evidence(
            evidence_id=_next_id(),
            source_type=EvidenceSourceType.MCP_CUSTOMER_HISTORY,
            source_id=customer_id,
            claim=f"Customer {customer_id} total historical fraud exposure: ${exposure:.2f}",
            value=exposure,
            timestamp=ts,
            relevance="Historical exposure indicates fraud severity for this customer",
            retrieval_method="get_customer_history",
        ))

    return items


def _extract_get_transaction_context(result: ToolResult) -> list[Evidence]:
    items: list[Evidence] = []
    txn = result.transaction_data
    if not txn:
        return items

    txn_id = str(txn.get("TransactionID", result.raw.get("TransactionID", "unknown")))
    ts = _now()

    # Device info
    device_type = txn.get("DeviceType")
    device_info = txn.get("DeviceInfo")
    if device_type or device_info:
        items.append(Evidence(
            evidence_id=_next_id(),
            source_type=EvidenceSourceType.MCP_TRANSACTION_CONTEXT,
            source_id=txn_id,
            claim=f"Transaction {txn_id} used device: {device_type or 'unknown'} / {device_info or 'unknown'}",
            value={"DeviceType": device_type, "DeviceInfo": device_info},
            timestamp=ts,
            relevance="Device type/info identifies if a new or shared device was used",
            retrieval_method="get_transaction_context",
        ))
    else:
        items.append(Evidence(
            evidence_id=_next_id(),
            source_type=EvidenceSourceType.MCP_TRANSACTION_CONTEXT,
            source_id=txn_id,
            claim=f"Transaction {txn_id} has NO device identity record",
            value=None,
            timestamp=ts,
            relevance="Missing device info is a data quality gap — increases uncertainty",
            retrieval_method="get_transaction_context",
        ))

    # Email domain
    email = txn.get("P_emaildomain")
    if email:
        items.append(Evidence(
            evidence_id=_next_id(),
            source_type=EvidenceSourceType.MCP_TRANSACTION_CONTEXT,
            source_id=txn_id,
            claim=f"Transaction {txn_id} purchaser email domain: {email}",
            value=email,
            timestamp=ts,
            relevance="Email domain change can indicate account takeover",
            retrieval_method="get_transaction_context",
        ))

    # Region / billing address
    region = txn.get("addr1")
    if region:
        items.append(Evidence(
            evidence_id=_next_id(),
            source_type=EvidenceSourceType.MCP_TRANSACTION_CONTEXT,
            source_id=txn_id,
            claim=f"Transaction {txn_id} billing region: {region}",
            value=region,
            timestamp=ts,
            relevance="Unusual billing region indicates out-of-region use",
            retrieval_method="get_transaction_context",
        ))

    # Prior fraud cases for customer
    prior_fraud = result.customer_data.get("customer_prior_fraud_cases", 0)
    items.append(Evidence(
        evidence_id=_next_id(),
        source_type=EvidenceSourceType.MCP_TRANSACTION_CONTEXT,
        source_id=txn_id,
        claim=f"Customer associated with transaction {txn_id} has {prior_fraud} prior fraud cases",
        value=prior_fraud,
        timestamp=ts,
        relevance="Prior fraud case count for the transacting customer",
        retrieval_method="get_transaction_context",
    ))

    return items


def _extract_find_connected_entities(result: ToolResult) -> list[Evidence]:
    items: list[Evidence] = []
    entities = result.connected_entities
    data = result.customer_data
    entity_id = data.get("entity_id", "unknown")
    ts = _now()

    count = len(entities)
    items.append(Evidence(
        evidence_id=_next_id(),
        source_type=EvidenceSourceType.MCP_CONNECTED_ENTITIES,
        source_id=entity_id,
        claim=f"Entity {entity_id} is connected to {count} other entities via shared attributes",
        value=count,
        timestamp=ts,
        relevance="High connectivity suggests fraud ring or shared device/email activity",
        retrieval_method="find_connected_entities",
    ))

    # Summarise relationship types
    rel_counts: dict[str, int] = {}
    for e in entities:
        rel = e.get("relationship", "unknown")
        rel_counts[rel] = rel_counts.get(rel, 0) + 1

    for rel, cnt in rel_counts.items():
        items.append(Evidence(
            evidence_id=_next_id(),
            source_type=EvidenceSourceType.MCP_CONNECTED_ENTITIES,
            source_id=entity_id,
            claim=f"{cnt} connected entities via {rel}",
            value=cnt,
            timestamp=ts,
            relevance=f"Shared {rel.replace('_', ' ')} connections indicate coordinated fraud risk",
            retrieval_method="find_connected_entities",
        ))

    return items


def _extract_find_prior_cases(result: ToolResult) -> list[Evidence]:
    items: list[Evidence] = []
    data = result.customer_data
    cases = result.prior_cases
    ts = _now()

    source_id = str(result.raw.get("customer_id") or result.raw.get("card_id") or "unknown")
    total = data.get("total_cases", 0)
    fraud = data.get("fraud_cases", 0)
    exposure = data.get("total_exposure_usd", 0.0)

    items.append(Evidence(
        evidence_id=_next_id(),
        source_type=EvidenceSourceType.MCP_PRIOR_CASES,
        source_id=source_id,
        claim=f"Found {total} prior cases: {fraud} confirmed fraud, {total - fraud} cleared. Total exposure: ${exposure:.2f}",
        value={"total_cases": total, "fraud_cases": fraud, "exposure_usd": exposure},
        timestamp=ts,
        relevance="Prior confirmed fraud is a strong predictor of current fraud",
        retrieval_method="find_prior_cases",
    ))

    # Summarise patterns from prior cases
    pattern_counts: dict[str, int] = {}
    action_counts: dict[str, int] = {}
    for c in cases:
        p = c.get("pattern") or c.get("fraud_pattern", "")
        if p and p != "none":
            pattern_counts[p] = pattern_counts.get(p, 0) + 1
        a = c.get("actions_taken", "")
        if a:
            action_counts[a] = action_counts.get(a, 0) + 1

    if pattern_counts:
        top_pattern = max(pattern_counts, key=lambda k: pattern_counts[k])
        items.append(Evidence(
            evidence_id=_next_id(),
            source_type=EvidenceSourceType.MCP_PRIOR_CASES,
            source_id=source_id,
            claim=f"Most frequent historical fraud pattern: {top_pattern} ({pattern_counts[top_pattern]} cases)",
            value=top_pattern,
            timestamp=ts,
            relevance="Recurring fraud pattern indicates likely current pattern",
            retrieval_method="find_prior_cases",
        ))

    if action_counts:
        top_action = max(action_counts, key=lambda k: action_counts[k])
        items.append(Evidence(
            evidence_id=_next_id(),
            source_type=EvidenceSourceType.MCP_PRIOR_CASES,
            source_id=source_id,
            claim=f"Most frequent historical action taken: {top_action}",
            value=top_action,
            timestamp=ts,
            relevance="Historical action taken is a policy precedent signal",
            retrieval_method="find_prior_cases",
        ))

    return items


def _extract_detect_temporal_patterns(result: ToolResult) -> list[Evidence]:
    items: list[Evidence] = []
    signals_data = result.temporal_signals
    if not signals_data:
        return items

    customer_id = signals_data.get("customer_id", "unknown")
    signals = signals_data.get("signals", {})
    ts = _now()

    # Card testing signal
    if signals.get("card_testing"):
        micro = signals_data.get("micro_transaction_count", 0)
        items.append(Evidence(
            evidence_id=_next_id(),
            source_type=EvidenceSourceType.MCP_TEMPORAL_PATTERNS,
            source_id=customer_id,
            claim=f"Card testing signal detected: {micro} micro-transactions (< $5.00)",
            value=micro,
            timestamp=ts,
            relevance="Multiple small transactions are classic card testing behaviour",
            retrieval_method="detect_temporal_patterns",
        ))

    # Burst activity signal
    if signals.get("burst_activity"):
        window_count = signals_data.get("transactions_in_window", 0)
        window_h = signals_data.get("window_hours", 24)
        items.append(Evidence(
            evidence_id=_next_id(),
            source_type=EvidenceSourceType.MCP_TEMPORAL_PATTERNS,
            source_id=customer_id,
            claim=f"Burst activity: {window_count} transactions within {window_h}h window",
            value=window_count,
            timestamp=ts,
            relevance="Transaction bursts suggest rapid fraudulent use before card block",
            retrieval_method="detect_temporal_patterns",
        ))

    # Channel switching
    if signals.get("channel_switching"):
        online = signals_data.get("online_transaction_count", 0)
        inperson = signals_data.get("in_person_transaction_count", 0)
        items.append(Evidence(
            evidence_id=_next_id(),
            source_type=EvidenceSourceType.MCP_TEMPORAL_PATTERNS,
            source_id=customer_id,
            claim=f"Channel switching: {online} online + {inperson} in-person transactions",
            value={"online": online, "in_person": inperson},
            timestamp=ts,
            relevance="Mixed channel use can indicate account takeover or stolen credentials",
            retrieval_method="detect_temporal_patterns",
        ))

    # No fraud signals — negative evidence
    if not any(signals.values()):
        items.append(Evidence(
            evidence_id=_next_id(),
            source_type=EvidenceSourceType.MCP_TEMPORAL_PATTERNS,
            source_id=customer_id,
            claim="No temporal fraud signals detected (no card testing, no burst, no channel switch)",
            value=False,
            timestamp=ts,
            relevance="Absence of temporal signals reduces card_testing and burst_fraud probability",
            retrieval_method="detect_temporal_patterns",
        ))

    return items


def _extract_calculate_exposure(result: ToolResult) -> list[Evidence]:
    items: list[Evidence] = []
    data = result.exposure_data
    if not data:
        return items

    source_id = str(data.get("customer_id") or data.get("card_id") or "unknown")
    ts = _now()

    confirmed = data.get("total_confirmed_exposure_usd", 0.0)
    pending = data.get("pending_exposure_usd", 0.0)
    total = confirmed + pending

    items.append(Evidence(
        evidence_id=_next_id(),
        source_type=EvidenceSourceType.MCP_EXPOSURE,
        source_id=source_id,
        claim=(
            f"Financial exposure: ${confirmed:.2f} confirmed fraud + "
            f"${pending:.2f} pending = ${total:.2f} total"
        ),
        value={"confirmed_usd": confirmed, "pending_usd": pending, "total_usd": total},
        timestamp=ts,
        relevance="High exposure justifies disruptive actions like card block",
        retrieval_method="calculate_exposure",
    ))

    confirmed_cases = data.get("confirmed_fraud_cases", 0)
    if confirmed_cases:
        items.append(Evidence(
            evidence_id=_next_id(),
            source_type=EvidenceSourceType.MCP_EXPOSURE,
            source_id=source_id,
            claim=f"{confirmed_cases} confirmed fraud cases with total exposure ${confirmed:.2f}",
            value=confirmed_cases,
            timestamp=ts,
            relevance="Number of confirmed fraud cases strengthens BLOCK_CARD recommendation",
            retrieval_method="calculate_exposure",
        ))

    return items


def _extract_find_shared_devices(result: ToolResult) -> list[Evidence]:
    items: list[Evidence] = []
    data = result.customer_data
    customer_id = data.get("customer_id", "unknown")
    ts = _now()

    devices_shared = data.get("devices_shared_with_others", 0)
    shared_customers = data.get("total_shared_customer_count", 0)

    if devices_shared > 0:
        items.append(Evidence(
            evidence_id=_next_id(),
            source_type=EvidenceSourceType.MCP_SHARED_DEVICES,
            source_id=customer_id,
            claim=(
                f"Customer {customer_id} shares {devices_shared} device(s) "
                f"with {shared_customers} other customer(s)"
            ),
            value={"devices_shared": devices_shared, "other_customers": shared_customers},
            timestamp=ts,
            relevance="Shared devices are a strong fraud ring indicator",
            retrieval_method="find_shared_devices",
        ))
    else:
        items.append(Evidence(
            evidence_id=_next_id(),
            source_type=EvidenceSourceType.MCP_SHARED_DEVICES,
            source_id=customer_id,
            claim=f"Customer {customer_id} does not share devices with other customers",
            value=0,
            timestamp=ts,
            relevance="No shared devices reduces fraud ring probability",
            retrieval_method="find_shared_devices",
        ))

    return items


# ── Dispatch table ────────────────────────────────────────────────────────────

_EXTRACTORS = {
    "get_case": _extract_get_case,
    "get_customer_history": _extract_get_customer_history,
    "get_transaction_context": _extract_get_transaction_context,
    "find_connected_entities": _extract_find_connected_entities,
    "find_prior_cases": _extract_find_prior_cases,
    "detect_temporal_patterns": _extract_detect_temporal_patterns,
    "calculate_exposure": _extract_calculate_exposure,
    "find_shared_devices": _extract_find_shared_devices,
}


def extract_evidence(result: ToolResult) -> list[Evidence]:
    """
    Extract Evidence objects from a ToolResult.

    Every returned Evidence item has a source_type and source_id that
    traces back to an actual MCP tool call. Nothing is fabricated.

    Parameters
    ----------
    result : ToolResult
        Normalized output from an MCP tool adapter

    Returns
    -------
    list[Evidence]
        Extracted evidence items (may be empty if tool failed or returned nothing)
    """
    if not result.success:
        log.warning(f"Skipping evidence extraction for failed tool: {result.tool_name} — {result.error}")
        return []

    extractor = _EXTRACTORS.get(result.tool_name)
    if extractor is None:
        log.warning(f"No extractor for tool: {result.tool_name!r}")
        return []

    try:
        items = extractor(result)
        log.debug(f"Extracted {len(items)} evidence items from {result.tool_name}")
        return items
    except Exception as exc:
        log.error(f"Extractor for {result.tool_name!r} raised: {exc}")
        return []


def reset_counter() -> None:
    """Reset the evidence ID counter. Call at the start of each investigation."""
    global _COUNTER
    _COUNTER = 0
