# RC48 visual training notes

The 80-slide deck uses editable vector diagrams and structured Arial bullet text.
The workflow lifecycle and tenant/global distinction were checked against app/workflow_lifecycle.py, app/tenant_defaults_views.py, app/route_modules/tenancy.py and app/tenant_default_settings.py.

Global/shared keys: ssl_enabled, ssl_cert_path, ssl_key_path, application_external_url, application_timezone, max_upload_size_mb, setup_wizard_progress_json, setup_wizard_completed and global_ui_mode. Some are bootstrap/internal values rather than everyday editable fields.

Tenant-scoped administrative areas: lists, workflows, incident templates, notifications, external recipients, backups, AI plugins and knowledge base. Explicit local overrides take precedence over inherited defaults.

Only superusers may change catalog workflow lifecycle; tenant administrators with admin authorization may change their own tenant workflow status. Obsolescence propagates from default catalog source to installed copies, but reactivation of source does not automatically reactivate local copies. Existing incidents retain their workflow.

Screenshots of SPAM live browser sessions have not been acquired in this package. The vector diagrams are illustrative and must not be represented as CI-attested screenshots.
