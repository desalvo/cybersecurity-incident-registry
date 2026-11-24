# Legacy form-template cleanup (0.10.0-1 RC39)

At application bootstrap, before the initial Tenants Default seed, CIR examines form-template configurations. A configuration is eligible for removal only if its PDF is absent both from the binary table and from the configured form-template directory, and no operational reference is found in the mapped application tables' reference-bearing text/JSON fields. Field mappings owned by that template are internal dependent configuration, not evidence of operational use.

For eligible configurations, CIR removes the configuration and its mappings within the **same bootstrap transaction**, and adds an `AuditLog` entry (`operation_type=legacy_template_cleanup`) containing the name, ID, mapping count and reason. No files are deleted. On failure, the bootstrap transaction is rolled back, including audit and cleanup. Repeated startups are idempotent.

If references are found, CIR **does not delete** the configuration. It emits `CIR-DATA-002` with the reference source; an eligible cleanup emits `CIR-DATA-001`. Both appear in Kubernetes container logs. The admin can inspect committed events in the existing audit log; no new administration page is claimed for this iteration.

This is a generalized rule for legacy **form templates**, not an unrestricted garbage collector for incidents, documents, audit records or other regulated data. The check uses known mapped reference-bearing columns and cannot establish the absence of references in external integrations or unmodeled data. Take and verify a PostgreSQL backup before rollout, and initially run one application replica. Do not use this cleanup as a substitute for backup or incident-data retention policies.

Normal portable import/export validation remains strict. No placeholder PDF is generated and no custom name is hardcoded. CI must verify bootstrap on real PostgreSQL and the existing dataset before production deployment.
