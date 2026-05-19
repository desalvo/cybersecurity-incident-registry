# cybersecurity-incident-registry

Flask/Gunicorn application for a cybersecurity incident registry backed by PostgreSQL.

## Version 0.2.1-9 - Platform consolidation and bilingual documentation

Version 0.2.1-9, build 2026051901, consolidates recent platform developments: Italian/English interface, restructured user and administrator documentation, anti-flooding audit with retention and purge, deadline notification scheduler with cron/interval planning, per-incident scheduled reminders, professional PDF reports, multiple SSO/OAuth2 profiles with shared logos, optional HTTPS/SSL access and mobile usability improvements.

Operational guides are maintained in both languages. Release notes are separated from the operational documentation and are available from the Help menu.

## Production hardening build 2026051901

This build introduces an application security baseline for production use:

- automatic CSRF protection for all `POST`, `PUT`, `PATCH` and `DELETE` forms, with server-side hidden-field injection in rendered HTML templates;
- browser security headers: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, `Permissions-Policy` and HSTS when HTTPS is active or `CIR_FORCE_HSTS=1`;
- session cookies are `HttpOnly`, `SameSite=Lax` and `Secure` when `CIR_PRODUCTION=1` or `SESSION_COOKIE_SECURE=1`;
- upload size limit controlled by `MAX_CONTENT_LENGTH`, default 25 MiB;
- fail-fast production validation: with `CIR_PRODUCTION=1` the application rejects weak `SECRET_KEY` values, weak bootstrap admin passwords and SQLite databases;
- the notification/reminder scheduler uses a PostgreSQL advisory lock, so it is safe with multiple Gunicorn workers or Kubernetes replicas;
- `docker-compose.yml` no longer contains hardcoded secrets and requires a `.env` file derived from `.env.example`.

Secure startup preparation:

```bash
cp .env.example .env
# change POSTGRES_PASSWORD, DATABASE_URL, SECRET_KEY and ADMIN_INITIAL_PASSWORD
docker compose up --build
```


## Environment variables and container operations

A dedicated guide, `docs/CONTAINER_ENVIRONMENT_en.md`, has been added. It describes every environment variable used by the container, persistent volumes, Docker Compose startup, Kubernetes secrets, internal HTTPS, Gunicorn tuning, notification/reminder scheduler, backup and container upgrade operations.

The online administrator documentation includes the same operational content in summarized form: in production always prepare `.env` from `.env.example`, set `DATABASE_URL`, `SECRET_KEY`, `ADMIN_INITIAL_PASSWORD`, `POSTGRES_PASSWORD`, enable `CIR_PRODUCTION=1` and mount `UPLOAD_DIR`, `LOGO_DIR`, `FORM_TEMPLATE_DIR`, `SSO_LOGO_DIR` and `SSL_DIR` on persistent storage.

## Local startup

```bash
docker compose up --build
```

Open `http://localhost:8000`. The initial local user is `admin`; the initial password is taken from `ADMIN_INITIAL_PASSWORD` only when the user is created for the first time. It is not reset on later restarts.


### SSO documentation and figure update

The user documentation now integrates SSO/OAuth2 access into the access chapter, explaining the flow from the user perspective, provider selection, redirection to the external identity system and what to do in case of login errors. The incident-detail figure was updated so all main-card text remains inside its frame.

The administrator documentation now integrates shared SSO/OAuth2 logo management into the SSO profile chapter, including persistent storage configured through `SSO_LOGO_DIR`, default logos, upload, per-profile selection, removal, export/import and the need to back up persistent storage.

## Main features

- Configurable maximum number of recommendations selectable per incident in Admin → Recommendations, default 3.

- Persistent PostgreSQL database.
- Local login, configurable LDAP authentication with user filter, and configurable SSO/OAuth2/OpenID Connect login from the Admin interface.
- Roles: admin, operator, reader, writer, disabled.
- Drag-and-drop management of categories, affected data, personnel and recommendations, with drop targets next to the palettes.
- Contextual online help on the incident detail page for the main fields and sensitive procedural information.
- Document upload and download.
- CSV export, full compressed export with all real database fields, professional PDF incident reports with wrapped tables and an action-over-time chart.
- Idempotent seed with PostgreSQL lock to avoid duplicate keys and `WORKER_BOOT_ERROR`.
- PBKDF2-SHA256 password hashes with SHA256 pre-hash to avoid the historical bcrypt 72-byte limit.

## SSO / OAuth2 login

Administrators can configure federated login from **Admin → SSO**. The configuration includes:

