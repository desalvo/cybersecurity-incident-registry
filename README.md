# Cybersecurity Incident Registry (CIR)

**CIR** è un’applicazione web per registrare, gestire e documentare incidenti di sicurezza informatica, dall’apertura alla chiusura. Centralizza le attività, le evidenze e la tracciabilità operativa.

## Funzionalità principali

- **Registro incidenti:** Creazione, ricerca, filtri, schede incidente, evidenze, allegati e cronologia delle azioni.
- **Workflow configurabili:** Step operativi, task, pulsanti, dipendenze e procedure di apertura e chiusura.
- **Multi-tenancy:** Tenant separati, ruoli, permessi, catalogo condiviso Tenants Default e importazioni personalizzabili.
- **Amministrazione:** Wizard iniziale, utenti, configurazioni LDAP e SSO/OAuth2, tassonomie, notifiche e SMTP.
- **Integrazioni:** Alfresco, import/export e assistente AI opzionale AlBot con controlli di autorizzazione.
- **Interfaccia:** Layout responsive, italiano/inglese, modalità moderna o classica impostata globalmente.

## Architettura e installazione

Applicazione **Python/Flask** servita tramite **Gunicorn**, con **PostgreSQL** in produzione. Le guide coprono **Docker, Podman, Kubernetes e OpenShift**, oltre a Helm. Le integrazioni dipendono dalla configurazione.

## Documentazione

- [Deployment](docs/DEPLOYMENT.md)
- [Migration](docs/MIGRATION.md)
- [Training](docs/TRAINING.md)
- [Security](docs/SECURITY.md)
- [Release history](docs/RELEASE.md)
- [Testing and production](docs/TESTING_AND_PRODUCTION.md)
- [Handoff](docs/HANDOFF.md)
- [Historical README archive](docs/DEVELOPMENT_HISTORY_README_IT.md)

Versione e build sono registrate in [`VERSION`](VERSION) e [`BUILD`](BUILD). **Il superamento dei test non equivale all’approvazione production:** verificare digest OCI, scansioni e risk acceptance prima del deployment.

Repository: https://github.com/desalvo/cybersecurity-incident-registry

[English](README_en.md)
