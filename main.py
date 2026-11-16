from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import select, func
from decimal import Decimal
from uuid import UUID
from .db import get_db
from . import models as m, schemas as s
from .settings import settings
app=FastAPI(title='SHIPMENTS ERP API', version='2.0.0', description='API backend for SHIPMENTS ERP')
origins=[x.strip() for x in settings.cors_origins.split(',') if x.strip()]
app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=True, allow_methods=['GET','POST','OPTIONS'], allow_headers=['Authorization','Content-Type'])
@app.get('/health')
def health(): return {'status':'ok','service':'shipments-erp-api','version':'2.0.0'}
@app.post('/api/v1/companies', response_model=s.CompanyOut, status_code=201)
def create_company(payload:s.CompanyCreate, db:Session=Depends(get_db)):
    obj=m.Company(**payload.model_dump()); db.add(obj)
    try: db.commit(); db.refresh(obj)
    except Exception: db.rollback(); raise HTTPException(409,'Company code already exists or data is invalid')
    return obj
@app.get('/api/v1/companies', response_model=list[s.CompanyOut])
def list_companies(db:Session=Depends(get_db), limit:int=100):
    return db.scalars(select(m.Company).order_by(m.Company.name).limit(min(limit,500))).all()
@app.post('/api/v1/customers', response_model=s.CustomerOut, status_code=201)
def create_customer(payload:s.CustomerCreate, db:Session=Depends(get_db)):
    if not db.get(m.Company,payload.company_id): raise HTTPException(404,'Company not found')
    obj=m.Customer(**payload.model_dump()); db.add(obj)
    try: db.commit(); db.refresh(obj)
    except Exception: db.rollback(); raise HTTPException(409,'Customer account code already exists or data is invalid')
    return obj
@app.get('/api/v1/customers', response_model=list[s.CustomerOut])
def list_customers(company_id:UUID, db:Session=Depends(get_db), limit:int=100, offset:int=0):
    return db.scalars(select(m.Customer).where(m.Customer.company_id==company_id).order_by(m.Customer.name).limit(min(limit,500)).offset(offset)).all()
@app.post('/api/v1/invoices', response_model=s.InvoiceOut, status_code=201)
def create_invoice(payload:s.InvoiceCreate, db:Session=Depends(get_db)):
    if payload.subtotal + payload.tax_amount != payload.total_amount: raise HTTPException(422,'total_amount must equal subtotal + tax_amount')
    customer=db.get(m.Customer,payload.customer_id)
    if not customer or customer.company_id != payload.company_id: raise HTTPException(404,'Customer not found in this company')
    obj=m.Invoice(**payload.model_dump()); db.add(obj)
    try: db.commit(); db.refresh(obj)
    except Exception: db.rollback(); raise HTTPException(409,'Invoice number already exists or data is invalid')
    return obj
@app.get('/api/v1/invoices', response_model=list[s.InvoiceOut])
def list_invoices(company_id:UUID, customer_id:UUID|None=None, db:Session=Depends(get_db), limit:int=100, offset:int=0):
    q=select(m.Invoice).where(m.Invoice.company_id==company_id)
    if customer_id: q=q.where(m.Invoice.customer_id==customer_id)
    return db.scalars(q.order_by(m.Invoice.issue_date.desc()).limit(min(limit,500)).offset(offset)).all()
@app.post('/api/v1/payments', response_model=s.PaymentOut, status_code=201)
def create_payment(payload:s.PaymentCreate, db:Session=Depends(get_db)):
    customer=db.get(m.Customer,payload.customer_id)
    if not customer or customer.company_id != payload.company_id: raise HTTPException(404,'Customer not found in this company')
    obj=m.Payment(**payload.model_dump()); db.add(obj)
    try: db.commit(); db.refresh(obj)
    except Exception: db.rollback(); raise HTTPException(409,'Receipt number already exists or data is invalid')
    return obj
@app.get('/api/v1/reports/customer-balance/{customer_id}')
def customer_balance(customer_id:UUID, db:Session=Depends(get_db)):
    customer=db.get(m.Customer,customer_id)
    if not customer: raise HTTPException(404,'Customer not found')
    invoiced=db.scalar(select(func.coalesce(func.sum(m.Invoice.total_amount),0)).where(m.Invoice.customer_id==customer_id,m.Invoice.status!='void')) or Decimal('0')
    paid=db.scalar(select(func.coalesce(func.sum(m.Payment.amount),0)).where(m.Payment.customer_id==customer_id)) or Decimal('0')
    return {'customer_id':str(customer_id),'account_code':customer.account_code,'customer_name':customer.name,'invoiced_total':str(invoiced),'payments_total':str(paid),'balance_due':str(invoiced-paid),'currency':'EGP'}
