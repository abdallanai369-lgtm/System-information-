-- PostgreSQL schema draft for SHIPMENTS ERP V3. Apply only after review and approval.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE TABLE branches (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), code text NOT NULL UNIQUE, name text NOT NULL, is_active boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE app_users (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  username text NOT NULL UNIQUE,
  password_hash text NOT NULL,
  role text NOT NULL CHECK (role IN ('super_admin','company_manager','branch_manager','treasury','auditor','courier')),
  branch_id uuid REFERENCES branches(id),
  courier_code text,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE customers (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), customer_code text NOT NULL UNIQUE, name text NOT NULL, phone text, customer_type text NOT NULL CHECK (customer_type IN ('company','individual')), is_active boolean NOT NULL DEFAULT true, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE couriers (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), courier_code text NOT NULL UNIQUE, branch_id uuid NOT NULL REFERENCES branches(id), full_name text NOT NULL, is_active boolean NOT NULL DEFAULT true);
ALTER TABLE app_users ADD CONSTRAINT app_users_courier_code_fk FOREIGN KEY (courier_code) REFERENCES couriers(courier_code);
CREATE TABLE shipments (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tracking_no text NOT NULL UNIQUE, customer_id uuid NOT NULL REFERENCES customers(id), branch_id uuid NOT NULL REFERENCES branches(id), courier_id uuid REFERENCES couriers(id), recipient_name text NOT NULL, recipient_phone text, destination text, status text NOT NULL, shipping_fee numeric(14,2) NOT NULL DEFAULT 0 CHECK (shipping_fee >= 0), cod_amount numeric(14,2) NOT NULL DEFAULT 0 CHECK (cod_amount >= 0), delivered_at timestamptz, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE cod_collections (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), shipment_id uuid NOT NULL UNIQUE REFERENCES shipments(id), collected_amount numeric(14,2) NOT NULL CHECK (collected_amount >= 0), collected_by uuid REFERENCES couriers(id), collected_at timestamptz NOT NULL, evidence_ref text, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE courier_settlements (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), branch_id uuid NOT NULL REFERENCES branches(id), courier_id uuid NOT NULL REFERENCES couriers(id), reference_no text NOT NULL UNIQUE, expected_amount numeric(14,2) NOT NULL CHECK (expected_amount >= 0), declared_amount numeric(14,2) NOT NULL CHECK (declared_amount >= 0), received_amount numeric(14,2) NOT NULL DEFAULT 0 CHECK (received_amount >= 0), status text NOT NULL CHECK (status IN ('draft','submitted','under_review','approved','rejected')), submitted_at timestamptz, approved_at timestamptz, approved_by uuid, created_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE settlement_lines (settlement_id uuid NOT NULL REFERENCES courier_settlements(id), shipment_id uuid NOT NULL REFERENCES shipments(id), expected_amount numeric(14,2) NOT NULL CHECK (expected_amount >= 0), declared_amount numeric(14,2) NOT NULL CHECK (declared_amount >= 0), received_amount numeric(14,2) NOT NULL DEFAULT 0 CHECK (received_amount >= 0), discrepancy_reason text, PRIMARY KEY(settlement_id, shipment_id));
CREATE TABLE audit_log (id bigserial PRIMARY KEY, actor_id uuid, action text NOT NULL, entity_type text NOT NULL, entity_id uuid, before_data jsonb, after_data jsonb, created_at timestamptz NOT NULL DEFAULT now());
CREATE INDEX shipments_branch_status_idx ON shipments(branch_id,status);
CREATE INDEX shipments_courier_status_idx ON shipments(courier_id,status);
CREATE INDEX shipments_created_idx ON shipments(created_at);
CREATE INDEX cod_collections_date_idx ON cod_collections(collected_at);
CREATE INDEX settlements_courier_status_idx ON courier_settlements(courier_id,status);
-- IMPORTANT: settlement approval, ledger posting and cash receipt must be implemented
-- as one backend transaction with role checks, row locks and immutable audit records.

-- V3.2 immutable courier custody ledger. Corrections are new reversal rows, never UPDATE/DELETE.
CREATE TABLE courier_ledger_entries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  reference_no text NOT NULL UNIQUE,
  courier_id uuid NOT NULL REFERENCES couriers(id),
  branch_id uuid NOT NULL REFERENCES branches(id),
  entry_type text NOT NULL CHECK (entry_type IN ('opening','assignment','collection','remittance','adjustment','reversal')),
  debit_amount numeric(14,2) NOT NULL DEFAULT 0 CHECK (debit_amount >= 0),
  credit_amount numeric(14,2) NOT NULL DEFAULT 0 CHECK (credit_amount >= 0),
  running_balance numeric(14,2) NOT NULL CHECK (running_balance >= 0),
  source_reference text,
  reversal_of uuid REFERENCES courier_ledger_entries(id),
  reason text NOT NULL,
  created_by uuid NOT NULL REFERENCES app_users(id),
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (NOT (debit_amount > 0 AND credit_amount > 0)),
  CHECK ((entry_type = 'reversal') = (reversal_of IS NOT NULL))
);
CREATE UNIQUE INDEX courier_ledger_one_reversal_idx ON courier_ledger_entries(reversal_of) WHERE reversal_of IS NOT NULL;
CREATE INDEX courier_ledger_courier_date_idx ON courier_ledger_entries(courier_id, created_at, id);
-- Enforce immutability at the database boundary as well as the API boundary.
CREATE OR REPLACE FUNCTION reject_courier_ledger_mutation() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'courier ledger entries are immutable; post a reversal instead'; END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER courier_ledger_no_update BEFORE UPDATE OR DELETE ON courier_ledger_entries
FOR EACH ROW EXECUTE FUNCTION reject_courier_ledger_mutation();


-- V3.3 centralized audit trail. Append-only by application policy; production DB role
-- must be denied UPDATE/DELETE on audit_events and ledger entries.
CREATE TABLE audit_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  actor_id uuid NOT NULL REFERENCES app_users(id),
  action text NOT NULL,
  entity_type text NOT NULL,
  entity_reference text,
  details jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_events_created_at_idx ON audit_events(created_at DESC);
CREATE INDEX audit_events_actor_idx ON audit_events(actor_id, created_at DESC);

-- V3.3 append-only audit protection. Grant SELECT/INSERT to the application role only.
CREATE OR REPLACE FUNCTION reject_audit_mutation() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'audit events are append-only'; END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER audit_events_no_update_delete BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation();

CREATE OR REPLACE FUNCTION reject_audit_mutation() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'audit events are immutable'; END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER audit_events_no_update BEFORE UPDATE OR DELETE ON audit_events
FOR EACH ROW EXECUTE FUNCTION reject_audit_mutation();
