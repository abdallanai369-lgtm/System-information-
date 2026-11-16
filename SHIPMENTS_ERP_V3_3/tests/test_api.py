import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
from backend.main import app
import backend.main as api
import uuid
from datetime import datetime, timezone

client = TestClient(app)

def admin_headers(tmp_path, monkeypatch):
    db = tmp_path / 'ledger.sqlite'
    monkeypatch.setenv('SHIPMENTS_LEDGER_DB', str(db))
    conn = api._ledger_conn()
    user_id = str(uuid.uuid4())
    conn.execute('INSERT INTO app_users(id,username,password_hash,role,branch_code,is_active,created_at) VALUES(?,?,?,?,?,?,?)', (user_id, 'admin_test', api._password_hash('StrongTestPassword!123'), 'super_admin', None, 1, datetime.now(timezone.utc).isoformat()))
    conn.commit()
    row = conn.execute('SELECT * FROM app_users WHERE id=?', (user_id,)).fetchone()
    token = api._issue_token(row)
    conn.close()
    return {'Authorization': 'Bearer ' + token}

def test_health():
    r = client.get('/health')
    assert r.status_code == 200
    assert r.json()['mode'] == 'local-sqlite-demo' and r.json()['auth_required'] is True

def test_allocation_valid():
    r = client.post('/v1/finance/validate-allocation', json={'receipt_amount':'100','allocations':['40','35']})
    assert r.status_code == 200 and r.json()['unallocated'] == '25'

def test_allocation_overflow_rejected():
    r = client.post('/v1/finance/validate-allocation', json={'receipt_amount':'100','allocations':['80','30']})
    assert r.status_code == 422

def test_cod_reconciliation_gap():
    r = client.post('/v1/cod/reconcile-preview', json={'expected':'1000','collected':'900','remitted':'700'})
    assert r.status_code == 200
    assert r.json()['uncollected'] == '100' and r.json()['unremitted'] == '200'

def test_cod_over_remittance_rejected():
    r = client.post('/v1/cod/reconcile-preview', json={'expected':'1000','collected':'900','remitted':'950'})
    assert r.status_code == 422

def test_ledger_append_and_running_balance(tmp_path, monkeypatch):
    headers = admin_headers(tmp_path, monkeypatch)
    first = client.post('/v1/couriers/ledger', json={
        'courier_code':'CR-01','branch_code':'CAI','entry_type':'collection','amount':'500.00','reason':'COD collected','source_reference':'SHP-1'
    }, headers=headers)
    assert first.status_code == 201 and first.json()['balance'] == '500.00'
    second = client.post('/v1/couriers/ledger', json={
        'courier_code':'CR-01','branch_code':'CAI','entry_type':'remittance','amount':'200.00','reason':'Cash handed to treasury','source_reference':'RCPT-1'
    }, headers=headers)
    assert second.status_code == 201 and second.json()['balance'] == '300.00'
    ledger = client.get('/v1/couriers/CR-01/ledger', headers=headers).json()
    assert len(ledger['entries']) == 2 and ledger['closing_balance'] == '300.00'

def test_ledger_rejects_over_remittance(tmp_path, monkeypatch):
    headers = admin_headers(tmp_path, monkeypatch)
    r = client.post('/v1/couriers/ledger', json={
        'courier_code':'CR-02','branch_code':'GIZ','entry_type':'remittance','amount':'10','reason':'Too much remittance'
    }, headers=headers)
    assert r.status_code == 422

def test_ledger_reversal_is_new_immutable_entry(tmp_path, monkeypatch):
    headers = admin_headers(tmp_path, monkeypatch)
    original = client.post('/v1/couriers/ledger', json={
        'courier_code':'CR-03','branch_code':'ALX','entry_type':'collection','amount':'75','reason':'Recorded collection'
    }, headers=headers).json()
    reversal = client.post(f"/v1/couriers/ledger/{original['reference_no']}/reverse", json={'reason':'Duplicate source entry'}, headers=headers )
    assert reversal.status_code == 201 and reversal.json()['balance'] == '0.00'
    duplicate = client.post(f"/v1/couriers/ledger/{original['reference_no']}/reverse", json={'reason':'Try twice'}, headers=headers)
    assert duplicate.status_code == 409
    ledger = client.get('/v1/couriers/CR-03/ledger', headers=headers).json()
    assert len(ledger['entries']) == 2 and ledger['entries'][1]['reversal_of'] == original['reference_no']

