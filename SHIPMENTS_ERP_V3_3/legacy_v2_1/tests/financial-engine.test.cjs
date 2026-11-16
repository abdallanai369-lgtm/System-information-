const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const html = fs.readFileSync(new URL('../index.html', `file://${__filename}`), 'utf8');
const start = html.indexOf('/* FINANCIAL_ENGINE_START */');
const end = html.indexOf('/* FINANCIAL_ENGINE_END */');
assert.ok(start >= 0 && end > start, 'financial engine markers must exist');
const engine = html.slice(start + '/* FINANCIAL_ENGINE_START */'.length, end);

function makeDb() {
  return {
    customers: [
      { id: 'CUS-2026-0001', name: 'Customer One' },
      { id: 'CUS-2026-0002', name: 'Customer Two' },
    ],
    invoices: [
      { id: 'INV-2026-0001', customerId: 'CUS-2026-0001', date: '2026-01-01', amount: 100 },
      { id: 'INV-2026-0002', customerId: 'CUS-2026-0001', date: '2026-01-15', amount: 50 },
      { id: 'INV-2026-0003', customerId: 'CUS-2026-0002', date: '2026-01-05', amount: 200 },
    ],
    payments: [
      {
        id: 'RCT-2026-0001', customerId: 'CUS-2026-0001', date: '2026-01-10',
        amount: 70, method: 'نقدي', allocations: [{ invoiceId: 'INV-2026-0001', amount: 40 }],
      },
    ],
    statements: [],
    sequences: {},
  };
}

const db = makeDb();
const context = vm.createContext({ db });
vm.runInContext(engine, context, { timeout: 1000 });
const run = (name, fn) => {
  try { fn(); console.log(`PASS ${name}`); }
  catch (error) { console.error(`FAIL ${name}: ${error.message}`); process.exitCode = 1; }
};

run('separates cash received, allocated amount, invoice outstanding and unapplied credit', () => {
  const f = context.customerFinancials('CUS-2026-0001');
  assert.equal(f.inv, 150);
  assert.equal(f.paid, 70);
  assert.equal(f.allocated, 40);
  assert.equal(f.invoiceOutstanding, 110);
  assert.equal(f.unappliedCredit, 30);
  assert.equal(f.netReceivable, 80);
  assert.equal(context.paidForInvoice('INV-2026-0001'), 40);
});

run('accepts one receipt allocated across multiple invoices and retains the unallocated remainder', () => {
  const result = context.validatePayment('CUS-2026-0001', 80, [
    { invoiceId: 'INV-2026-0001', amount: 60 },
    { invoiceId: 'INV-2026-0002', amount: 10 },
  ]);
  assert.equal(result.ok, true);
  assert.equal(result.allocated, 70);
  assert.equal(result.unapplied, 10);
  assert.equal(result.allocations.length, 2);
});

run('rejects allocation to another customer invoice', () => {
  const result = context.validatePayment('CUS-2026-0001', 50, [
    { invoiceId: 'INV-2026-0003', amount: 10 },
  ]);
  assert.equal(result.ok, false);
  assert.match(result.error, /عميل آخر/);
});

run('rejects allocation above the invoice outstanding amount', () => {
  const result = context.validatePayment('CUS-2026-0001', 100, [
    { invoiceId: 'INV-2026-0001', amount: 61 },
  ]);
  assert.equal(result.ok, false);
  assert.match(result.error, /المتبقي/);
});

run('rejects allocation totals greater than the cash receipt', () => {
  const result = context.validatePayment('CUS-2026-0001', 50, [
    { invoiceId: 'INV-2026-0001', amount: 30 },
    { invoiceId: 'INV-2026-0002', amount: 25 },
  ]);
  assert.equal(result.ok, false);
  assert.match(result.error, /أكبر من مبلغ الدفعة/);
});

run('rejects duplicate invoice allocations', () => {
  const result = context.validatePayment('CUS-2026-0001', 50, [
    { invoiceId: 'INV-2026-0001', amount: 10 },
    { invoiceId: 'INV-2026-0001', amount: 10 },
  ]);
  assert.equal(result.ok, false);
  assert.match(result.error, /تكرار الفاتورة/);
});

run('builds period statement with opening balance and running balances', () => {
  const snapshot = context.buildStatementSnapshot('CUS-2026-0001', '2026-01-10', '2026-01-31', '2026-02-01');
  assert.equal(snapshot.customerName, 'Customer One');
  assert.equal(snapshot.customerPhone, '');
  assert.equal(snapshot.opening, 100);
  assert.equal(snapshot.totalDebit, 50);
  assert.equal(snapshot.totalCredit, 70);
  assert.equal(snapshot.closing, 80);
  assert.deepEqual(Array.from(snapshot.rows, r => r.balance), [30, 80]);
});

run('rejects an invalid statement period', () => {
  assert.throws(() => context.buildStatementSnapshot('CUS-2026-0001', '2026-02-01', '2026-01-01', '2026-02-02'));
});

run('statement snapshot remains unchanged after later source-data changes', () => {
  const snapshot = context.buildStatementSnapshot('CUS-2026-0001', '2026-01-01', '2026-01-31', '2026-02-01');
  const frozenClosing = snapshot.closing;
  const frozenName = snapshot.customerName;
  db.customers[0].name = 'Renamed Customer';
  db.payments.push({ id: 'RCT-2026-0002', customerId: 'CUS-2026-0001', date: '2026-02-02', amount: 25, allocations: [] });
  assert.equal(snapshot.closing, frozenClosing);
  assert.equal(snapshot.customerName, frozenName);
});

run('generates a non-colliding sequential account ID using max suffix and stored sequence', () => {
  db.sequences['CUS-2026'] = 4;
  const id = context.nextId('CUS', [{ id: 'CUS-2026-0009' }], 6, 2026);
  assert.equal(id, 'CUS-2026-000010');
  assert.equal(db.sequences['CUS-2026'], 10);
});

if (process.exitCode) process.exit(process.exitCode);
console.log('All financial engine tests passed.');
