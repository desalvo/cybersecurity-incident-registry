#!/usr/bin/env python3
"""Create JSON and Markdown summaries for AGID compliance test runs."""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def read_status(path: Path) -> list[dict[str, object]]:
    rows = []
    status_file = path / "status.tsv"
    if not status_file.exists():
        return rows
    for line in status_file.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        name, rc = line.split("\t", 1)
        rows.append({"step": name, "return_code": int(rc), "passed": int(rc) == 0})
    return rows


def bandit_counts(path: Path) -> dict[str, int] | None:
    bandit_file = path / "bandit.json"
    if not bandit_file.exists():
        return None
    try:
        data = json.loads(bandit_file.read_text(encoding="utf-8"))
    except Exception:
        return None
    metrics = data.get("metrics", {}).get("_totals", {})
    return {
        "high": int(metrics.get("SEVERITY.HIGH", 0)),
        "medium": int(metrics.get("SEVERITY.MEDIUM", 0)),
        "low": int(metrics.get("SEVERITY.LOW", 0)),
    }


def main() -> int:
    out_dir = Path(sys.argv[1]).resolve()
    overall_rc = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    status = read_status(out_dir)
    bandit = bandit_counts(out_dir)
    generated_at = datetime.now(timezone.utc).isoformat()
    summary = {
        "generated_at_utc": generated_at,
        "overall_passed": overall_rc == 0,
        "steps": status,
        "bandit_severity_counts": bandit,
        "notes": [
            "pip-audit requires access to Python package vulnerability metadata; offline failures are environment limitations and must be rerun in a connected CI environment.",
            "Dynamic tests use an isolated SQLite database and Flask test client; production deployments must also be checked with DAST/container/infrastructure scans.",
        ],
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    lines = [
        "# Risultati test conformità AGID",
        "",
        f"Generato: `{generated_at}`",
        f"Esito complessivo: **{'PASS' if overall_rc == 0 else 'FAIL'}**",
        "",
        "## Passi eseguiti",
        "",
        "| Passo | Esito | Return code |",
        "| --- | --- | ---: |",
    ]
    for row in status:
        lines.append(f"| `{row['step']}` | {'PASS' if row['passed'] else 'FAIL'} | {row['return_code']} |")
    if bandit is not None:
        lines.extend([
            "",
            "## Bandit",
            "",
            f"Finding per severità: HIGH={bandit['high']}, MEDIUM={bandit['medium']}, LOW={bandit['low']}.",
        ])
    note = out_dir / "pip-audit-note.txt"
    if note.exists():
        lines.extend(["", "## Nota pip-audit", "", note.read_text(encoding="utf-8").strip()])
    lines.extend([
        "",
        "## Evidenze prodotte",
        "",
        "I file `.log`, `bandit.json`, `pip-audit.json` quando disponibile e `summary.json` nella stessa directory costituiscono le evidenze riproducibili del run.",
    ])
    (out_dir / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # Also print a compact terminal summary so manual/CI runs show the
    # result immediately without opening the generated report files.
    print("\nAGID compliance summary")
    print("=======================")
    print(f"Results directory: {out_dir}")
    print(f"Overall result: {'PASS' if overall_rc == 0 else 'FAIL'}")
    print("")
    print("Test results:")
    for row in status:
        print(f"- {row['step']}: {'PASS' if row['passed'] else 'FAIL'} (rc={row['return_code']})")
    if bandit is not None:
        print(f"- bandit severity counts: HIGH={bandit['high']}, MEDIUM={bandit['medium']}, LOW={bandit['low']}")
    if note.exists():
        note_text = note.read_text(encoding="utf-8").strip()
        if note_text:
            print("- pip-audit note: " + note_text.splitlines()[0])
    print(f"Human-readable report: {out_dir / 'SUMMARY.md'}")
    print(f"Machine-readable report: {out_dir / 'summary.json'}")
    print("")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
