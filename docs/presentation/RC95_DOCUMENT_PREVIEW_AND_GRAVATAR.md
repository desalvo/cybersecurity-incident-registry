# CIR 0.10.0-1 RC95: anonymized PDF teaching example and optional Gravatar

## Training

The user-approved anonymized version of the INFN personal-data-breach
notification is stored at
`docs/presentation/rc95_user_supplied/data_breach_notification_anonymized.png`.
Its expected SHA-256 is
`17898ab5874ae15ded91a0c8f2d022402eac9f6c5d212bd72b24dd213965a9ce`.

The PptxGenJS source `scripts/build_training_visual_rc64.js` inserts the approved
image into the teaching PDF-preview example and the dedicated appendix preview
slide. It is **an anonymized teaching example**, not a screenshot obtained from
CIR. In same-run CI builds, the authentic generated mapped-PDF raster remains
visible next to the teaching example on the appendix page and is independently
verified by the browser manifest. The actual `pdf-generated-preview` browser
capture remains in the complete screenshot gallery. The verification script
pins the approved asset digest and continues to validate the CI screenshots.

## Profile avatars

`/admin/interface` now exposes a global `Gravatar` switch, stored as the
physical `Setting` key `global_gravatar_enabled`. An absent setting means
**enabled** on both new and upgraded databases. Only a super administrator can
change it. The change is audited as `admin:global_gravatar_update`.

When enabled and the signed-in user has a nonempty email, the account header
in the modern or classic UI requests an avatar from
`https://secure.gravatar.com/avatar/{lowercase_trimmed_email_md5}?s=80&d=404&r=g`.
The raw email address is never inserted into the image URL. If the URL returns
404 or cannot be loaded, initials are retained (modern UI) or no icon is
shown (classic UI). If disabled, no Gravatar URL is rendered. HTTPS and
`referrerpolicy="no-referrer"` are used. The default CSP allows only the
fixed secure Gravatar image origin; custom CSPs remain administrator-controlled.

**Privacy:** enabling the feature causes the user's browser to contact an
external service and disclose its IP address and an email-derived hash.
Administrators may switch it off for environments where that is unsuitable.
