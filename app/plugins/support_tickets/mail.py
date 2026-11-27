"""Professional, self-contained HTML mail for support ticket notifications."""
from html import escape


def ticket_email_html(ticket, event_label, url, status, priority):
    ref = escape(ticket.reference)
    subject = escape(ticket.subject)
    event = escape(event_label)
    safe_url = escape(url, quote=True)
    tenant = escape(ticket.tenant.name if ticket.tenant else 'CIR')
    return f'''<!doctype html><html lang="it"><head><meta charset="utf-8"><title>{ref} Support Tickets</title></head>
<body style="margin:0;padding:28px;background:#eef3f9;font:15px Arial,sans-serif;color:#172d49">
<table role="presentation" cellpadding="0" cellspacing="0" width="100%" style="max-width:640px;margin:auto;background:#fff;border-radius:18px;overflow:hidden">
<tr><td style="background:#152c54;padding:26px 30px;color:white">
<span style="font-size:12px;letter-spacing:2px;color:#91ddfb;font-weight:bold">CIR · SUPPORT TICKETS</span>
<h1 style="margin:12px 0 0;font-size:26px">{event}</h1></td></tr>
<tr><td style="padding:30px"><div style="display:inline-block;background:#e7f3fc;color:#18578a;padding:8px 12px;border-radius:20px;font-weight:bold">{ref}</div>
<h2 style="font-size:21px;margin:17px 0">{subject}</h2>
<p style="color:#64748b">Tenant destinatario: <strong>{tenant}</strong></p>
<table role="presentation" width="100%" style="margin:20px 0"><tr>
<td style="background:#edf7fe;padding:14px;border-radius:12px">Stato<br><strong>{escape(status)}</strong></td>
<td style="width:8px"></td>
<td style="background:#fff5e7;padding:14px;border-radius:12px">Priorità<br><strong>{escape(priority)}</strong></td></tr></table>
<a href="{safe_url}" style="display:inline-block;background:#087fa8;color:#fff;text-decoration:none;padding:14px 22px;border-radius:10px;font-weight:bold">Apri il ticket in CIR</a>
<p style="font-size:13px;color:#64748b;margin-top:26px">Accedi con il tuo account CIR per leggere i messaggi e gli allegati. Nessuna informazione sensibile viene riportata in questa notifica.</p></td></tr>
<tr><td style="background:#f0f6fc;padding:18px 30px;color:#64748b;font-size:12px">Cybersecurity Incident Registry · messaggio automatico del servizio Support Tickets</td></tr></table></body></html>'''
