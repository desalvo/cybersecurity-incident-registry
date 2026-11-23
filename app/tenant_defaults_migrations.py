"""Non-destructive removal of the recipient-address identity constraint."""


def _sqlite_allow_recipient_copies(connection):
    """Keep IDs/data/indexes; reject unknown schemas instead of losing data.

    Accepts a DB-API connection so the SQLite migration can also be exercised
    with the standard library independently of the web application.
    """
    name = 'external_recipient'
    if not connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone():
        return False
    columns = [row[1] for row in connection.execute('PRAGMA table_info(external_recipient)')]
    expected = ['id', 'tenant_id', 'name', 'email', 'notes', 'created_at', 'updated_at']
    if set(columns) != set(expected):
        raise RuntimeError('Schema external_recipient inatteso: migrazione interrotta senza cancellare dati.')
    indexes = connection.execute('PRAGMA index_list(external_recipient)').fetchall()
    removed = set()
    for index in indexes:
        index_name = index[1]
        quoted = '"' + index_name.replace('"', '""') + '"'
        index_columns = tuple(row[2] for row in connection.execute(f'PRAGMA index_info({quoted})'))
        if index[2] and index_columns in {('email',), ('tenant_id', 'email')}:
            removed.add(index_name)
        elif index[2] and index_name.startswith('sqlite_autoindex_'):
            raise RuntimeError('Vincolo recipient personalizzato: migrazione automatica non applicabile.')
    if not removed:
        return False
    if connection.execute("SELECT 1 FROM sqlite_master WHERE type='trigger' AND tbl_name=?", (name,)).fetchone():
        raise RuntimeError('Trigger recipient personalizzato: migrazione automatica non applicabile.')
    tables = connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    for (table,) in tables:
        quoted = '"' + table.replace('"', '""') + '"'
        if any(row[2] == name for row in connection.execute(f'PRAGMA foreign_key_list({quoted})')):
            raise RuntimeError('Riferimenti recipient personalizzati: migrazione automatica non applicabile.')
    retained_indexes = [sql for index_name, sql in connection.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='index' AND tbl_name=? AND sql IS NOT NULL", (name,)
    ) if index_name not in removed]
    connection.execute('BEGIN IMMEDIATE')
    try:
        connection.execute('''CREATE TABLE __cir_recipient_identity_migration (
            id INTEGER NOT NULL PRIMARY KEY,
            tenant_id INTEGER REFERENCES tenant(id), name VARCHAR(160) NOT NULL,
            email VARCHAR(255) NOT NULL, notes TEXT, created_at DATETIME, updated_at DATETIME
        )''')
        connection.execute('''INSERT INTO __cir_recipient_identity_migration
            (id, tenant_id, name, email, notes, created_at, updated_at)
            SELECT id, tenant_id, name, email, notes, created_at, updated_at FROM external_recipient''')
        connection.execute('DROP TABLE external_recipient')
        connection.execute('ALTER TABLE __cir_recipient_identity_migration RENAME TO external_recipient')
        for sql in retained_indexes:
            connection.execute(sql)
        connection.execute('CREATE INDEX IF NOT EXISTS ix_external_recipient_email ON external_recipient(email)')
        connection.execute('CREATE INDEX IF NOT EXISTS ix_external_recipient_tenant_id ON external_recipient(tenant_id)')
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    return True


def migrate_recipient_configuration_identity(engine):
    if engine.dialect.name == 'sqlite':
        connection = engine.raw_connection()
        try:
            return _sqlite_allow_recipient_copies(connection)
        finally:
            connection.close()
    if engine.dialect.name != 'postgresql':
        return False
    from sqlalchemy import inspect, text
    inspector = inspect(engine)
    if not inspector.has_table('external_recipient'):
        return False
    quote = engine.dialect.identifier_preparer.quote
    removed = False
    with engine.begin() as connection:
        for constraint in inspector.get_unique_constraints('external_recipient'):
            if tuple(constraint.get('column_names') or ()) in {('email',), ('tenant_id', 'email')}:
                connection.execute(text('ALTER TABLE external_recipient DROP CONSTRAINT IF EXISTS ' + quote(constraint['name'])))
                removed = True
        for index in inspector.get_indexes('external_recipient'):
            if index.get('unique') and tuple(index.get('column_names') or ()) in {('email',), ('tenant_id', 'email')}:
                connection.execute(text('DROP INDEX IF EXISTS ' + quote(index['name'])))
                removed = True
        connection.execute(text('CREATE INDEX IF NOT EXISTS ix_external_recipient_email ON external_recipient(email)'))
    return removed
