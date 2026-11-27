# RC100: 3-D statistics bubbles and structured exports

The Italian presentation specification is the authoritative training source.
The English PPTX/PDF are regenerated from it; only the slides' native, editable
text and diagrams are translated. Illustrative bubble counts are *synthetic*.

## Scope and grouping

- Active tenant is the default for everyone, including global super admins.
- Only global super admins may choose `all` and `per_tenant` or see the dedicated
  cross-tenant 3-D bubble dashboard, grouped as `tenant`, `category`, or
  `tenant_category`.
- 30 visible bubbles by default; the limit can be set to 1–100. The table is
  not truncated. Counts are sorted descending and ties are sorted by name.
- Multi-category incidents contribute once to each selected category group;
  the total across category groups may therefore exceed the number of incidents.
- No network calls, graphics libraries, or external chart endpoints are needed.
  Bubbles use local HTML/CSS, a colored radial gradient and depth shadows.

## Exports and passwords

Endpoint `POST /reports/stats.export` accepts `scope` (`tenant`, `all`,
`per_tenant`), `mode` (`tenant`, `category`, `tenant_category`), `format`
(`json`, `xml`, `csv`), optional ISO date filters, and `encrypt=1` with a
password of at least 12 characters. Tenant authorization and CSRF are enforced
before any export; only aggregated count rows are included. Backwards-compatible
PDF/CSV/JSON routes remain available. The new XML GET route is
`/reports/stats.xml` and JSON grouped data API is
`/reports/stats.aggregates.json`.

Encrypted files use the transparent `cir-statistics-encrypted-v1` envelope:
PBKDF2-HMAC-SHA256 (600,000 iterations, random 16-byte salt) derives a 256-bit
AES-GCM key; a random 12-byte nonce, ciphertext and authentication tag are
stored as base64. The output remains unreadable without the password. Neither
password nor key is persisted, included in URLs or written to logs.

To decrypt:

```bash
python scripts/decrypt_statistics_export.py cir-statistics-xml.enc.json statistics.xml
```

The script prompts for a password without echo and writes mode `0600`, refusing
to overwrite a destination. For noninteractive connectors, pipe a password over
stdin with `--password-stdin` rather than including it on the command line.
Consumers should validate the XML/JSON schema before ingestion. Store the
password in an approved secret manager, never alongside the exported file.

## Presentation

The existing statistics slide (Italian master, original source index 24) now
shows an editable six-bubble 3-D illustration with imaginary incident counts
across tenants and categories. The bilingual generators produce that same
teaching example, localized in English. It is **not** a production or CI capture.