- enabling or disabling SSO login;
- provider name shown on the login page;
- authorization endpoint, token endpoint and UserInfo endpoint;
- client ID and client secret;
- OAuth2/OpenID Connect scopes, default `openid email profile`;
- claim names used for username, email, display name and unique identifier;
- automatic creation of SSO users and default role, default `disabled`;
- optional provider logo, displayed on the login button when present. Shared logos uploaded from the UI are stored in the persistent directory configured by `SSO_LOGO_DIR`, default `/data/sso_logos`, not in the container's ephemeral static area.

The redirect URI to register on the provider is shown in **Admin → SSO**. The same page includes **Check configuration**, which validates the values currently present in the form even before saving and checks mandatory parameters, authorization endpoint, token endpoint, UserInfo endpoint, scopes and main claims. The check is non-destructive: it does not create users and does not complete a real login. A full test is available through **Start interactive login test**, which uses the standard OAuth2 redirect flow. Local and LDAP login remain available. Automatically created SSO users can be enabled or promoted from **Admin → Users**. The application account identity is always the **username + backend** pair: the same username may therefore exist at the same time as a local, LDAP and SSO/OAuth2 account, including different SSO profiles, without overwriting roles, MFA settings or preferences of the other accounts. Administrators can create local or LDAP accounts even when the same username already exists on another backend. The users table shows a readable login type: for SSO/OAuth2 accounts it also displays the provider name and profile id, while keeping the technical backend (`local`, `ldap`, `sso:<profile id>`) underneath. This makes users with the same username but different SSO providers immediately distinguishable, because the **username + backend** pair identifies the actual application user. Administrators can also remove accounts that are no longer needed from **Admin → Users**. Deletion removes the account and its MFA tokens, while incidents, reminders and audit records are preserved by detaching the technical user reference. The interface prevents deleting the currently signed-in administrator and prevents deletion of the last remaining administrator.

### Persistent SSO logo storage

Shared SSO/OAuth2 profile logos uploaded from **Admin → SSO** are stored outside `app/static`, in the directory configured through the `SSO_LOGO_DIR` environment variable. The default is `/data/sso_logos`. In production containers this path must be mounted on persistent storage; `docker-compose.yml` defines the `sso_logos` named volume and the Kubernetes manifests define the `cir-sso-logos` PVC.

On startup the application copies the default provider logos shipped with the image into the persistent directory only when they are missing. Full export includes the files stored in `SSO_LOGO_DIR` and full import restores them to the same persistent area.

## Kubernetes

Apply the manifests in `k8s/` after publishing the container image.

## Container build

```bash
docker build --no-cache -t cybersecurity-incident-registry:latest .
docker compose up --build
```

The image is based on Debian Trixie through `python:3.12-slim-trixie`. Native runtime dependencies required by PostgreSQL, ReportLab, Matplotlib and the healthcheck are installed with `apt`; Python dependencies are installed from binary wheels where possible. The package includes `.dockerignore` to avoid copying local files into the build context.

## Application information

- Name: Cybersecurity Incident Registry
- Version: 0.2.1-9
- Build: 2026051901
- Author: Alessandro De Salvo <Alessandro.DeSalvo@roma1.infn.it>

The information is visible from **Info → Application** and can be configured through the environment variables `APP_NAME`, `APP_VERSION`, `APP_BUILD`, `APP_AUTHOR`, `APP_AUTHOR_EMAIL`.

## CSIRT/DPO notifications

The detail page of each incident includes a **Notifications** section with **Notify CSIRT** and **Notify DPO** buttons. A message preview is shown before sending. Sending uses the sender associated with the logged-in user, attaches the current incident PDF report and automatically adds an action to the incident with label:

- `04-comunicazione allo CSIRT` for CSIRT;
- `05-comunicazione al DPO` for DPO.

From **Notifications**, an administrator can configure:

- CSIRT and DPO email addresses;
- SMTP parameters;
- separate CSIRT and DPO templates;
- automatic deadline reminders for actions.

Templates support the placeholders `%DATA%`, `%CATEGORIES%`, `%PERSONAL_DATA%`, `%REPORT%`, `%DOCUMENTS%`, `%ACTIONS%`, `%MEASURES_ADOPTED%`, `%INCIDENT_URL%`, `%SITE%`, `%STATISTICS%` and the other fields shown in the template configuration page. The direct incident link is inserted only through `%INCIDENT_URL%`; `%STATISTICS%` attaches the PDF statistics report.

### Automatic action deadline reminders

Action labels managed in **Admin → Configurable lists** provide the numeric field **Maximum time (hours)**, expressed in hours and defaulting to 0, and the field **Exportable by default**. A value of 0 means that the label has no deadline and is not considered by reminders. If the value is greater than zero, the system treats the action as an activity to be completed within that number of hours starting from the first **initial information** action of the incident.

Notification settings include:

