"""Starter API for SHIPMENTS ERP V3. Demo scaffold; no production DB is configured."""
from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel, Field
from decimal import Decimal
from typing import Literal
import os, sqlite3, uuid, hashlib, hmac, base64, json, time, secrets
from datetime import datetime, timezone, timedelta

app = FastAPI(title="SHIPMENTS ERP API", version="3.3.0", description="Demo API with authentication and role controls; production deployment requires managed PostgreSQL and secret configuration.")

class AllocationCheck(BaseModel):
    receipt_amount: Decimal = Field(gt=0)
    allocations: list[Decimal]

class CODReconciliation(BaseModel):
    expected: Decimal = Field(ge=0)
    collected: Decimal = Field(ge=0)
    remitted: Decimal = Field(ge=0)

@app.get('/health')
def health():
    return {"status": "ok", "mode": "local-sqlite-demo", "auth_required": os.getenv('SHIPMENTS_AUTH_REQUIRED','true').lower() == 'true', "database": 'sqlite-demo' }


@app.post('/v1/finance/validate-allocation')
def validate_allocation(payload: AllocationCheck):
    if any(x < 0 for x in payload.allocations):
        raise HTTPException(422, "Allocation values cannot be negative")
    total = sum(payload.allocations, Decimal('0'))
    if total > payload.receipt_amount:
        raise HTTPException(422, "Allocations exceed receipt amount")
    return {"valid": True, "allocated": str(total), "unallocated": str(payload.receipt_amount-total)}

@app.post('/v1/cod/reconcile-preview')
def reconcile_cod(payload: CODReconciliation):
    if payload.collected > payload.expected:
        raise HTTPException(422, "Collected amount exceeds expected COD")
    if payload.remitted > payload.collected:
        raise HTTPException(422, "Remitted amount exceeds collected COD")
    return {"expected": str(payload.expected), "collected": str(payload.collected), "remitted": str(payload.remitted), "uncollected": str(payload.expected-payload.collected), "unremitted": str(payload.collected-payload.remitted), "status": "review_required" if payload.collected != payload.remitted else "matched"}


# Local demo ledger. Set SHIPMENTS_LEDGER_DB to a persistent path when running locally.
# This is NOT a production accounting store: authentication/roles and PostgreSQL transaction
# integration must be completed before real money is posted.
LEDGER_DB = os.getenv("SHIPMENTS_LEDGER_DB", os.path.join(os.path.dirname(__file__), "ledger_demo.sqlite3"))

