from datetime import date
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
class CustomerCreate(BaseModel):
    company_id: UUID
    account_code: str = Field(min_length=2, max_length=40)
    name: str = Field(min_length=2, max_length=200)
    phone: str|None = None
    email: str|None = None
class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID; company_id: UUID; account_code: str; name: str; phone: str|None; email: str|None
class InvoiceCreate(BaseModel):
    company_id: UUID; customer_id: UUID; invoice_number: str = Field(min_length=2, max_length=50)
    issue_date: date; due_date: date|None = None
    subtotal: Decimal = Field(ge=0); tax_amount: Decimal = Field(default=Decimal('0'), ge=0); total_amount: Decimal = Field(ge=0)
class InvoiceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID; company_id: UUID; customer_id: UUID; invoice_number: str; issue_date: date; due_date: date|None; subtotal: Decimal; tax_amount: Decimal; total_amount: Decimal; status: str
class PaymentCreate(BaseModel):
    company_id: UUID; customer_id: UUID; receipt_number: str; payment_date: date
    amount: Decimal = Field(gt=0); method: str; reference: str|None = None
class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID; company_id: UUID; customer_id: UUID; receipt_number: str; payment_date: date; amount: Decimal; method: str

class CompanyCreate(BaseModel):
    code: str = Field(min_length=2, max_length=30)
    name: str = Field(min_length=2, max_length=200)
    currency: str = Field(default='EGP', min_length=3, max_length=3)
class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID; code: str; name: str; currency: str; is_active: bool