- enabling or disabling automatic reminders;
- checking interval in hours and minutes;
- immediate manual execution of the check;
- global enabling or disabling of email sending for deadline reminders.

At every check, for each open non-muted incident, the application looks for action labels with a configured maximum time that are not yet present in the incident timeline. If email sending is enabled and missing actions exist, an email is sent only when at least one personnel entry with a valid email address is associated with the incident. If no personnel is selected, the incident is skipped and no email is sent. From the incident detail page, **Mute email notifications for deadline tasks** excludes only that incident from automatic reminders.

The deadline email template is configurable with subject and body fields. Placeholders use `%placeholder_name%` syntax and include `%incident_name%`, `%incident_reference%`, `%incident_status%`, `%initial_information_at%`, `%pending_actions%`, `%pending_actions_count%`, `%recipients%`, `%generated_at%`, `%application_name%`, `%external_url%`, `%report%` and `%statistics%`. The preview button generates a demonstration preview and does not send email. If `%report%` or `%statistics%` is present, the message attaches respectively the incident report PDF or the statistics PDF generated at sending time.

All deadline notification dates and times are formatted in the application time zone configured in **Admin → Other settings**. The time zone name is included in the notification text to avoid operational ambiguity.

## Incidents and action lifecycle

The incident form uses separate date and time fields for the start and end of the incident. Existing databases are migrated automatically from the historical `start_at` and `end_at` columns to the granular `start_date`, `start_time`, `end_date`, `end_time` fields. Compatibility properties remain available for reports and filters.

In the incident detail page, the **Actions** section pre-fills the action date/time with the current time computed in the configured application time zone. When an action whose label, label description or free text contains “conclusione” is added or updated, the incident is automatically moved to the closed state and its end date/time is aligned with the action date/time.

Before generating filled PDF forms, the application validates all incident fields used by the mappings of the selected templates. If one or more values are missing, generation is blocked and the user receives a grouped message listing the fields to complete, by template and PDF field.

The **Procedural warnings** section is displayed near the top of the incident detail page, immediately after the main incident card, so pending checks and required notifications are visible before the lower operational sections.

## PDF forms

The application uses the original uploaded PDF template to generate filled PDFs. The form field names are the AcroForm field names extracted from the uploaded PDF. Template configuration maps database fields to PDF fields, while preserving the original PDF as the generation source.

The full export includes PDF templates both as physical files and as persistent binary copies in the database, together with field mappings and detected PDF field metadata. A template PDF can be replaced only if the new PDF contains exactly the same fillable AcroForm fields as the previous one; in that case the template name, field mapping, configured font and size are preserved.

Available PDF mapping fields include incident data, granular date/time fields, administrative data such as security owner, security owner role, structure and security responsible information, and the calculated fields derived from the first initial-information action.

## Full export and import

The full export includes:

- all application tables configured in the current data model;
- all real columns of each table, including settings, users, roles, LDAP/SSO, TOTP MFA, notifications, labels, categories, incidents, actions, recommendations and templates;
- all many-to-many relation tables;
- incident documents and action attachments;
- PDF form templates both as physical files and as persistent binary database copies;
- the configured custom logo and static application logos;
- an export manifest with schema information and a `_coverage` section to verify what is included.

Binary database values are serialized as Base64 inside the JSON manifest. Full import rebuilds the database, settings, files, templates and logos.

The `audit_log` table and all settings stored in `setting` are included in full export and full import. After a full import, imported audit records older than the configured retention are removed automatically.

## Audit log

The application records user operations, notification scheduler operations and automated task operations in the `audit_log` table. Each entry stores date/time, operation type, username, user identifier where available, actor type and essential technical details.

Audit retention is configured in **Admin → Other settings** through four fields: months, days, hours and minutes. The default is 6 months. If all fields are set to zero, the application restores the 6-month default to avoid a null retention period. Cleanup is centralized in `purge_audit_logs()` and is triggered after successful mutating user requests, after the deadline notification scheduler check and at the end of full import.

The **Admin → Audit** page is visible only to administrators. It displays the current retention and cutoff and allows administrators to search audit entries by free text, operation type, username, actor type and date/time interval. Results are ordered from newest to oldest and limited to 500 rows.

## Configurable lists and exportable actions

In **Admin → Configurable lists → Action labels**, the **Maximum time (hours)** column explicitly states that the deadline unit is hours. The **Exportable by default** field controls the default value of the `exportable` flag when a new incident action is created with that label. The flag remains editable on each individual action.

## Contextual messages and menus

In the incident edit page, operation results and errors are displayed in the operational section that generated them: main incident data, actions, documents or form generation. For example, a PDF generation error remains visible inside **Form generation**, while an action validation error remains inside **Actions**.