def _ledger_conn():
    conn = sqlite3.connect(os.getenv("SHIPMENTS_LEDGER_DB", LEDGER_DB), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript("""
      CREATE TABLE IF NOT EXISTS courier_ledger (
        id TEXT PRIMARY KEY, reference_no TEXT NOT NULL UNIQUE, courier_code TEXT NOT NULL,
        branch_code TEXT NOT NULL, entry_type TEXT NOT NULL CHECK(entry_type IN
          ('opening','assignment','collection','remittance','adjustment','reversal')),
        debit TEXT NOT NULL, credit TEXT NOT NULL, balance TEXT NOT NULL,
        source_reference TEXT, reversal_of TEXT REFERENCES courier_ledger(reference_no),
        reason TEXT NOT NULL, created_at TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS courier_ledger_lookup_idx ON courier_ledger(courier_code, created_at);
      CREATE TABLE IF NOT EXISTS app_users (
        id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('super_admin','company_manager','branch_manager','treasury','auditor','courier')),
        branch_code TEXT, is_active INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL
      );
      CREATE TABLE IF NOT EXISTS audit_events (
        id TEXT PRIMARY KEY, actor_id TEXT NOT NULL, actor_username TEXT NOT NULL,
        action TEXT NOT NULL, entity_type TEXT NOT NULL, entity_reference TEXT,
        details TEXT NOT NULL, created_at TEXT NOT NULL
      );
      CREATE INDEX IF NOT EXISTS audit_events_date_idx ON audit_events(created_at);
      CREATE TRIGGER IF NOT EXISTS audit_events_no_update BEFORE UPDATE ON audit_events
        BEGIN SELECT RAISE(ABORT, 'audit events are immutable'); END;
      CREATE TRIGGER IF NOT EXISTS audit_events_no_delete BEFORE DELETE ON audit_events
        BEGIN SELECT RAISE(ABORT, 'audit events are immutable'); END;
      CREATE TRIGGER IF NOT EXISTS courier_ledger_no_update BEFORE UPDATE ON courier_ledger
        BEGIN SELECT RAISE(ABORT, 'ledger entries are immutable'); END;
      CREATE TRIGGER IF NOT EXISTS courier_ledger_no_delete BEFORE DELETE ON courier_ledger
        BEGIN SELECT RAISE(ABORT, 'ledger entries are immutable'); END;
    """)
    # Backward-compatible demo migration for courier-scoped logins.
    user_columns = {row['name'] for row in conn.execute('PRAGMA table_info(app_users)').fetchall()}
    if 'courier_code' not in user_columns:
        conn.execute('ALTER TABLE app_users ADD COLUMN courier_code TEXT')
    return conn

# V3.3 authentication. Demo users are bootstrapped only from environment variables.
# Set SHIPMENTS_AUTH_SECRET to a long random secret before any non-demo deployment.
AUTH_SECRET = os.getenv("SHIPMENTS_AUTH_SECRET", "DEMO-ONLY-CHANGE-ME-32-CHARS-MINIMUM")
TOKEN_TTL_SECONDS = int(os.getenv("SHIPMENTS_TOKEN_TTL", "3600"))
ROLE_PERMISSIONS = {
    "super_admin": {"ledger:read", "ledger:write", "ledger:reverse", "users:manage", "audit:read"},
    "company_manager": {"ledger:read", "ledger:write", "ledger:reverse", "audit:read"},
    "branch_manager": {"ledger:read", "ledger:write", "ledger:reverse"},
    "treasury": {"ledger:read", "ledger:write"},
    "auditor": {"ledger:read", "audit:read"},
    "courier": {"ledger:read"},
}

class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=80)
    password: str = Field(min_length=10, max_length=200)

class UserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_.-]+$")
    password: str = Field(min_length=12, max_length=200)
    role: Literal['super_admin','company_manager','branch_manager','treasury','auditor','courier']
    branch_code: str | None = Field(default=None, max_length=40)
    courier_code: str | None = Field(default=None, max_length=40)


def _password_hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 310000)
    return base64.urlsafe_b64encode(salt).decode() + '$' + base64.urlsafe_b64encode(digest).decode()

def _password_matches(password: str, encoded: str) -> bool:
    try:
        salt_b64, digest_b64 = encoded.split('$', 1)
        salt, expected = base64.urlsafe_b64decode(salt_b64), base64.urlsafe_b64decode(digest_b64)
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), salt, 310000)
        return hmac.compare_digest(actual, expected)
    except Exception:
        return False

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode()

def _issue_token(user: sqlite3.Row) -> str:
    payload = {"sub": user['id'], "username": user['username'], "role": user['role'], "branch": user['branch_code'], "courier": user['courier_code'], "exp": int(time.time()) + TOKEN_TTL_SECONDS}
    body = _b64(json.dumps(payload, separators=(',', ':')).encode())
    sig = _b64(hmac.new(AUTH_SECRET.encode(), body.encode(), hashlib.sha256).digest())
    return body + '.' + sig

def _audit(conn, actor, action, entity_type, entity_reference, details):
    conn.execute('INSERT INTO audit_events VALUES(?,?,?,?,?,?,?,?)', (str(uuid.uuid4()), actor['id'], actor['username'], action, entity_type, entity_reference, json.dumps(details, ensure_ascii=False, default=str), datetime.now(timezone.utc).isoformat()))

