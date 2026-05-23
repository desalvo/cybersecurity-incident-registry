# Risultati test conformità AGID

Generato: `2026-05-23T02:10:34.096513+00:00`
Esito complessivo: **PASS**

## Passi eseguiti

| Passo | Esito | Return code |
| --- | --- | ---: |
| `pip_check` | PASS | 0 |
| `compileall` | PASS | 0 |
| `pytest_all` | PASS | 0 |
| `pytest_agid_dynamic` | PASS | 0 |
| `bandit_json` | PASS | 0 |
| `bandit_threshold_high_medium` | PASS | 0 |
| `pip_audit_manual_docker_only` | PASS | 0 |

## Bandit

Finding per severità: HIGH=0, MEDIUM=0, LOW=29.

## Nota pip-audit

pip-audit is available only in the manual Docker compliance runner: compliance/agid/run_docker_agid_compliance.sh

## Evidenze prodotte

I file `.log`, `bandit.json`, `pip-audit.json` quando disponibile e `summary.json` nella stessa directory costituiscono le evidenze riproducibili del run.
