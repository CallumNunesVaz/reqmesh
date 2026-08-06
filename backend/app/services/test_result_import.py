"""CI test-result import — JUnit XML, CTRF JSON, and TAP format parsers.

Maps test results onto verification cases by matching test names against
VC IDs or names. Supports dry-run preview and live import.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime, timezone

import logging

logger = logging.getLogger("test_import")


@dataclass
class ParsedTestResult:
    name: str
    classname: str = ""
    status: str = "unknown"  # passed, failed, skipped, error
    duration_ms: float = 0
    message: str = ""
    output: str = ""


@dataclass
class ImportSummary:
    parsed: int = 0
    matched: int = 0
    updated: int = 0
    unmatched: int = 0
    errors: list[str] = field(default_factory=list)
    details: list[dict] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════════════
# Parsers
# ═══════════════════════════════════════════════════════════════════════════════


_DOCTYPE_RE = re.compile(rb"<!DOCTYPE", re.IGNORECASE)


def parse_junit_xml(content: bytes) -> list[ParsedTestResult]:
    """Parse JUnit XML (pytest, JUnit 4/5, TestNG)."""
    # Refuse a DTD outright, the same way the ReqIF importer does.
    # ElementTree ignores *external* entities (no XXE), but internal entity
    # definitions still expand: four nested ones turn a 289-byte upload into
    # 100 KB, six reach gigabytes. A JUnit report has no legitimate use for a
    # DOCTYPE, so rejecting it removes the amplification vector without adding
    # a parser dependency.
    if _DOCTYPE_RE.search(content):
        raise ValueError(
            "Test result file contains a DOCTYPE declaration, which is not "
            "accepted (entity expansion risk). Remove the DTD and retry."
        )

    # A DOCTYPE is rejected above, so internal entity expansion cannot reach
    # the parser; ElementTree already ignores external entities.
    root = ET.fromstring(content)  # nosec B314
    results: list[ParsedTestResult] = []

    for suite in root.iter("testsuite"):
        suite_name = suite.get("name", "")
        for case in suite.iter("testcase"):
            name = case.get("name", "")
            classname = case.get("classname", suite_name)
            time_s = float(case.get("time", "0"))

            status = "passed"
            message = ""

            failure = case.find("failure")
            error = case.find("error")
            skipped = case.find("skipped")

            if skipped is not None:
                status = "skipped"
                message = skipped.get("message", "") or (skipped.text or "")
            elif failure is not None:
                status = "failed"
                message = failure.get("message", "") or (failure.text or "")
            elif error is not None:
                status = "error"
                message = error.get("message", "") or (error.text or "")

            output = ""
            system_out = case.find("system-out")
            if system_out is not None and system_out.text:
                output = system_out.text

            results.append(ParsedTestResult(
                name=name, classname=classname, status=status,
                duration_ms=time_s * 1000, message=message, output=output,
            ))

    return results


def parse_ctrf_json(content: bytes) -> list[ParsedTestResult]:
    """Parse CTRF JSON (Playwright, Vitest, etc.)."""
    data = json.loads(content)
    results: list[ParsedTestResult] = []

    def _parse_suite(suite: dict, prefix: str = "") -> None:
        suite_name = suite.get("name", "")
        full_name = f"{prefix}{suite_name}"
        for test in suite.get("tests", []):
            name = test.get("name", "")
            status = test.get("status", "unknown")
            duration = float(test.get("duration", 0))
            message = ""
            if test.get("message"):
                message = test["message"]
            if test.get("trace"):
                message += "\n" + test["trace"]
            results.append(ParsedTestResult(
                name=name, classname=full_name, status=status,
                duration_ms=duration, message=message,
            ))
        for subsuite in suite.get("suites", []):
            _parse_suite(subsuite, f"{full_name}.")

    if "results" in data:
        data = data["results"]
    if "suites" in data:
        for suite in data.get("suites", []):
            _parse_suite(suite)
    elif "tests" in data:
        for test in data.get("tests", []):
            results.append(ParsedTestResult(
                name=test.get("name", ""), classname="",
                status=test.get("status", "unknown"),
                duration_ms=float(test.get("duration", 0)),
            ))

    return results


def parse_tap(content: str) -> list[ParsedTestResult]:
    """Parse TAP (Test Anything Protocol) output."""
    results: list[ParsedTestResult] = []
    current_class = ""
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("# suite:") or line.startswith("# class:"):
            current_class = line.split(":", 1)[1].strip()
            continue
        m = re.match(r"^(ok|not ok)\s+(\d+)\s*(.*?)(?:\s*#\s*(.*))?$", line)
        if m:
            status = "passed" if m.group(1) == "ok" else "failed"
            name = m.group(3).strip() or f"Test #{m.group(2)}"
            message = m.group(4) or ""
            results.append(ParsedTestResult(
                name=name, classname=current_class, status=status,
                message=message,
            ))
    return results


# ═══════════════════════════════════════════════════════════════════════════════
# Matcher — maps parsed test results to Verification Cases
# ═══════════════════════════════════════════════════════════════════════════════


# Shortest verification-case name eligible for fuzzy name matching. Below this
# a name is far more likely to be an incidental word in a test identifier than
# a deliberate reference to the case.
_MIN_NAME_MATCH = 4


def match_test_results(store, results: list[ParsedTestResult]) -> tuple[list[dict], list[ParsedTestResult]]:
    """Returns (matched_list, unmatched_list).

    A matched entry is ``{vc_id, vc_name, test_name, status, ...}``.
    """
    vcs = store.list_verification_cases()
    vc_by_id = {vc["id"]: vc for vc in vcs}
    vc_names = {vc.get("name", "").lower(): vc["id"] for vc in vcs if vc.get("name")}

    matched: list[dict] = []
    unmatched: list[ParsedTestResult] = []
    seen_vcs: set[str] = set()

    for tr in results:
        vc_id: str | None = None
        full_name = f"{tr.classname}.{tr.name}" if tr.classname else tr.name

        # 1. Direct ID match
        if tr.name in vc_by_id:
            vc_id = tr.name
        elif tr.classname and tr.classname in vc_by_id:
            vc_id = tr.classname

        # 2. VC ID appears anywhere in the test identifier. IDs are distinctive,
        #    so a bare substring is safe here — but take the *longest* match so
        #    the result doesn't depend on dict ordering when one id is a prefix
        #    of another (VCAF0001 vs VCAF00011).
        if not vc_id:
            candidates = [vid for vid in vc_by_id if vid in full_name or vid in tr.name]
            if candidates:
                vc_id = max(candidates, key=len)

        # 3. Fall back to the VC *name*, which is free text and needs care.
        #    This used to be a bare substring test taken in dict order, so a
        #    case named "Test" (or any short common word) claimed every
        #    incoming result and silently overwrote an unrelated case's
        #    verification status. Require a whole-word match and, again, prefer
        #    the longest — a name has to be a deliberate match, not a fragment.
        if not vc_id:
            haystack = full_name.lower()
            candidates = [
                (vc_name, vid) for vc_name, vid in vc_names.items()
                if len(vc_name) >= _MIN_NAME_MATCH
                and re.search(rf"(?<!\w){re.escape(vc_name)}(?!\w)", haystack)
            ]
            if candidates:
                vc_id = max(candidates, key=lambda c: len(c[0]))[1]

        if vc_id:
            vc = vc_by_id[vc_id]
            matched.append({
                "vc_id": vc_id,
                "vc_name": vc.get("name", ""),
                "test_name": tr.name,
                "test_class": tr.classname,
                "status": tr.status,
                "duration_ms": tr.duration_ms,
                "message": tr.message[:500] if tr.message else "",
                "vc_current_status": vc.get("status", "pending"),
                "is_new": vc_id not in seen_vcs,
            })
            seen_vcs.add(vc_id)
        else:
            unmatched.append(tr)

    return matched, unmatched


def import_test_results(store, results: list[ParsedTestResult], dry_run: bool = False) -> ImportSummary:
    """Match and import test results into verification cases."""
    summary = ImportSummary()
    summary.parsed = len(results)

    matched, unmatched = match_test_results(store, results)
    summary.matched = len(matched)
    summary.unmatched = len(unmatched)
    for u in unmatched:
        summary.details.append({
            "test_name": u.name, "test_class": u.classname,
            "status": "unmatched", "detail": "No matching verification case found",
        })

    for m in matched:
        vc_id = m["vc_id"]
        test_status = m["status"]
        # Map test statuses to VC statuses
        vc_status_map = {"passed": "passed", "failed": "failed", "error": "failed",
                         "skipped": "pending", "unknown": "pending"}
        new_vc_status = vc_status_map.get(test_status, "pending")

        if dry_run:
            summary.details.append({
                "vc_id": vc_id, "test_name": m["test_name"],
                "status": "dry_run", "detail": f"Would set status to '{new_vc_status}'",
            })
            continue

        try:
            vc = store.get_verification_case(vc_id)
            if not vc:
                summary.errors.append(f"VC {vc_id} not found during import")
                summary.details.append({
                    "vc_id": vc_id, "test_name": m["test_name"],
                    "status": "error", "detail": "VC not found",
                })
                continue

            execution_record = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "status": new_vc_status,
                "notes": f"[CI] {m['test_name']}: {m['status']}" +
                         (f" ({m['duration_ms']:.0f}ms)" if m["duration_ms"] else ""),
                "executed_by": "ci-import",
            }

            history = list(vc.get("execution_history") or [])
            history.append(execution_record)

            store.update_verification_case(vc_id, {
                "status": new_vc_status,
                "result": test_status,
                "execution_history": history,
            })

            summary.updated += 1
            summary.details.append({
                "vc_id": vc_id, "test_name": m["test_name"],
                "status": "imported",
                "detail": f"Status: {vc.get('status', '?')} → {new_vc_status}",
            })
        except Exception as exc:
            logger.exception("Failed to import test result for VC %s", vc_id)
            summary.errors.append(f"{vc_id}: {exc}")
            summary.details.append({
                "vc_id": vc_id, "test_name": m["test_name"],
                "status": "error", "detail": str(exc),
            })

    return summary


# ═══════════════════════════════════════════════════════════════════════════════
# Format detection
# ═══════════════════════════════════════════════════════════════════════════════


def detect_format(content: bytes) -> str:
    """Auto-detect test result format from content."""
    text = content.decode("utf-8", errors="replace").strip()

    if text.startswith("<?xml") or text.startswith("<testsuite") or text.startswith("<testsuites"):
        return "junit"
    if text.startswith("{") and ('"results"' in text or '"tests"' in text or '"suites"' in text):
        try:
            json.loads(text)
            return "ctrf"
        except (json.JSONDecodeError, ValueError):
            pass
    if re.match(r"^(ok|not ok)\s+\d+", text, re.MULTILINE):
        return "tap"

    return "unknown"


def parse_results(content: bytes, fmt: str = "auto") -> list[ParsedTestResult]:
    """Parse test results from content, auto-detecting format if needed."""
    if fmt == "auto":
        fmt = detect_format(content)
    if fmt == "junit":
        return parse_junit_xml(content)
    if fmt == "ctrf":
        return parse_ctrf_json(content)
    if fmt == "tap":
        return parse_tap(content.decode("utf-8", errors="replace"))
    raise ValueError(f"Unknown test result format: {fmt}. Supported: junit, ctrf, tap.")
