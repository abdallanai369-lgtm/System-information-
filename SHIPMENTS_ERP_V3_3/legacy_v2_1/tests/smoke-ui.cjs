const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');

const html = fs.readFileSync(new URL('../index.html', `file://${__filename}`), 'utf8');
const match = html.match(/<script>([\s\S]*?)<\/script>/);
assert.ok(match, 'inline application script must exist');
const elements = new Map();
function element(id) {
  if (!elements.has(id)) {
    elements.set(id, {
      id, value: '', innerHTML: '', textContent: '', dataset: {}, onclick: null,
      classList: { add() {}, remove() {}, toggle() {} },
      addEventListener() {},
      querySelector() { return null; },
      querySelectorAll() { return []; },
    });
  }
  return elements.get(id);
}
const storage = new Map();
const context = vm.createContext({
  console,
  alert(message) { throw new Error(`Unexpected alert: ${message}`); },
  localStorage: {
    getItem(key) { return storage.has(key) ? storage.get(key) : null; },
    setItem(key, value) { storage.set(key, value); },
  },
  document: {
    getElementById: element,
    querySelectorAll() { return []; },
    createElement() { return element('created-link'); },
  },
  URL: { createObjectURL() { return 'blob:test'; }, revokeObjectURL() {} },
  Blob,
});
vm.runInContext(match[1], context, { timeout: 2000 });

assert.match(element('dashStats').innerHTML, /المتبقي على الفواتير/);
assert.match(element('dashStats').innerHTML, /39,500\.00/);
assert.match(element('dashStats').innerHTML, /18,000\.00/);
context.renderCustomers();
context.renderInvoices();
context.renderPayments();
context.renderShipments();
context.renderReports();
context.fillCustomerOptions();
assert.match(element('customersRows').innerHTML, /CUS-2026-0001/);
assert.match(element('paymentsRows').innerHTML, /RCT-2026-0001/);
assert.match(element('debtRows').innerHTML, /12,000\.00/);

element('statementCustomer').value = 'CUS-2026-0001';
element('fromDate').value = '2026-01-01';
element('toDate').value = '2026-02-28';
context.generateStatement();
assert.match(element('statementResult').innerHTML, /ST-2026-00001/);
assert.match(element('statementResult').innerHTML, /12,000\.00/);
const persisted = JSON.parse(storage.get('shipments_erp_demo_v1'));
assert.equal(persisted.statements.length, 1);

context.openModal('payment', 'CUS-2026-0001');
element('f_customer').value = 'CUS-2026-0001';
context.refreshUnpaid();
assert.match(element('modalBody').innerHTML, /allocationList/);
assert.match(element('allocationList').innerHTML, /INV-2026-0002/);

console.log('PASS full application script initializes with demo data');
console.log('PASS dashboard, customers, invoices, payments, shipments and reports render');
console.log('PASS statement generation stores a sequential snapshot');
console.log('PASS multi-invoice payment editor renders');
console.log('All UI smoke tests passed.');

// Backward-compatibility smoke test for records created before allocations existed.
const legacyElements = new Map();
function legacyElement(id) {
  if (!legacyElements.has(id)) legacyElements.set(id, {
    id, value: '', innerHTML: '', textContent: '', dataset: {}, onclick: null,
    classList: { add() {}, remove() {}, toggle() {} }, addEventListener() {},
    querySelector() { return null; }, querySelectorAll() { return []; },
  });
  return legacyElements.get(id);
}
const legacyState = {
  customers: [{ id: 'CUS-2026-0099', name: 'Legacy Customer', phone: '01000000000', type: 'شركة' }],
  invoices: [{ id: 'INV-2026-0099', customerId: 'CUS-2026-0099', date: '2026-01-01', amount: 100 }],
  payments: [{ id: 'RCT-2026-0099', customerId: 'CUS-2026-0099', date: '2026-01-02', amount: 25 }],
  shipments: [], statements: [],
};
const legacyContext = vm.createContext({
  console,
  alert(message) { throw new Error(`Unexpected legacy alert: ${message}`); },
  localStorage: { getItem() { return JSON.stringify(legacyState); }, setItem() {} },
  document: { getElementById: legacyElement, querySelectorAll() { return []; }, createElement() { return legacyElement('link'); } },
  URL: { createObjectURL() { return 'blob:legacy'; }, revokeObjectURL() {} },
  Blob,
});
vm.runInContext(match[1], legacyContext, { timeout: 2000 });
assert.match(legacyElement('dashStats').innerHTML, /100\.00/);
assert.match(legacyElement('dashStats').innerHTML, /25\.00/);
legacyContext.renderPayments();
assert.match(legacyElement('paymentsRows').innerHTML, /25\.00/);
console.log('PASS older localStorage payments without allocations are normalized safely');
