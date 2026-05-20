# cybersecurity-incident-registry




Flask/Gunicorn application for a cybersecurity incident registry backed by PostgreSQL.

## Application state

The operational documentation describes the current state of platform 0.2.1, build 2026051901. Chronological changes are maintained in Release notes and in `CHANGELOG.txt`, not in the user or administrator guides.

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
- Version: 0.2.1
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

The **Procedural warnings** section is displayed immediately below **Expected operations**. It lists the applicable workflow steps marked as required that have not yet been completed, using the step description when available or otherwise the task description/name.

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

The scheduler sends every due one-off reminder whose `sent_at` field is still empty. After an application restart, all missed one-off reminders are recovered from the reminder status itself, without applying the type/interval block used by periodic notifications. A temporary technical claim still prevents simultaneous sends of the same reminder record, but it does not suppress other one-off reminders in the same period. Periodic deadline-task notifications remain deduplicated by type/interval: when multiple slots are missed, only the latest due notification for that type is executed.

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

## Release notes

Version changes are collected in `CHANGELOG.txt` and in **Help → Release notes** inside the application. Operational guides keep only current usage instructions.


## Update 0.2.1-35 - Notification scheduler, anti-flooding and time zone

Scheduled notifications for maximum-time tasks are now more robust against simultaneous duplicate sends. Before sending, the scheduler persistently claims the notification slot for each incident; if another worker or replica tries to send the same notification in the same interval, the send is skipped. Each scheduler cycle also cleans up stale notification states left by deleted incidents.

All schedules, cron times and maximum-task intervals are interpreted in the application time zone configured under **Admin → Other configurations**. Regular intervals always start from midnight of the current day in that time zone, not from container or process startup time.

### Workflow step descriptions and clickable URLs

In **Admin → Incident workflows** the procedural step description is multiline and limited to 500 characters. In the incident detail page, `http://` and `https://` URLs included in the step text are rendered as clickable links; clicking the rest of the card still starts the guided workflow behaviour.

### Update 0.2.1-37 - Serial notification scheduler

Scheduled notifications are no longer sent from the web-request hook: automatic delivery is handled only by the dedicated scheduler thread. Scheduled emails are sent sequentially. Deadline summaries keep their persistent type/window claim, while one-off reminders use `sent_at` as the only functional delivery flag and a temporary claim only for concurrency protection, so different reminders in the same period are not suppressed.

## Update 0.2.1-40 - Audit for incidents skipped by the notification scheduler

Whenever the notification scheduler skips an incident, a dedicated audit record is now written with the affected incident and the skip reason. Periodic deadline notifications use `scheduler:deadline_notification_skipped`; incident-specific reminders use `scheduler:incident_reminder_skipped`. Details include the scheduler source, schedule slot or planned reminder time, reason code and readable reason, so **Admin → Audit** can distinguish already-sent notifications, concurrent claims, missing recipients/SMTP errors and application exceptions.
