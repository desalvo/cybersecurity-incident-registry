# Cybersecurity Incident Registry (CIR)

**CIR** is a web application for recording, managing and documenting cybersecurity incidents from initial reporting to closure. It centralizes activities, evidence and operational traceability.

## Key features

- **Incident register:** Create, search, filter and manage incidents, evidence, attachments and action history.
- **Configurable workflows:** Operational steps, tasks, buttons, dependencies and procedures from opening through closure.
- **Multi-tenancy:** Separated tenants, roles, permissions, shared Tenants Default catalog and customizable imports.
- **Administration:** Initial setup wizard, users, LDAP and SSO/OAuth2 settings, taxonomies, notifications and SMTP.
- **Integrations:** Alfresco, import/export and optional AlBot AI assistant with authorization controls.
- **Interface:** Responsive layout, Italian/English localization and administrator-controlled modern/classic modes.

## Architecture and deployment

**Python/Flask** application served by **Gunicorn**, using **PostgreSQL** in production. Deployment guidance covers **Docker, Podman, Kubernetes and OpenShift**, including Helm. Integrations depend on configuration.

## Documentation

- [Deployment](docs/DEPLOYMENT.md)
- [Migration](docs/MIGRATION.md)
- [Training](docs/TRAINING.md)
- [Security](docs/SECURITY.md)
- [Release history](docs/RELEASE.md)
- [Testing and production](docs/TESTING_AND_PRODUCTION.md)
- [Handoff](docs/HANDOFF.md)
- [Historical README archive](docs/DEVELOPMENT_HISTORY_README_EN.md)

Version and build are recorded in [`VERSION`](VERSION) and [`BUILD`](BUILD). **Passing CI does not approve production:** verify OCI digest, security scans and risk acceptance before deployment.

Repository: https://github.com/desalvo/cybersecurity-incident-registry

[Italiano](README.md)