The **Forms** menu is displayed only when the current user has privileges for at least one item inside the menu; otherwise the menu is hidden and no empty dropdown is shown.

## Language and documentation

The web interface and the user and administrator documentation are available in Italian and English. By default the language follows the browser locale: Italian for Italian locale, English for all other locales. An administrator can force `auto`, `it` or `en` from **Admin → Other settings → Interface language**.

The Italian package README remains `README.md`. The English counterpart is `README_en.md`. Both files must be kept aligned whenever functional, configuration or deployment documentation changes. Operational requests may continue to be provided in Italian; the corresponding English UI and documentation text must be updated at the same time.

The package also includes `docs/PROJECT_DESIGN.md`, which describes the logical architecture, data model, application flows, authorization rules, notification system, export/reporting functions and a complete textual specification for rebuilding the application while preserving the current build features.

## Help

The **Help** menu provides **User documentation**, **Administrator documentation** and **Release notes**. Direct PDF download entries are not shown in the menu; each page provides its own PDF download button. The selected language follows the resolved interface language.

## PostgreSQL 18.4 note

Docker Compose and Kubernetes manifests mount the persistent PostgreSQL volume on `/var/lib/postgresql`, as required by the `postgres:18.4` image. The actual data directory is managed by the official image inside the volume, avoiding permission or initialization problems caused by directly mounting `/var/lib/postgresql/data`.

## Recent updates

### 0.110-95 - English README

- Added `README_en.md` as the English counterpart of `README.md`.
- The bilingual maintenance policy now explicitly includes the package README files.
- User, administrator and project documentation updated.

### 0.110-94 - IT/EN internationalization

- Bilingual Italian/English web interface.
- Automatic language from browser locale: Italian for Italian locale, English for all others.
- New **Admin → Other settings → Interface language** option with automatic, Italian and English modes.
- User and administrator documentation available in Italian and English, including PDF pages.
- `interface_language` is included in application settings and therefore in full export/import.

### 0.110-93 - Maximum time in hours and time zone in deadline notifications

- Action-label column renamed to **Maximum time (hours)**.
- Automatic deadline notifications format all dates and times in the application time zone configured in **Admin → Other settings**.

### 0.110-92 - Configurable exportable default on action labels

- Added **Exportable by default** to action labels.
- New incident actions initialize `Action.exportable` from the selected label configuration.
- The `ConfigLabel.default_exportable` column is migrated automatically and included in full export/import.

### 0.110-91 - Procedural warnings at the top of incident detail

- The incident detail page displays **Procedural warnings** near the top, immediately after the main incident card.

### 0.110-90 - Granular audit retention and configuration layout

- Audit retention is expressed in months, days, hours and minutes, default 6 months.
- Audit cleanup uses the complete configured period.
- The **Save configuration** button in **Admin → Other settings** has a maximum height of 1 cm.

### 0.110-89 - Searchable audit, full export/import and retention

- Full export/import includes `audit_log` and all settings.
- Centralized audit retention cleanup.
- New **Admin → Audit** page for administrators, with search and filters.

### 0.110-88 - Contextual errors, audit log and dynamic Forms menu

- Incident detail operation messages are displayed in the corresponding operational section.
- Added `audit_log` table and automatic operation logging.
- The **Forms** menu is hidden when it would be empty.


### 0.110-96 - User-notification warning wording

In incident **Procedural warnings**, the user-notification item is now worded as **User notification required**. The new wording clarifies that the procedural step is required and remains pending until the matching action is recorded.

### Incident PDF reports: Documents section

In incident PDF reports, the **Documents** table gives more space to the document name column and reduces the width reserved for the upload date and time. The upload date/time is formatted as `YYYY-MM-DD HH:MM:SS`; seconds are always shown as integer values and fractional seconds or microseconds are not displayed.

### 0.110-97 - PDF report documents

The Documents section in incident PDF reports now uses a more compact upload date/time column and assigns more space to the document name. Upload timestamps are normalised as `YYYY-MM-DD HH:MM:SS`, without microseconds and with seconds always shown as integer values.
## Update 0.1.0-98 - Incident PDF reports: times and duration

In incident PDF reports, all textual date/time values are normalised as `YYYY-MM-DD HH:MM:SS`: seconds are always integer values and fractional seconds or microseconds are never displayed. The report summary section now also includes **Duration**, when available, calculated with the same rule used by the application main page: the interval between the first recorded action and the incident closing date/time.
## Update 0.1.0-99 - Incident PDF reports: professional layout

Incident PDF reports have been reformatted with a more professional presentation: the beginning of the document shows the application logo and, when configured, the GUI-uploaded logo without textual labels. A concise table of contents follows. Section titles use a highlighted style and are kept on the same page as their related content, avoiding orphan headings at the bottom of a page. The footer includes page numbering.

