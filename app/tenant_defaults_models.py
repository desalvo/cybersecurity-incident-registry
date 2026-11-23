"""Persistent provenance for the shared configuration tenant.

Numeric IDs remain private to the receiving database. A UUID identifies each
published item, while replicas remember exactly what was last synchronized.
Retired sources are deliberately retained for audit and repeat imports.
"""
import uuid

from .models import db
from .timeutils import utcnow


class TenantDefaultSource(db.Model):
    __tablename__ = 'tenant_default_source'
    id = db.Column(db.String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    source_type = db.Column(db.String(40), nullable=False)
    source_id = db.Column(db.Integer, nullable=True)
    snapshot_json = db.Column(db.Text, nullable=False, default='{}')
    active = db.Column(db.Boolean, nullable=False, default=True)
    import_origin = db.Column(db.String(36), nullable=True)
    import_key = db.Column(db.String(36), nullable=True)
    import_snapshot_json = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    __table_args__ = (
        db.UniqueConstraint('source_type', 'source_id', name='uq_default_source_record'),
        db.UniqueConstraint('import_origin', 'import_key', name='uq_default_source_import'),
    )


class TenantDefaultReplica(db.Model):
    __tablename__ = 'tenant_default_replica'
    id = db.Column(db.Integer, primary_key=True)
    source_id = db.Column(db.String(36), db.ForeignKey('tenant_default_source.id'), nullable=False, index=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id', ondelete='CASCADE'), nullable=False, index=True)
    local_type = db.Column(db.String(40), nullable=False)
    local_id = db.Column(db.Integer, nullable=False)
    snapshot_json = db.Column(db.Text, nullable=False)
    __table_args__ = (
        db.UniqueConstraint('source_id', 'tenant_id', name='uq_default_replica_tenant'),
        db.UniqueConstraint('local_type', 'local_id', name='uq_default_replica_record'),
    )


class TenantDefaultAlert(db.Model):
    __tablename__ = 'tenant_default_alert'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id', ondelete='CASCADE'), nullable=False, index=True)
    source_id = db.Column(db.String(36), db.ForeignKey('tenant_default_source.id'), nullable=False, index=True)
    kind = db.Column(db.String(40), nullable=False)
    message = db.Column(db.Text, nullable=False)
    local_type = db.Column(db.String(40), nullable=False)
    local_id = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    acknowledged_at = db.Column(db.DateTime, nullable=True)
    __table_args__ = (
        db.UniqueConstraint('tenant_id', 'source_id', 'kind', 'local_id', name='uq_default_alert_event'),
    )
