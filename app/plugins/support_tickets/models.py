"""Database entities for the optional, tenant-isolated Support Tickets plugin."""
from ...models import db
from ...timeutils import utcnow


class SupportTicketCategory(db.Model):
    __tablename__ = 'support_ticket_category'
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(80), unique=True, nullable=False, index=True)
    label_it = db.Column(db.String(120), nullable=False)
    label_en = db.Column(db.String(120), nullable=False)
    active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)


class SupportTicket(db.Model):
    __tablename__ = 'support_ticket'
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id', ondelete='RESTRICT'), nullable=False, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True, index=True)
    creator_label = db.Column(db.String(160), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('support_ticket_category.id', ondelete='RESTRICT'), nullable=False, index=True)
    subject = db.Column(db.String(255), nullable=False)
    priority = db.Column(db.String(12), nullable=False, default='medium', index=True)
    assignee_level = db.Column(db.String(20), nullable=False, default='tenant_admin', index=True)
    escalated = db.Column(db.Boolean, nullable=False, default=False)
    status = db.Column(db.String(16), nullable=False, default='submitted', index=True)
    status_reason = db.Column(db.String(1000), nullable=False, default='')
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, nullable=False, index=True)
    closed_at = db.Column(db.DateTime, nullable=True)
    tenant = db.relationship('Tenant', foreign_keys=[tenant_id])
    creator = db.relationship('User', foreign_keys=[created_by_id])
    category = db.relationship('SupportTicketCategory', foreign_keys=[category_id])
    messages = db.relationship('SupportTicketMessage', back_populates='ticket', cascade='all,delete-orphan', order_by='SupportTicketMessage.id', passive_deletes=True)
    __table_args__ = (
        db.CheckConstraint("priority IN ('urgent','high','medium','low')", name='ck_support_ticket_priority'),
        db.CheckConstraint("status IN ('submitted','open','assigned','in_progress','completed','rejected','closed')", name='ck_support_ticket_status'),
        db.CheckConstraint("assignee_level IN ('tenant_admin','super_admin')", name='ck_support_ticket_level'),
    )

    @property
    def reference(self):
        return f'SUP-{self.id:06d}'


class SupportTicketMessage(db.Model):
    __tablename__ = 'support_ticket_message'
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('support_ticket.id', ondelete='CASCADE'), nullable=False, index=True)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    author_label = db.Column(db.String(160), nullable=False)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    ticket = db.relationship('SupportTicket', back_populates='messages')
    author = db.relationship('User', foreign_keys=[author_id])
    attachments = db.relationship('SupportTicketAttachment', back_populates='message', cascade='all,delete-orphan', passive_deletes=True)


class SupportTicketAttachment(db.Model):
    __tablename__ = 'support_ticket_attachment'
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey('support_ticket_message.id', ondelete='CASCADE'), nullable=False, index=True)
    uploaded_by_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'), nullable=True)
    original_filename = db.Column(db.String(255), nullable=False)
    stored_filename = db.Column(db.String(120), nullable=False, unique=True)
    content_type = db.Column(db.String(120), nullable=False, default='application/octet-stream')
    byte_count = db.Column(db.Integer, nullable=False)
    sha256 = db.Column(db.String(64), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=utcnow, nullable=False)
    message = db.relationship('SupportTicketMessage', back_populates='attachments')
    uploaded_by = db.relationship('User', foreign_keys=[uploaded_by_id])