## Update 0.1.0-100 - Incident PDF reports: logos

Incident PDF reports no longer show the **custom logo** wording on the first page. The static application logo remains present; the logo uploaded from the GUI is shown, when available, as an additional application logo. If no GUI logo has been uploaded, that slot is omitted from the PDF.


## Update 0.1.0-101 - Incident PDF reports: logo image rendering

Incident PDF reports now render first-page logos as actual images. The static SVG application logo is internally converted to a temporary PNG before being added to the PDF, preventing SVG metadata or fallback text from appearing instead of the image. The logo area no longer prints textual labels below the images; the GUI-uploaded logo is still omitted when it is not configured or unavailable.

## Update 0.1.0-102 - Incident PDF reports: application logo and uploaded logo

Incident PDF reports now insert the application logo using the application PNG asset already used by the documentation as the primary source, with SVG conversion only as a fallback. This prevents text from appearing in the PDF and prevents the application logo from being omitted. The GUI-uploaded logo continues to appear next to the application logo when configured and present on the filesystem; when no GUI logo has been uploaded, only the application logo is shown.

## Update 0.1.0-103 - Deadline notification scheduler and grouped Admin menu

Periodic deadline notifications no longer depend on incoming web requests. At application startup, a lightweight internal scheduler checks periodically whether the interval configured in **Admin → Notifications** has elapsed and, when due, runs the same check used by the manual button. The technical polling interval can be configured with the `CIR_DEADLINE_SCHEDULER_POLL_SECONDS` environment variable and can be disabled with `CIR_ENABLE_DEADLINE_SCHEDULER=0` for deployments that prefer an external job. Every effective run writes an `audit_log` record with operation type `scheduler:deadline_notification_check`, actor `scheduler`, execution source, checked incidents, sent messages, skipped messages and errors.

The **Admin** menu has been reorganised into collapsible subgroups: general configuration, master data and workflow, users and access, control and audit. This reduces menu height and makes all administration entries easier to view on smaller screens.

## 0.1.0-104 - Next deadline notification run and midnight-based scheduling

The **Settings → Notifications** page now shows a **Estimated next send** section for automatic deadline task reminders. It displays whether the automatic check is enabled, whether email sending is enabled, the effective interval in minutes, the reference midnight in the application time zone, the current schedule slot, the last automatic execution and the estimated next send date and time.

The scheduler no longer computes intervals from the application startup time. Execution slots are always multiples of the configured interval starting from midnight of the current day in the time zone configured in **Admin → Other settings**. For example, with a 4-hour interval, the slots are 00:00, 04:00, 08:00, 12:00, 16:00 and 20:00. The manual button still runs the check immediately without changing the automatic schedule.

## Incident-specific reminders

Each incident now includes a **Specific reminders** section where users with write permissions can schedule, edit, and delete one-off reminders for exact dates and times. The message is defined by the user, the primary recipients are automatically the personnel associated with the incident that have an e-mail address, and additional CC addresses can be configured.

The scheduler sends every due, one-off reminder that has not been sent yet. After an application restart, all missed one-off reminders are recovered by comparing the reminder status with the audit records for sent reminders. Periodic deadline-task notifications remain deduplicated by type/interval: when multiple slots are missed, only the latest due notification for that type is executed.

Full export/import now includes the incident-specific reminder table and preserves the audit history for automated sends.


## Update 0.1.0-106 - Incident closing, paginated audit and direct links in notifications

Manual or automatic incident closing is now blocked when active procedural warnings are still present. The blocking message is shown in the section where the operation was requested: the main incident data section for manual closing, and the Actions section for automatic closing through a conclusion action.

The **Admin → Audit** page now uses pagination. The default number of records per page can be configured in **Admin → Other settings** through **Audit records per page**, with default 20 and maximum 100. The top of the Audit page shows the current total number of audit records, the filtered record count and the currently selected interval.

For manual/non-scheduled incident notifications, the direct link to the specific incident page is inserted only when the template contains the `%INCIDENT_URL%` placeholder. Deadline-task templates continue to support `%incident_url%` separately. General templates also support `%MEASURES_ADOPTED%` (list of countermeasures adopted so far in the incident), `%SITE%` (structure name configured in Admin → Structure) and `%STATISTICS%`, which requests the generated statistics PDF attachment at send time.

### Update 0.1.0-107

- The **Specific reminders** section in the incident detail page now uses a responsive card layout: on smartphones, date/time, message, CC, status and actions remain visible and editable without horizontal overflow.
- **Audit** records now store and display concise, readable details limited to the essential operational information, avoiding long or unclear payloads.