def test_ledger_storage_blocks_update_and_delete(tmp_path, monkeypatch):
    import sqlite3
    db = tmp_path / 'ledger.sqlite'
    headers = admin_headers(tmp_path, monkeypatch)
    created = client.post('/v1/couriers/ledger', json={
        'courier_code':'CR-IMM','branch_code':'CAI','entry_type':'collection','amount':'25','reason':'Immutable test row'
    }, headers=headers).json()
    con = sqlite3.connect(db)
    try:
        import pytest
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('UPDATE courier_ledger SET reason=? WHERE reference_no=?', ('tampered', created['reference_no']))
        con.rollback()
        with pytest.raises(sqlite3.IntegrityError):
            con.execute('DELETE FROM courier_ledger WHERE reference_no=?', (created['reference_no'],))
    finally:
        con.close()


def test_ledger_requires_authentication(tmp_path, monkeypatch):
    monkeypatch.setenv('SHIPMENTS_LEDGER_DB', str(tmp_path / 'ledger.sqlite'))
    response = client.get('/v1/couriers/CR-X/ledger')
    assert response.status_code == 401


def test_role_permissions_block_courier_writes(tmp_path, monkeypatch):
    monkeypatch.setenv('SHIPMENTS_LEDGER_DB', str(tmp_path / 'ledger.sqlite'))
    conn = api._ledger_conn()
    user_id = str(uuid.uuid4())
    conn.execute('INSERT INTO app_users(id,username,password_hash,role,branch_code,is_active,created_at) VALUES(?,?,?,?,?,?,?)', (user_id, 'courier_test', api._password_hash('CourierPassword!123'), 'courier', 'CAI', 1, datetime.now(timezone.utc).isoformat()))
    row = conn.execute('SELECT * FROM app_users WHERE id=?', (user_id,)).fetchone()
    token = api._issue_token(row)
    conn.commit(); conn.close()
    response = client.post('/v1/couriers/ledger', json={'courier_code':'CR-X','branch_code':'CAI','entry_type':'collection','amount':'10','reason':'test entry'}, headers={'Authorization':'Bearer '+token})
    assert response.status_code == 403


def test_audit_records_ledger_activity(tmp_path, monkeypatch):
    headers = admin_headers(tmp_path, monkeypatch)
    response = client.post('/v1/couriers/ledger', json={'courier_code':'CR-AUD','branch_code':'CAI','entry_type':'collection','amount':'10','reason':'audit test'}, headers=headers)
    assert response.status_code == 201
    events = client.get('/v1/admin/audit', headers=headers).json()['events']
    assert any(e['action'] == 'ledger_entry_created' for e in events)


def test_branch_user_cannot_write_to_other_branch(tmp_path, monkeypatch):
    monkeypatch.setenv('SHIPMENTS_LEDGER_DB', str(tmp_path / 'ledger.sqlite'))
    conn = api._ledger_conn()
    user_id = str(uuid.uuid4())
    conn.execute('INSERT INTO app_users(id,username,password_hash,role,branch_code,is_active,created_at) VALUES(?,?,?,?,?,?,?)', (user_id, 'branch_mgr', api._password_hash('BranchPassword!123'), 'branch_manager', 'CAI', 1, datetime.now(timezone.utc).isoformat()))
    row = conn.execute('SELECT * FROM app_users WHERE id=?', (user_id,)).fetchone()
    token = api._issue_token(row); conn.commit(); conn.close()
    response = client.post('/v1/couriers/ledger', json={'courier_code':'CR-X','branch_code':'ALX','entry_type':'collection','amount':'10','reason':'wrong branch'}, headers={'Authorization':'Bearer '+token})
    assert response.status_code == 403


def test_audit_log_is_immutable(tmp_path, monkeypatch):
    import sqlite3, pytest
    headers = admin_headers(tmp_path, monkeypatch)
    client.post('/v1/couriers/ledger', json={'courier_code':'CR-AUD2','branch_code':'CAI','entry_type':'collection','amount':'10','reason':'audit immutability'}, headers=headers)
    db = tmp_path / 'ledger.sqlite'
    con = sqlite3.connect(db)
    try:
        with pytest.raises(sqlite3.IntegrityError):
            con.execute("UPDATE audit_events SET action='tampered'")
    finally: con.close()

