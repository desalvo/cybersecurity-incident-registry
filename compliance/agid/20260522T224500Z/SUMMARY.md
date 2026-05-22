# Risultati test conformità AGID

Generato: `2026-05-22T22:41:23.153343+00:00`
Esito complessivo: **PASS**

## Passi eseguiti

| Passo | Esito | Return code |
| --- | --- | ---: |
| `pip_check` | PASS | 0 |
| `compileall` | PASS | 0 |
| `pytest_all` | PASS | 0 |
| `pytest_agid_dynamic` | PASS | 0 |
| `bandit_json` | FAIL | 1 |
| `bandit_threshold_high_medium` | PASS | 0 |
| `pip_audit_json` | FAIL | 125 |

## Bandit

Finding per severità: HIGH=0, MEDIUM=0, LOW=29.

## Nota pip-audit

pip-audit skipped by AGID_SKIP_PIP_AUDIT=1. Rerun in connected CI before production release.

## Evidenze prodotte

I file `.log`, `bandit.json`, `pip-audit.json` quando disponibile e `summary.json` nella stessa directory costituiscono le evidenze riproducibili del run.
