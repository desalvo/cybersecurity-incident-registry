# RC75 — teaching terminology, linked documentation and AlBot identity

- Public-facing training slides use the meaning of the risk-for-rights-and-freedoms condition rather than the internal `personal_data` flag. That technical key remains unchanged in application logic, fixtures and authentic screenshots.
- Notification of the Italian data protection authority (Garante per la protezione dei dati personali) and communication to data subjects are subject to applicability and assessment, not automatic for every incident.
- Slide 3 explains **Continuous Improvement**, an additional reading of the acronym CI.
- First AlBot reference: **AlBot with an L, not AIBot**, from Alex. The existing, original cartoon avatar `app/static/ai-chatbot/albot-avatar.png` is restored to the modern application header and bot messages; the same asset remains on the training slide.
- The manual URLs chapter now links the stable, current training PDF at `docs/presentation/CIR_Operational_Training_Visual.pdf` and describes automatic full regeneration by CI after source changes.
- Source: `docs/presentation/visual_rc64_spec.json`; presentation builder: `scripts/build_training_visual_rc64.js`.
- CI browser capture is the authoritative source for screenshots; never fabricate screenshots for the published CI artifacts.

- Tenant slides now explain **Admin → Wizard setup iniziale** for tenant admins and super admins, with save/skip/restart sections and the restriction that creation of new tenants is reserved for super admins.


## Tenant initial configuration wizard - authentic CI capture

- Admin of the active tenant and super admin: `Admin` -> `Wizard setup iniziale` (`/admin/setup-wizard`).
- The wizard's actual status is persisted by the application; Save and continue, Skip, leave and return, and Restart from the beginning are verified using an authenticated demo tenant administrator.
- Creating/cloning tenants and editing the global local-admin password remain super-admin-only operations.
- New mandatory, SHA-256-verified Chromium evidence: `tenant-setup-wizard-desktop` (full wizard shell with step progress), `tenant-setup-wizard-panel` (legible form detail). The latter is linked into original slide 33 / displayed slide 41. Both are included in the complete PDF/PPTX screenshot appendices.
- Editorial decks built offline keep the approved thematic illustration with a clear note until authenticated screenshots are available; no synthetic screenshot is represented as real.
