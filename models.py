import uuid
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import String, DateTime, Date, Boolean, ForeignKey, Numeric, Text, CheckConstraint, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .db import Base

def uid(): return uuid.uuid4()
class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
class Company(TimestampMixin, Base):
    __tablename__='companies'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), default='EGP', nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
class Branch(TimestampMixin, Base):
    __tablename__='branches'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('companies.id'), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    __table_args__=(UniqueConstraint('company_id','code'),)
class User(TimestampMixin, Base):
    __tablename__='users'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('companies.id'), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(30), default='operator', nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
class Customer(TimestampMixin, Base):
    __tablename__='customers'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('companies.id'), nullable=False, index=True)
    account_code: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    phone: Mapped[str|None] = mapped_column(String(30))
    email: Mapped[str|None] = mapped_column(String(255))
    tax_number: Mapped[str|None] = mapped_column(String(50))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    __table_args__=(UniqueConstraint('company_id','account_code'),)
class Invoice(TimestampMixin, Base):
    __tablename__='invoices'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('companies.id'), nullable=False, index=True)
    branch_id: Mapped[uuid.UUID|None] = mapped_column(ForeignKey('branches.id'), index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('customers.id'), nullable=False, index=True)
    invoice_number: Mapped[str] = mapped_column(String(50), nullable=False)
    issue_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date|None] = mapped_column(Date)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(14,2), nullable=False)
    tax_amount: Mapped[Decimal] = mapped_column(Numeric(14,2), default=0, nullable=False)
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14,2), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default='issued', nullable=False)
    __table_args__=(UniqueConstraint('company_id','invoice_number'), CheckConstraint('subtotal >= 0 AND tax_amount >= 0 AND total_amount >= 0'), CheckConstraint("status IN ('draft','issued','partially_paid','paid','void')"))
class InvoiceLine(Base):
    __tablename__='invoice_lines'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('invoices.id', ondelete='RESTRICT'), nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12,3), default=1, nullable=False)
    unit_price: Mapped[Decimal] = mapped_column(Numeric(14,2), nullable=False)
    line_total: Mapped[Decimal] = mapped_column(Numeric(14,2), nullable=False)
class Payment(TimestampMixin, Base):
    __tablename__='payments'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('companies.id'), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('customers.id'), nullable=False, index=True)
    receipt_number: Mapped[str] = mapped_column(String(50), nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(14,2), nullable=False)
    method: Mapped[str] = mapped_column(String(30), nullable=False)
    reference: Mapped[str|None] = mapped_column(String(100))
    __table_args__=(UniqueConstraint('company_id','receipt_number'), CheckConstraint('amount > 0'))
class PaymentAllocation(Base):
    __tablename__='payment_allocations'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    payment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('payments.id', ondelete='RESTRICT'), nullable=False, index=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('invoices.id', ondelete='RESTRICT'), nullable=False, index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14,2), nullable=False)
    __table_args__=(CheckConstraint('amount > 0'), UniqueConstraint('payment_id','invoice_id'))
class JournalEntry(TimestampMixin, Base):
    __tablename__='journal_entries'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('companies.id'), nullable=False, index=True)
    entry_number: Mapped[str] = mapped_column(String(50), nullable=False)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False)
    description: Mapped[str] = mapped_column(String(300), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default='draft', nullable=False)
    posted_at: Mapped[datetime|None] = mapped_column(DateTime(timezone=True))
    reversal_of_id: Mapped[uuid.UUID|None] = mapped_column(ForeignKey('journal_entries.id'))
    __table_args__=(UniqueConstraint('company_id','entry_number'), CheckConstraint("status IN ('draft','approved','posted','reversed')"))
class JournalLine(Base):
    __tablename__='journal_lines'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    entry_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('journal_entries.id', ondelete='RESTRICT'), nullable=False, index=True)
    account_code: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[str|None] = mapped_column(String(250))
    debit: Mapped[Decimal] = mapped_column(Numeric(14,2), default=0, nullable=False)
    credit: Mapped[Decimal] = mapped_column(Numeric(14,2), default=0, nullable=False)
    __table_args__=(CheckConstraint('debit >= 0 AND credit >= 0 AND NOT (debit > 0 AND credit > 0)'),)
class AuditLog(Base):
    __tablename__='audit_logs'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uid)
    company_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('companies.id'), nullable=False, index=True)
    user_id: Mapped[uuid.UUID|None] = mapped_column(ForeignKey('users.id'))
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(80), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
Index('ix_invoices_customer_issue_date','invoices.customer_id','invoices.issue_date')
