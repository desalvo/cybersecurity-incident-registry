# Testing, CI and production promotion

Testing and production evidence requirements for 0.9.0-1, including GitHub Actions, real PostgreSQL tests, SCA, multi-architecture builds, Trivy gates, immutable digest promotion and Docker Hub secrets.

## Source consolidation map

The historical source files listed below were consolidated into this document for Hotfix 7. They are no longer shipped as separate root-level Markdown files.

- `GITHUB_ACTIONS_RELEASE.md`

---

## Historical source: `GITHUB_ACTIONS_RELEASE.md`

La workflow `.github/workflows/ci-release.yml` automatizza la validazione e la pubblicazione della release CIR.

## Trigger

- Pull request: esegue tutti i gate applicativi, PostgreSQL, SCA e packaging, ma non pubblica immagini.
- Push su `main`: dopo tutti i gate costruisce e pubblica l'immagine multi-arch e, solo dopo il PASS Trivy, promuove il digest a `latest`.
- Push di un tag Git: dopo tutti i gate promuove il digest allo stesso tag, ad esempio il tag Git `0.9.0-1` produce `desalvo/cybersecurity-incident-registry:0.9.0-1`.

Il tag Git deve essere anche un tag Docker valido (`[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}`).

## Docker Hub secrets e variabili

Configurare in GitHub `Settings -> Secrets and variables -> Actions`:

- secret `DOCKERHUB_USERNAME`: username Docker Hub con permesso push;
- secret `DOCKERHUB_TOKEN`: access token Docker Hub, non la password dell'account;
- variable opzionale `CIR_DOCKER_REPOSITORY`: repository destinazione. Se assente usa `desalvo/cybersecurity-incident-registry`.

## Gate eseguiti

1. installazione delle dipendenze di test e `pip-audit`;
2. `python -m pip check`;
3. `python -m pytest -q`;
4. `./scripts/run_postgres_tests.sh` con PostgreSQL reale in Docker Compose;
5. `python scripts/verify_release_candidate.py`;
6. `python scripts/verify_security_gate_context.py`;
7. `./scripts/run_sca.sh`;
8. packaging smoke test con `scripts/package_release.sh`;
9. build multi-arch `linux/amd64,linux/arm64` con base image aggiornata e senza cache;
10. Trivy production gate CIR sul digest candidato esatto;
11. promozione dello stesso digest al tag finale solo dopo PASS.

I report SCA e Trivy vengono conservati come artifact GitHub Actions per 30 giorni.

## Strategia di pubblicazione fail-closed

La build viene prima pubblicata con un tag temporaneo `ci-<commit-sha>`. Il gate Trivy scansiona l'esatto digest OCI prodotto. Solo se entrambe le piattaforme superano la policy viene creato il tag finale (`latest` o il tag Git) sul medesimo digest. Un candidato che fallisce non modifica quindi il tag production.

I tag `ci-*` sono evidenza tecnica e possono essere rimossi dal registry in base alla retention policy scelta per Docker Hub.

## Risk acceptance temporanea Debian

La workflow usa `TRIVY_RISK_ACCEPTANCE_R8.json`. L'allowlist resta fail-closed: Python HIGH/CRITICAL, nuovi CVE OS, CVE fuori dallo scope di package approvato, CVE con `FixedVersion` disponibile o acceptance scaduta bloccano la promozione.

La disposition aggiunta il 20 settembre 2026 per i CVE util-linux/systemd scade il 20 ottobre 2026 e dipende dall'hardening runtime verificato da `scripts/verify_security_gate_context.py`.

---

## Automatic production-digest recording

For a push to `main`, the production workflow is self-closing after all quality, PostgreSQL, SCA and Trivy gates pass. The candidate OCI index is promoted to `latest`, the registry is re-inspected, and the published digest must exactly match the approved candidate digest. Only then does CI run `scripts/record_production_digest.py` to update `PRODUCTION_IMAGE_DIGEST` and `k8s/kustomization.yaml`, verify the resulting production metadata, and commit those two files back to `main` as `github-actions[bot]`.

The digest-recording step uses the workflow's standard `GITHUB_TOKEN` with job-scoped `contents: write`; no personal access token is required. Pushes made with that token do not recursively start another `push` workflow, so the metadata commit does not rebuild the image it just recorded. Tag-triggered releases never write back to `main`: they publish and report their tag digest only.

Repository/organization Actions policy must permit `GITHUB_TOKEN` write access, and branch protection must allow the Actions bot to push this metadata commit. If either policy forbids the push, the workflow fails rather than silently claiming that repository metadata was updated. The push is non-forced, so a concurrent change to `main` also fails safely instead of overwriting it.