### Update 0.1.0-108 - Cron-style deadline task notifications

Automatic deadline task notifications now use a cron-style schedule in addition to regular intervals. In **Admin → Notifications**, administrators can choose **Regular interval** or **Cron / specific times**. In cron mode, daily times can be entered as `HH:MM`, separated by commas, spaces, or new lines; interval-based slots remain available and are always calculated from midnight in the application timezone. The scheduler does not use the application start time as the reference. If the application restarts after one or more missed slots, only the latest due periodic slot is executed and the outcome is recorded in the audit table. The page also shows configured slots, current slot, estimated next run and last automatic execution.

The sending logic has been reviewed: the internal scheduler keeps running independently from web traffic and records SMTP errors and delivery summaries in audit. For manual notifications, the direct link is controlled by the template and is replaced only through `%INCIDENT_URL%`; scheduled notifications continue to use `%incident_url%`.

### Update 0.1.0-109
- The Admin menu grouped into collapsible subsections now always loads with all submenus closed by default, improving readability when reloading or changing pages.

### Update 0.1.0-110

Fixed the deadline-task notification scheduler. The automatic check no longer treats a cron/interval slot as permanently completed just because the first poll found no pending tasks: deduplication is now performed per incident and per scheduled slot. If the scheduler starts before pending tasks become detectable, later polls in the same slot can still send the notifications. Pending-task detection is separated from recipient validation: incidents without assigned staff or e-mail addresses are counted and logged as skipped instead of being reported as no pending task. Successful sends also create a `scheduler:deadline_notification_sent` audit entry with incident, slot and recipients.

### Update 0.1.0-111 - Deadline notification scheduler audit

The automatic deadline notification check still uses a frequent technical poll, but global `scheduler:deadline_notification_check` audit records are now written only in two cases: when notifications are actually sent, or once for the scheduled cron/interval slot when notifications would have been sent, even if no due tasks were found. Intermediate polls within the same slot no longer create repeated audit records. Successful deliveries continue to write the incident-and-slot-specific `scheduler:deadline_notification_sent` record.

### Update 0.1.0-112 - Documentation formatting
User and administrator documentation, both online and PDF, has been revised to prevent titles or text from overflowing cards. The illustrative images for the recommended workflow, main page, incident detail and module configuration have been regenerated with text wrapping and wider spacing. The main-page screenshot no longer has the “New incident” button overlapping the title. Documentation CSS includes stronger responsive and wrapping rules for desktop and mobile layouts.

### Audit anti-flooding and release notes

The audit log collapses consecutive identical records by incrementing the `Occurrences` field instead of creating many identical rows. When 100 occurrences are reached, a new record is written and the counter restarts. Update summaries are available from **Help → Release notes**, with the PDF downloadable from inside that page, separate from the operational documentation.

### Audit: maximum records, manual purge and CSV

The `Admin → Audit` page includes the maximum audit row configuration, defaulting to 10000 records. The automatic purge applies both time-based retention and the maximum row limit, deleting the oldest records first. The same page supports manual purge by number of records to keep or by cutoff date, and can export the current filtered audit view as CSV.

## Update 0.1.0-117 - Deadline notification deduplication within the same schedule window

Automatic deadline-task notifications now keep a persistent last-success state for each incident summary notification. Before sending a new email, the scheduler checks the window between the current scheduled slot and the next one: if the same notification type for the same incident was already successfully sent in that window, the message is skipped. This prevents repeated messages during the pause between two consecutive schedules, even with repeated technical polls or application restarts. Successful sends are still audited and update the `deadline_notification_state` table, which is included in full export/import.


## Update 0.1.0-118 - Multiple SSO/OAuth2 profiles

Federated SSO/OAuth2/OpenID Connect login now supports multiple profiles that can be configured and enabled at the same time from **Admin → SSO**. Each profile has a technical ID, provider name, enabled/disabled status, authorization/token/userinfo endpoints, client ID, client secret, scopes and claim mapping.

On the login page, when complete active SSO profiles exist, one button is shown for each provider so users can choose which SSO provider to use. The redirect URI is common and is displayed in Admin → SSO. Automatically created SSO users receive the default role configured for the selected profile; the recommended default remains `disabled` so administrators can enable them later.

The **Add Google example** button pre-fills a Google OpenID Connect profile with:

- Authorization endpoint: `https://accounts.google.com/o/oauth2/v2/auth`;
- Token endpoint: `https://oauth2.googleapis.com/token`;
- UserInfo endpoint: `https://openidconnect.googleapis.com/v1/userinfo`;
- scopes: `openid email profile`;
- claims: `email`, `email`, `name`, `sub`.

