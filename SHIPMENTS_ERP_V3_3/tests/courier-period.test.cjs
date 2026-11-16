const fs = require('fs');
const vm = require('vm');
const assert = require('assert');
const html = fs.readFileSync(require('path').join(__dirname, '..', 'index.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];
const elements = new Map();
function el(id) {
  if (!elements.has(id)) elements.set(id, { value: '', innerHTML: '', textContent: '', click: null });
  return elements.get(id);
}
const store = new Map();
const context = {
  document: { getElementById: el },
  localStorage: { getItem: k => store.get(k) ?? null, setItem: (k,v) => store.set(k,String(v)) },
  window: { open: () => ({ document: { write: html => { context.printed = html; }, close() {} } }) },
  alert: msg => { context.lastAlert = msg; },
  console, Date, Math, Set, JSON, Number, String
};
vm.createContext(context);
vm.runInContext(script, context);
// A single-courier, one-day statement must include only that courier's shipments.
el('courierSelect').value = 'أحمد سمير';
el('periodFrom').value = '2026-11-14';
el('periodTo').value = '2026-11-16';
vm.runInContext('generateCourierStatement()', context);
let doc = context.window.__currentCourierDoc;
assert.equal(doc.rows.length, 2);
assert.equal(doc.expected, 5650);
assert.equal(doc.collected, 5650);
assert.equal(doc.remitted, 0);
assert.equal(doc.custody, 5650);
assert.equal(doc.notCollected, 0);
// Period exclusion: date range with no courier deliveries returns zero rows and zero totals.
el('periodFrom').value = '2026-11-01';
el('periodTo').value = '2026-11-02';
vm.runInContext('generateCourierStatement()', context);
doc = context.window.__currentCourierDoc;
assert.equal(doc.rows.length, 0);
assert.equal(doc.custody, 0);
// Saving preserves a reference snapshot locally; printing creates a printable document.
vm.runInContext('saveCourierDoc(window.__currentCourierDoc.ref)', context);
assert.equal(JSON.parse(store.get('shipments_erp_courier_docs_v1')).length, 1);
vm.runInContext('printCourierDoc(window.__currentCourierDoc.ref)', context);
assert(context.printed.includes('فاتورة تسوية إلكترونية داخلية'));
console.log('4 courier-period tests passed');
