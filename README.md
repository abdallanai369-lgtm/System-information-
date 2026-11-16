# SHIPMENTS ERP V2

نظام إدارة وتشغيل شركة شحن. يحتوي هذا المستودع على واجهة النظام الحالية + Backend API باستخدام FastAPI + قاعدة PostgreSQL.

> **تنبيه مهم:** هذه حزمة أساس احترافية قابلة للتطوير والنشر، وليست اعتمادًا بأن النظام أصبح جاهزًا للإنتاج أو متوافقًا ضريبيًا. اختبر على بيانات تجريبية أولًا، وراجع إعدادات الأمان والنسخ الاحتياطي قبل بيانات العملاء الحقيقية.

## المكونات
- `frontend/index.html`: واجهة النظام الحالية محفوظة كما هي.
- `backend`: API وطبقة البيانات والصلاحيات الأولية.
- PostgreSQL 16 عبر Docker Compose.
- Alembic لإدارة تغييرات قاعدة البيانات.
- فحوصات API أساسية.

## التشغيل المحلي (Windows / macOS / Linux)
1. ثبّت Docker Desktop وشغّله.
2. انسخ `.env.example` إلى `.env` وغيّر كلمات المرور والمفتاح السري.
3. من مجلد المشروع شغّل: `docker compose up --build -d`
4. افتح `http://localhost:8000/docs` لتجربة API.
5. افتح `frontend/index.html` لواجهة النظام الحالية.

## التشغيل بدون Docker (للتطوير)
```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```
اضبط `DATABASE_URL` في البيئة على PostgreSQL. SQLite ليس بديلًا للإنتاج.

## قاعدة البيانات
- PostgreSQL مع UUIDs، مفاتيح خارجية، قيود تحقق، فهارس، وحقول `created_at/updated_at`.
- الجداول الأساسية: companies, branches, users, customers, invoices, invoice_lines, payments, payment_allocations, journal_entries, journal_lines, audit_logs.
- القيود المحاسبية لا تُحذف بعد الترحيل؛ التصحيح يكون بقيد عكسي موثق.
- ترحيل قاعدة البيانات: `docker compose exec api alembic upgrade head`.

## API المتاح
- `GET /health`
- `GET/POST /api/v1/customers`
- `GET/POST /api/v1/invoices`
- `GET/POST /api/v1/payments`
- `GET /api/v1/reports/customer-balance/{customer_id}`

الـ API لا يفتح على الإنترنت افتراضيًا في بيئة الإنتاج إلا خلف HTTPS وReverse Proxy. المصادقة والصلاحيات متعددة الأدوار يجب استكمال ربطها بحسابات المستخدمين قبل الإطلاق العام.

## رفع المشروع إلى GitHub
1. أنشئ Repository جديدًا على GitHub.
2. لا ترفع ملف `.env` أو نسخ قواعد البيانات أو مفاتيح API.
3. داخل مجلد المشروع:
```bash
git init
git add .
git commit -m "Initial SHIPMENTS ERP V2 with PostgreSQL backend"
git branch -M main
git remote add origin https://github.com/USERNAME/REPOSITORY.git
git push -u origin main
```
4. استبدل `USERNAME/REPOSITORY` برابط مستودعك الحقيقي.

## قبل الإنتاج
- إعداد HTTPS ونسخ احتياطي مجدول واختبار استعادة النسخة.
- إضافة مصادقة قوية (OIDC/ JWT مع تدوير refresh tokens) وربط RBAC بالشركة والفرع.
- مراجعة أمنية واختبارات ضغط وتزامن.
- ربط الواجهة بالـ API بدل التخزين المحلي، مع ترحيل بيانات LocalStorage بعد مطابقة وموافقة المستخدم.
- اعتماد التكامل الضريبي المصري عبر القنوات الرسمية ومتطلبات مصلحة الضرائب؛ لا تعتبر PDF أو QR وحدهما فاتورة إلكترونية معتمدة.