Then enter the Client ID and Client secret obtained from the Google console and register the redirect URI shown by the application. SSO profiles are stored in application settings and included in full export/import.

## Update 0.1.0-119 - SSO/OAuth2 profiles: HTTPS callback and generic profile

SSO/OAuth2 profile configuration now always generates and uses a redirect/callback URI with the `https://` scheme, even when the application receives internal HTTP traffic behind a reverse proxy or container network. **Save SSO profile** and **Check configuration** no longer ask for delete-style confirmation; confirmation is limited to actual profile deletion.

**Admin → SSO** now also provides **Add generic profile**, in addition to the Google example, to create an empty OAuth2/OpenID Connect profile that can be completed with the endpoints of the chosen Identity Provider.


## Update 0.1.0-120 - Optional HTTPS/SSL access

The container now also exposes port 8443 for optional HTTPS/SSL access. HTTP port 8000 always remains available, and a missing SSL configuration or missing certificates never prevents the application from starting.

Configuration can be provided through Docker Compose or Kubernetes environment variables: `SSL_ENABLED`, `SSL_PORT`, `SSL_DIR`, `SSL_CERT_FILE` and `SSL_KEY_FILE`. Alternatively, an administrator can use the new **Admin → HTTPS/SSL** page to enable or disable HTTPS access and upload the host certificate and private key in PEM format. If HTTPS is enabled but the certificate or private key is missing, the HTTPS listener remains disabled while HTTP access keeps working.

Full export/import includes SSL certificates uploaded from the web interface, so the complete application configuration remains restorable.


## Documentation - 0.1.0-121

User and administrator documentation has been reorganised into clearer chapters with procedures, checklists, examples and improved layout to prevent text from overflowing boxes in online and PDF versions.

## Update 0.1.0-122

- The user documentation now shows application version, build and author in the guide page.
- It clarifies that only actions marked as exportable are considered when generating documents and dynamic PDF form fields.
- The administrator documentation was refined in the SSO and HTTPS/SSL chapters.
- The Admin → Audit page displays, filters and exports date/time values in the application configured timezone.


## Update 0.2.0-4.2 - Uploaded SSO logo preview

The **Admin → SSO/OAuth2** page, in the **SSO logo storage** section, now displays a graphical preview for logos uploaded by administrators through the web interface. Previews no longer point to the container static area; they use the `/sso-logos/<filename>` application route, which reads from the persistent directory configured through `SSO_LOGO_DIR`. As a result, default logos copied on first startup and user-uploaded logos are rendered consistently in the storage list, profile selection area and login page.



## Update 0.2.0-125 - User identities by username and backend

User management now supports distinct identities with the same username as long as they belong to different authentication backends. A local `mario.rossi`, an LDAP `mario.rossi` and a `mario.rossi` coming from SSO profile `institution` are three separate application accounts, each with independent role, MFA status, audit relation and enablement state. SSO profiles use technical backends in the `sso:<profile id>` format. The PostgreSQL migration removes the former unique constraint on username alone and introduces the composite `username + auth_provider` constraint.

## Update 0.1.0-124 - SSO/OAuth2 profile logos

Each SSO/OAuth2 profile configured from **Admin → SSO** can have an optional logo selected from the shared SSO logo storage. The logo is shown in the configured profiles table and, when the profile is active, on the SSO button in the login page. The storage includes Google, Facebook and Apple logos by default, supports uploading additional logos and allows logos to be removed when no longer needed. Removing a logo automatically clears the association from SSO profiles that used it. All SSO logos are included in full export/import together with the profile configuration.


### Update 0.1.0-125
- SSO buttons on the login page are light grey.
- Shared SSO logo storage also supports logo removal.
- When a logo is removed, it is automatically cleared from associated SSO profiles.


## Update 0.2.0-126 - SSO login type distinguished by provider

In **Admin → Users**, the **Login type** column no longer shows only the technical backend for SSO accounts. Each SSO user also shows the configured provider name and profile id, for example `SSO/OAuth2 · Central institution (institution)` with technical backend `sso:institution`. The user creation menu also includes configured SSO profiles, allowing administrators to pre-create or enable an identity for a specific provider without confusing it with local, LDAP or other SSO providers returning the same username.


## Update 0.2.0-10 - Manual notification placeholders and explicit incident link

Manual/non-scheduled notifications no longer append the direct incident link automatically: the link appears only when the template contains `%INCIDENT_URL%`. The placeholders `%MEASURES_ADOPTED%`, `%SITE%` and `%STATISTICS%` were added; `%STATISTICS%` attaches the statistics PDF. The user documentation clarifies that the local `admin` user cannot send notifications from the incident page: these notifications must be sent while logged in as another authorised user.


