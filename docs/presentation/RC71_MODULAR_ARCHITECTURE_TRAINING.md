# CIR 0.10.0-1 RC71 — Modular architecture and process engine training

This editorial revision follows RC70 and introduces no functional changes to the application.

- Cover: expand **CIR** visibly as **Cybersecurity Incident Registry** in a different accent color.
- Slide 5: summarize incident management and general configurable process capabilities.
- Slide 6: describe the modular application architecture, data persistence and optional integrations.
- Insert after original slide 6: explain the two currently registered optional plugins: `ai_chatbot` (AlBot, engines ChatGPT, Claude, Gemini, Ollama and Perplexity) and `alfresco` (document repository integration). SSO, SMTP notifications, PDF templating and reporting are core integrations/capabilities, not additional plugin packages.
- Second insertion: explain CIR as a generic procedural workflow manager with step order, conditions, dependencies, mandatory activities, cross-step/global validation, timing, deadline notifications and incident reminders.
- Original slide 35: super admins configure the entire instance and tenants; tenant admins configure permitted tenant-specific items; operators follow rather than administer rules.

Editorial design: native editable PowerPoint right-column diagrams accompany two people-free synthetic photographic artworks. Their SHA-256 provenance is in `visual_rc71_art/provenance.json`. The original user-interface screenshots remain original source captures; no new UI screenshots are fabricated.

## Source confirmation

- `app/__init__.py` registers only the AI Chatbot and Alfresco plugin packages.
- `app/plugins/ai_chatbot/engines/__init__.py` enumerates the five AI providers.
- `app/models.py` defines workflow conditions, required flags and action maximum completion hours.
- `app/templates/notification_settings.html` exposes interval/cron scheduling and incident reminders.
- `app/routes.py` implements tenant role checks for administration and incident operations.

## Verification

The editorial PDF contains 87 pages, corresponding to 87 PPTX slides. The media integrity verifier, dedicated regressions and PowerPoint out-of-bounds checks are expected to pass before CI release. The PR's remote CI must still be executed.
