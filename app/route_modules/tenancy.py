"""Supporto multi-tenancy per route amministrative.

Questo modulo centralizza la terminologia e i metadati usati dalle schermate
multi-tenant. Gli endpoint restano in ``app.routes`` per non modificare nomi,
URL e compatibilità degli import esistenti.
"""

TENANT_SHARED_CONFIGURATION_KEYS = {
    'ssl_enabled',
    'ssl_cert_path',
    'ssl_key_path',
    'application_external_url',
    'application_timezone',
}

TENANT_SCOPED_ADMIN_AREAS = (
    'Liste configurabili',
    'Flussi operativi incidenti',
    'Modelli incidente',
    'Notifiche',
    'Destinatari esterni',
    'Backup',
    'Plugin e knowledge base AI',
)

TENANT_SHARED_ADMIN_AREAS = (
    'Moduli documento e relative configurazioni',
    'HTTPS/SSL',
    'URL applicazione',
    'Time zone applicazione',
)