## Update 0.2.0-11 - Manual notification placeholder fix

Fixed notification sending from the **Notifications** section of the incident detail page: placeholder values are now always normalised to text before being substituted into the template. In particular `%MEASURES_ADOPTED%`, which uses the same data source as the `measures_adopted` field used for form filling and may be calculated as a list of lines, is converted into a multiline text list. This removes the `TypeError: replace() argument 2 must be str, not list` error when pressing the notification button. The rule applies to all manual/non-scheduled notification placeholders: missing values become an empty string, lists/tuples/sets become newline-separated lines and other values are converted to strings.

### Notification templates, document attachments and external recipients

Manual notification templates can optionally be linked to a PDF form template. When sending from an incident, documents generated from that form template are preselected automatically, while the operator can still add other attachments or deselect the proposed ones. If the expected document is missing, a non-blocking warning is shown. The **Admin → External recipients** address book feeds recipient/CC fields, and new emails used during sending are saved after asking for the recipient name.


## Update 0.112-12 - Multiple document tags for notifications

In the incident document list, each file can be associated with one or more notification types. Tags are assigned through drag & drop: drag an available notification type onto the document tag area, remove individual tags when needed, and save the change. When sending a manual notification, documents tagged with the selected notification type are automatically preselected as attachments. This preselection is never mandatory: the operator can always deselect suggested documents or select other incident documents. Preselection of documents generated from the form template linked to the notification template remains supported.


## Update 0.2.1-2 - External recipient selection in manual notifications

For manual/non-scheduled notifications with user-editable recipients that are not locked by application settings, the send preview now shows an explicit picker from **Admin → External recipients**. The operator can select a contact with both name and e-mail and use it as the main recipient or append it to CC; manually typed new addresses remain supported and are added to the shared address book after the recipient name is provided.

## Update 0.2.1-1 - Automatic tags on generated forms

When a PDF form is generated from the incident detail page and attached as a document, the application automatically assigns at least the notification-type tags of the notification templates linked to the form template used for generation. This makes the newly generated document automatically preselected during the next notification send of the corresponding type, while the operator can always manually change the attachment selection before sending.

The application version is updated to **0.2.1-1**, build **2026051901**.

## Update 0.2.1-4 - External recipient management from Settings

Non-administrator users with the `writer` role, therefore allowed to write and edit incidents but not to access the Admin menu, can now fully manage the **External recipients** address book from **Settings → External recipients**. The page allows adding, editing and deleting contacts used by manual/non-scheduled notifications with free recipient or CC fields. Administrators continue to manage the same shared address book from **Admin → External recipients**.

## Update 0.2.1-5 - Operational workflows by incident category

The incident detail page now shows, at the top of the form, the list of operations expected until closure. Operations already recorded through incident actions are highlighted as completed, while missing operations are highlighted separately. From **Admin → Incident operational workflows** administrators can configure a default workflow and category-specific workflows. Each step uses a configurable action label, may have a dedicated operational description and has a numeric order. If an incident has multiple categories, workflows are merged and duplicates are removed; if no selected category has a workflow, the default workflow is used.

## Update 0.2.1-9 - Incident workflows with descriptions, deadlines and editable default flow

The incident detail page now uses the task description configured in the action list as the workflow-step caption when available, falling back to the task name. The description configured on the specific workflow step remains available as an additional operational note, so the same action can be reused multiple times with different meanings.

For steps based on tasks with a maximum completion time, the application shows the limit, due time and remaining time only while the step has not yet been completed; if the remaining time is less than or equal to zero, the missing step is highlighted as critical. The calculation uses the same logic already used for scheduled deadline notifications. The initial default workflow is: Initial information, Analysis, CSIRT notification, DPO notification and Closure. All steps, including default-workflow steps, can be added, edited or deleted from **Admin → Incident operational workflows**.

## Update 0.2.1-9 - Clickable workflow and procedural warnings placement

- In the incident detail page the **Procedural warnings** section is now displayed immediately below **Expected operations**, so missing activities and procedural checks are visible before the main incident form.
- Workflow step cards are clickable: selecting a step automatically scrolls to the **Actions** section and prepares the form with the action label associated with the selected step.
- The user can still change date/time, person, description, consequences and attachments before saving the action.


### Configurable application backups
The **Admin → Backup** menu provides central management for scheduled and on-demand backups. Selectable categories are: incidents as CSV, application database, templates, logos and uploads. All categories are selected by default; when all are enabled the archive is an application full backup consistent with the full export. Supported destinations are local POSIX filesystem, S3/compatible storage and downloadable file for on-demand backups only. Scheduled backups use a five-field cron-like syntax and are disabled by default. Optional e-mail notifications can be sent to the admin user for success or failure.