def get_current_user(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(401, 'Authentication required')
    token = authorization[7:]
    try:
        body, signature = token.split('.', 1)
        expected = _b64(hmac.new(AUTH_SECRET.encode(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(signature, expected): raise ValueError('signature')
        payload = json.loads(base64.urlsafe_b64decode(body + '=' * (-len(body) % 4)))
        if int(payload['exp']) < int(time.time()): raise ValueError('expired')
        conn = _ledger_conn()
        try: user = conn.execute('SELECT id,username,role,branch_code,courier_code,is_active FROM app_users WHERE id=?', (payload['sub'],)).fetchone()
        finally: conn.close()
        if not user or not user['is_active']: raise ValueError('inactive')
        return dict(user)
    except HTTPException: raise
    except Exception: raise HTTPException(401, 'Invalid or expired access token')

def _assert_branch_scope(actor, branch_code: str):
    if actor.get('courier_code'):
        raise HTTPException(403, 'Courier accounts cannot post ledger entries')
    if actor.get('branch_code') and actor['branch_code'] != branch_code:
        raise HTTPException(403, 'You cannot access another branch')

def require_permission(permission: str):
    def dependency(user=Depends(get_current_user)):
        if permission not in ROLE_PERMISSIONS.get(user['role'], set()):
            raise HTTPException(403, 'Insufficient permission')
        return user
    return dependency

@app.on_event('startup')
def bootstrap_demo_admin():
    if os.getenv('SHIPMENTS_ENV', 'demo').lower() == 'production' and AUTH_SECRET == 'DEMO-ONLY-CHANGE-ME-32-CHARS-MINIMUM':
        raise RuntimeError('Set a unique SHIPMENTS_AUTH_SECRET before production startup')
    conn = _ledger_conn()
    try:
        username = os.getenv('SHIPMENTS_BOOTSTRAP_ADMIN_USER')
        password = os.getenv('SHIPMENTS_BOOTSTRAP_ADMIN_PASSWORD')
        if username and password and not conn.execute('SELECT 1 FROM app_users WHERE username=?', (username,)).fetchone():
            conn.execute('INSERT INTO app_users(id,username,password_hash,role,branch_code,is_active,created_at,courier_code) VALUES(?,?,?,?,?,?,?,?)', (str(uuid.uuid4()), username, _password_hash(password), 'super_admin', None, 1, datetime.now(timezone.utc).isoformat(), None))
            conn.commit()
    finally: conn.close()

@app.post('/v1/auth/login')
def login(payload: LoginRequest):
    conn = _ledger_conn()
    try:
        user = conn.execute('SELECT * FROM app_users WHERE username=?', (payload.username,)).fetchone()
        if not user or not user['is_active'] or not _password_matches(payload.password, user['password_hash']):
            raise HTTPException(401, 'Invalid username or password')
        _audit(conn, dict(user), 'login', 'user', user['id'], {'role': user['role']})
        conn.commit()
        return {'access_token': _issue_token(user), 'token_type': 'bearer', 'expires_in': TOKEN_TTL_SECONDS, 'user': {'username': user['username'], 'role': user['role'], 'branch_code': user['branch_code'], 'courier_code': user['courier_code'], 'permissions': sorted(ROLE_PERMISSIONS[user['role']])}}
    finally: conn.close()

@app.get('/v1/auth/me')
def who_am_i(user=Depends(get_current_user)):
    return {'username': user['username'], 'role': user['role'], 'branch_code': user['branch_code'], 'courier_code': user['courier_code'], 'permissions': sorted(ROLE_PERMISSIONS[user['role']])}

@app.post('/v1/admin/users', status_code=201)
def create_user(payload: UserCreate, actor=Depends(require_permission('users:manage'))):
    if payload.role == 'branch_manager' and not payload.branch_code:
        raise HTTPException(422, 'Branch managers must be assigned a branch_code')
    if payload.role == 'courier' and not payload.courier_code:
        raise HTTPException(422, 'Courier users must be assigned a courier_code')
    conn = _ledger_conn()
    try:
        user_id = str(uuid.uuid4())
        conn.execute('INSERT INTO app_users(id,username,password_hash,role,branch_code,is_active,created_at,courier_code) VALUES(?,?,?,?,?,?,?,?)', (user_id, payload.username, _password_hash(payload.password), payload.role, payload.branch_code, 1, datetime.now(timezone.utc).isoformat(), payload.courier_code))
        _audit(conn, actor, 'user_created', 'user', user_id, {'username': payload.username, 'role': payload.role, 'branch_code': payload.branch_code, 'courier_code': payload.courier_code})
        conn.commit()
        return {'id': user_id, 'username': payload.username, 'role': payload.role, 'branch_code': payload.branch_code, 'courier_code': payload.courier_code}
    except sqlite3.IntegrityError:
        conn.rollback(); raise HTTPException(409, 'Username already exists')
    finally: conn.close()

@app.get('/v1/admin/audit')
def read_audit(limit: int = 100, actor=Depends(require_permission('audit:read'))):
    if limit < 1 or limit > 500: raise HTTPException(422, 'limit must be between 1 and 500')
    conn = _ledger_conn()
    try:
        rows = conn.execute('SELECT actor_username,action,entity_type,entity_reference,details,created_at FROM audit_events ORDER BY rowid DESC LIMIT ?', (limit,)).fetchall()
        return {'events': [dict(r) for r in rows]}
    finally: conn.close()

class LedgerEntry(BaseModel):
    courier_code: str = Field(min_length=1, max_length=40)
    branch_code: str = Field(min_length=1, max_length=40)
    entry_type: Literal['opening','assignment','collection','remittance','adjustment']
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    reason: str = Field(min_length=3, max_length=500)
    source_reference: str | None = Field(default=None, max_length=80)

class LedgerReversal(BaseModel):
    reason: str = Field(min_length=3, max_length=500)

@app.post('/v1/couriers/ledger', status_code=201)
def post_ledger_entry(payload: LedgerEntry, actor=Depends(require_permission('ledger:write'))):
    if actor['role'] == 'branch_manager' and actor['branch_code'] != payload.branch_code:
        raise HTTPException(403, 'Branch manager cannot post to another branch')
    if actor['role'] == 'treasury' and payload.entry_type not in ('remittance',):
        raise HTTPException(403, 'Cashiers may only record treasury remittances')
    conn = _ledger_conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        row = conn.execute('SELECT balance FROM courier_ledger WHERE courier_code=? ORDER BY rowid DESC LIMIT 1', (payload.courier_code,)).fetchone()
        balance = Decimal(row['balance']) if row else Decimal('0.00')
        # Debit increases the amount held by the courier; credit reduces it.
        debit = payload.amount if payload.entry_type in ('opening','assignment','collection') else Decimal('0.00')
        credit = payload.amount if payload.entry_type in ('remittance','adjustment') else Decimal('0.00')
        new_balance = balance + debit - credit
        if new_balance < 0:
            raise HTTPException(422, 'This credit exceeds the courier current custody balance')
        ref = 'CL-' + datetime.now(timezone.utc).strftime('%Y%m%d') + '-' + uuid.uuid4().hex[:8].upper()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute('INSERT INTO courier_ledger VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
          (str(uuid.uuid4()),ref,payload.courier_code,payload.branch_code,payload.entry_type,str(debit),str(credit),str(new_balance),payload.source_reference,None,payload.reason,now))
        _audit(conn, actor, 'ledger_entry_created', 'courier_ledger', ref, {'courier_code':payload.courier_code,'entry_type':payload.entry_type,'debit':str(debit),'credit':str(credit),'balance':str(new_balance)})
        conn.commit()
        return {'reference_no':ref,'courier_code':payload.courier_code,'branch_code':payload.branch_code,'entry_type':payload.entry_type,'debit':str(debit),'credit':str(credit),'balance':str(new_balance),'reason':payload.reason,'created_at':now}
    except HTTPException:
        conn.rollback(); raise
    except sqlite3.IntegrityError as e:
        conn.rollback(); raise HTTPException(409, str(e))
    finally:
        conn.close()

@app.get('/v1/couriers/{courier_code}/ledger')
def get_courier_ledger(courier_code: str, actor=Depends(require_permission('ledger:read'))):
    if actor['role'] == 'courier' and actor['courier_code'] != courier_code:
        raise HTTPException(403, 'Courier users may only view their own ledger')
    conn = _ledger_conn()
    try:
        rows = conn.execute('SELECT reference_no,courier_code,branch_code,entry_type,debit,credit,balance,source_reference,reversal_of,reason,created_at FROM courier_ledger WHERE courier_code=? ORDER BY rowid', (courier_code,)).fetchall()
        if actor['role'] == 'branch_manager' and any(r['branch_code'] != actor['branch_code'] for r in rows):
            raise HTTPException(403, 'Branch manager cannot view another branch ledger')
        if actor.get('courier_code') and actor['courier_code'] != courier_code:
            raise HTTPException(403, 'You can only access your own courier ledger')
        if actor.get('branch_code') and any(r['branch_code'] != actor['branch_code'] for r in rows):
            raise HTTPException(403, 'You cannot access another branch')
        return {'courier_code':courier_code,'entries':[dict(r) for r in rows], 'closing_balance': rows[-1]['balance'] if rows else '0.00'}
    finally: conn.close()

@app.post('/v1/couriers/ledger/{reference_no}/reverse', status_code=201)
def reverse_ledger_entry(reference_no: str, payload: LedgerReversal, actor=Depends(require_permission('ledger:reverse'))):
    conn = _ledger_conn()
    try:
        conn.execute('BEGIN IMMEDIATE')
        original = conn.execute('SELECT * FROM courier_ledger WHERE reference_no=?', (reference_no,)).fetchone()
        if not original: raise HTTPException(404, 'Ledger reference not found')
        if actor['role'] == 'branch_manager' and actor['branch_code'] != original['branch_code']:
            raise HTTPException(403, 'Branch manager cannot reverse another branch entry')
        if conn.execute('SELECT 1 FROM courier_ledger WHERE reversal_of=?', (reference_no,)).fetchone():
            raise HTTPException(409, 'This entry has already been reversed')
        _assert_branch_scope(actor, original['branch_code'])
        if actor.get('courier_code'):
            raise HTTPException(403, 'Courier accounts cannot reverse ledger entries')
        last = conn.execute('SELECT balance FROM courier_ledger WHERE courier_code=? ORDER BY rowid DESC LIMIT 1', (original['courier_code'],)).fetchone()
        balance = Decimal(last['balance']) if last else Decimal('0.00')
        debit, credit = Decimal(original['credit']), Decimal(original['debit'])
        new_balance = balance + debit - credit
        if new_balance < 0: raise HTTPException(422, 'Reversal would create a negative custody balance')
        ref = 'CL-' + datetime.now(timezone.utc).strftime('%Y%m%d') + '-REV-' + uuid.uuid4().hex[:6].upper()
        now = datetime.now(timezone.utc).isoformat()
        conn.execute('INSERT INTO courier_ledger VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
          (str(uuid.uuid4()),ref,original['courier_code'],original['branch_code'],'reversal',str(debit),str(credit),str(new_balance),reference_no,reference_no,payload.reason,now))
        _audit(conn, actor, 'ledger_entry_reversed', 'courier_ledger', ref, {'reversal_of':reference_no,'balance':str(new_balance)})
        conn.commit()
        return {'reference_no':ref,'reversal_of':reference_no,'debit':str(debit),'credit':str(credit),'balance':str(new_balance),'created_at':now}
    except HTTPException:
        conn.rollback(); raise
    finally: conn.close()