def test_login_returns_role_and_scoped_identity(tmp_path, monkeypatch):
    monkeypatch.setenv('SHIPMENTS_LEDGER_DB', str(tmp_path / 'ledger.sqlite'))
    conn = api._ledger_conn()
    uid = str(uuid.uuid4())
    password = 'CourierPassword!123'
    conn.execute('INSERT INTO app_users(id,username,password_hash,role,branch_code,is_active,created_at,courier_code) VALUES(?,?,?,?,?,?,?,?)',
                 (uid, 'courier_login', api._password_hash(password), 'courier', 'CAI', 1, datetime.now(timezone.utc).isoformat(), 'CR-77'))
    conn.commit(); conn.close()
    response = client.post('/v1/auth/login', json={'username':'courier_login','password':password})
    assert response.status_code == 200
    token = response.json()['access_token']
    me = client.get('/v1/auth/me', headers={'Authorization':'Bearer '+token})
    assert me.status_code == 200 and me.json()['courier_code'] == 'CR-77'
    assert 'ledger:write' not in me.json()['permissions']


def test_courier_cannot_view_another_courier(tmp_path, monkeypatch):
    monkeypatch.setenv('SHIPMENTS_LEDGER_DB', str(tmp_path / 'ledger.sqlite'))
    conn = api._ledger_conn()
    uid = str(uuid.uuid4())
    conn.execute('INSERT INTO app_users(id,username,password_hash,role,branch_code,is_active,created_at,courier_code) VALUES(?,?,?,?,?,?,?,?)',
                 (uid, 'courier_scope', api._password_hash('CourierPassword!123'), 'courier', 'CAI', 1, datetime.now(timezone.utc).isoformat(), 'CR-77'))
    row = conn.execute('SELECT * FROM app_users WHERE id=?', (uid,)).fetchone()
    token = api._issue_token(row)
    conn.commit(); conn.close()
    response = client.get('/v1/couriers/CR-88/ledger', headers={'Authorization':'Bearer '+token})
    assert response.status_code == 403


def test_branch_manager_cannot_post_to_other_branch(tmp_path, monkeypatch):
    monkeypatch.setenv('SHIPMENTS_LEDGER_DB', str(tmp_path / 'ledger.sqlite'))
    conn = api._ledger_conn()
    uid = str(uuid.uuid4())
    conn.execute('INSERT INTO app_users(id,username,password_hash,role,branch_code,is_active,created_at,courier_code) VALUES(?,?,?,?,?,?,?,?)',
                 (uid, 'branch_mgr', api._password_hash('BranchPassword!123'), 'branch_manager', 'CAI', 1, datetime.now(timezone.utc).isoformat(), None))
    row = conn.execute('SELECT * FROM app_users WHERE id=?', (uid,)).fetchone()
    token = api._issue_token(row)
    conn.commit(); conn.close()
    response = client.post('/v1/couriers/ledger', json={'courier_code':'CR-1','branch_code':'GIZ','entry_type':'collection','amount':'50','reason':'branch scope test'}, headers={'Authorization':'Bearer '+token})
    assert response.status_code == 403


def test_login_returns_signed_token_and_me_endpoint(tmp_path, monkeypatch):
    monkeypatch.setenv('SHIPMENTS_LEDGER_DB', str(tmp_path / 'ledger.sqlite'))
    conn = api._ledger_conn()
    conn.execute('INSERT INTO app_users(id,username,password_hash,role,branch_code,is_active,created_at) VALUES(?,?,?,?,?,?,?)', (str(uuid.uuid4()), 'login_admin', api._password_hash('LoginPassword!123'), 'super_admin', None, 1, datetime.now(timezone.utc).isoformat()))
    conn.commit(); conn.close()
    login = client.post('/v1/auth/login', json={'username':'login_admin','password':'LoginPassword!123'})
    assert login.status_code == 200
    token = login.json()['access_token']
    me = client.get('/v1/auth/me', headers={'Authorization':'Bearer '+token})
    assert me.status_code == 200 and me.json()['role'] == 'super_admin'
