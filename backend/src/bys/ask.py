"""Answers are built from the report already on the page.

A language model is not required. If one is configured, its text is kept
only when it does not add a claim this evidence cannot support.
"""

from __future__ import annotations

import os
import re
from typing import Any

import httpx

BANNED = (
    "safe",
    "unsafe",
    "compliant",
    "compliance",
    "no violations",
    "no concerns",
    "enough reserves",
    "adequately reserved",
    "will flood",
    "will not flood",
    "won't flood",
)

ABSTAIN_TOPICS = (
    "reserve",
    "special assessment",
    "hoa budget",
    "solvent",
    "structurally sound",
    "mold",
    "code violation",
    "lien",
)


def answer_question(question: str, report: dict[str, Any]) -> dict[str, Any]:
    text = (question or "").strip()
    lowered = text.lower()
    if any(topic in lowered for topic in ABSTAIN_TOPICS):
        return _abstain(text, report)
    if "ignore previous" in lowered or "you are now" in lowered:
        text = "What public records are available for this property?"
        lowered = text.lower()
    findings = report.get("findings") or []
    if "how many" in lowered and "permit" in lowered:
        drafted = _count_permits(findings)
    elif "flood" in lowered:
        drafted = _about(findings, "Flood hazard designation", "flood")
    elif "permit" in lowered:
        drafted = _about(findings, "Permit history", "permit")
    else:
        drafted = _overview(report)
    drafted = _maybe_phrase(drafted)
    _require_known_citations(drafted["answer"], drafted["citations"])
    if _has_banned_claim(drafted["answer"]):
        drafted = _overview(report)
        drafted["limitations"].append("A drafted sentence was discarded because it added a claim the records do not support.")
    return drafted


def _overview(report: dict[str, Any]) -> dict[str, Any]:
    prop = report["property"]
    citations = []
    lines = [
        f"{prop.get('address')} is folio {prop.get('folio')} in {prop.get('municipality') or 'a municipality that was not determined'}."
    ]
    identity = _first(report["findings"], "identity:")
    if identity:
        citations.append(_cite("c1", identity))
        lines[0] += " [c1]"
    permit_findings = [row for row in report["findings"] if row["theme"] == "Permit history"]
    if permit_findings:
        citations.append(_cite("c2", permit_findings[0]))
        lines.append(
            f"{len(permit_findings)} published permit record(s) are attached to this folio or its parent folio. [c2]"
        )
    else:
        lines.append("No published permit finding is attached to this property in the current report.")
    flood = _first(report["findings"], "flood:")
    if flood:
        citations.append(_cite("c3", flood))
        lines.append(f"{flood['what']} [c3]")
    lines.append("This is not a safety judgment, a legal opinion, or a statement that missing records mean a clean property.")
    return {
        "answer": " ".join(lines),
        "citations": citations,
        "limitations": _limits(report),
        "abstained": False,
        "provider": "template",
    }


def _count_permits(findings: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [row for row in findings if row["theme"] == "Permit history"]
    unit = [row for row in rows if row.get("attribution") == "unit_folio"]
    parent = [row for row in rows if row.get("attribution") == "parent_folio"]
    citations = [_cite(f"c{index}", row) for index, row in enumerate(rows[:8], start=1)]
    markers = " ".join(f"[{item['citation_id']}]" for item in citations)
    answer = (
        f"{len(rows)} published permit records are on this report. "
        f"{len(unit)} carry the unit folio and {len(parent)} carry the parent parcel folio. "
        "Records without a permit number are not included in this count."
    )
    if markers:
        answer += " " + markers
    return {
        "answer": answer,
        "citations": citations,
        "limitations": ["This count is the published rows on this report, not every record a building department might hold."],
        "abstained": False,
        "provider": "template",
    }


def _about(findings: list[dict[str, Any]], theme: str, prefix: str) -> dict[str, Any]:
    rows = [row for row in findings if row["theme"] == theme or row["id"].startswith(prefix)]
    if not rows:
        return {
            "answer": "The current report has no published finding on that point. That is not the same as a clean result.",
            "citations": [],
            "limitations": ["No matching evidence was in the package for this property."],
            "abstained": True,
            "provider": "template",
        }
    citations = [_cite(f"c{index}", row) for index, row in enumerate(rows[:6], start=1)]
    parts = [f"{row['what']} [{item['citation_id']}]" for row, item in zip(rows[:6], citations, strict=True)]
    return {
        "answer": " ".join(parts),
        "citations": citations,
        "limitations": [row["why"] for row in rows[:2]],
        "abstained": False,
        "provider": "template",
    }


def _abstain(question: str, report: dict[str, Any]) -> dict[str, Any]:
    return {
        "answer": (
            "I can't answer that from the records on this property. "
            "Association budgets, reserve studies, inspection reports, and code-enforcement cases "
            "are not in this report. Ask the seller or association for those documents."
        ),
        "citations": [],
        "limitations": [
            "Insufficient evidence. A fluent guess would not be a finding.",
            f"Question set aside: {question[:180]}",
        ],
        "abstained": True,
        "provider": "template",
    }


def _cite(citation_id: str, finding: dict[str, Any]) -> dict[str, Any]:
    return {
        "citation_id": citation_id,
        "finding_id": finding["id"],
        "label": finding["title"],
        "source_name": finding["source_name"],
        "source_record_id": finding.get("source_record_id"),
        "url": finding.get("source_url"),
    }


def _first(findings: list[dict[str, Any]], prefix: str) -> dict[str, Any] | None:
    return next((row for row in findings if row["id"].startswith(prefix)), None)


def _limits(report: dict[str, Any]) -> list[str]:
    limits = ["Answers use only the findings already retrieved for this property."]
    text = (report.get("property") or {}).get("limitations")
    if text:
        limits.append(text)
    return limits


def _require_known_citations(answer: str, citations: list[dict[str, Any]]) -> None:
    used = set(re.findall(r"\[(c\d+)\]", answer))
    known = {item["citation_id"] for item in citations}
    unknown = used - known
    if unknown:
        raise ValueError(f"citation not in evidence package: {sorted(unknown)}")


def _has_banned_claim(answer: str) -> bool:
    lowered = answer.lower()
    return any(re.search(rf"\b{re.escape(phrase)}\b", lowered) for phrase in BANNED)


def _maybe_phrase(drafted: dict[str, Any]) -> dict[str, Any]:
    if os.environ.get("BYS_USE_OLLAMA") != "1":
        return drafted
    model = os.environ.get("OLLAMA_MODEL", "qwen3.5:2b")
    url = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
    prompt = (
        "Rewrite the answer in plain sentences. Do not add facts. "
        "Keep every [cN] marker. Do not say a building is safe, compliant, or free of violations.\n\n"
        + drafted["answer"]
    )
    try:
        response = httpx.post(
            f"{url}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
            timeout=20,
        )
        response.raise_for_status()
        text = (response.json().get("response") or "").strip()
    except (httpx.HTTPError, ValueError):
        return drafted
    if not text or _has_banned_claim(text):
        return drafted
    try:
        _require_known_citations(text, drafted["citations"])
    except ValueError:
        return drafted
    drafted = {**drafted, "answer": text, "provider": "ollama"}
    return drafted
