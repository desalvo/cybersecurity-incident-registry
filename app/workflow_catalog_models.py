"""Persistence for the shared workflow catalog and independently installed copies."""
import uuid

from .models import db
from .timeutils import utcnow


class WorkflowCatalogEntry(db.Model):
    __tablename__ = 'workflow_catalog_entry'

    id = db.Column(db.Integer, primary_key=True)
    defaults_tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False, index=True)
    public_id = db.Column(db.String(36), nullable=False, unique=True, default=lambda: str(uuid.uuid4()))
    name = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=False, default='')
    version = db.Column(db.Integer, nullable=False, default=1)
    active = db.Column(db.Boolean, nullable=False, default=True)
    status = db.Column(db.String(20), nullable=False, default='current')
    obsolete_at = db.Column(db.DateTime, nullable=True)
    # Only a draft owned by Tenants Default can be linked to a catalogue entry.
    # This stable scope survives edits to the draft's individual step rows.
    source_scope_key = db.Column(db.String(80), nullable=True, index=True)
    payload_json = db.Column(db.Text, nullable=False)
    payload_hash = db.Column(db.String(64), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)


class WorkflowCatalogInstallation(db.Model):
    __tablename__ = 'workflow_catalog_installation'

    id = db.Column(db.Integer, primary_key=True)
    entry_id = db.Column(db.Integer, db.ForeignKey('workflow_catalog_entry.id'), nullable=False, index=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=False, index=True)
    entry_version = db.Column(db.Integer, nullable=False)
    copy_name = db.Column(db.String(160), nullable=False, default='')
    workflow_id = db.Column(db.Integer, nullable=True, index=True)
    payload_hash = db.Column(db.String(64), nullable=False)
    # An audit pointer rather than a foreign key: deleting a copied workflow
    # must not be prevented by its installation receipt.
    category_id = db.Column(db.Integer, nullable=True)
    step_ids_json = db.Column(db.Text, nullable=False, default='[]')
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    # Each explicit installation creates a separately editable copy, including
    # repeated installations of the same catalogue revision into one tenant.


class TenantWorkflow(db.Model):
    """Lifecycle of one local scope, independent of its mutable step rows."""
    __tablename__ = 'tenant_workflow'

    id = db.Column(db.Integer, primary_key=True)
    public_id = db.Column(db.String(36), nullable=False, unique=True, default=lambda: str(uuid.uuid4()))
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id', ondelete='CASCADE'), nullable=False, index=True)
    scope_key = db.Column(db.String(80), nullable=False)
    # A lifecycle record is retained until deliberate workflow deletion. The
    # source entry pointer remains after local edits or parameter detachment.
    category_id = db.Column(db.Integer, nullable=True)
    source_entry_id = db.Column(db.Integer, db.ForeignKey('workflow_catalog_entry.id'), nullable=True, index=True)
    name = db.Column(db.String(160), nullable=False, default='')
    status = db.Column(db.String(20), nullable=False, default='current')
    personalized = db.Column(db.Boolean, nullable=False, default=False)
    obsolete_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=utcnow, onupdate=utcnow)
    __table_args__ = (db.UniqueConstraint('tenant_id', 'scope_key', name='uq_tenant_workflow_scope'),
                      {'sqlite_autoincrement': True})


class WorkflowObsolescenceNotice(db.Model):
    """One durable, independently acknowledged notice per administrator."""
    __tablename__ = 'workflow_obsolescence_notice'

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.String(36), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False, index=True)
    entry_id = db.Column(db.Integer, db.ForeignKey('workflow_catalog_entry.id'), nullable=False, index=True)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=utcnow)
    read_at = db.Column(db.DateTime, nullable=True)
    __table_args__ = (db.UniqueConstraint('event_id', 'user_id', name='uq_workflow_notice_recipient'),)
