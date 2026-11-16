# دليل API V3.3 — المصادقة والصلاحيات

كل المسارات المالية التالية تتطلب ترويسة `Authorization: Bearer TOKEN`.

## تسجيل الدخول
`POST /v1/auth/login`
```json
{"username":"admin","password":"ضع-كلمة-المرور-التي-أنشأتها"}
```
يعيد `access_token` وبيانات الدور والصلاحيات.

## بيانات المستخدم الحالي
`GET /v1/auth/me`

## إنشاء مستخدم
`POST /v1/admin/users` — صلاحية super_admin فقط.
```json
{"username":"cashier_cairo","password":"StrongPassword!2026","role":"treasury","branch_code":"CAI"}
```

## إضافة حركة عهدة
`POST /v1/couriers/ledger` — صلاحية ledger:write.
```json
{"courier_code":"CR-100","branch_code":"CAI","entry_type":"collection","amount":"1250.00","reason":"تحصيل COD تجريبي","source_reference":"SHP-DEMO-100"}
```

## قراءة الدفتر
`GET /v1/couriers/CR-100/ledger` — صلاحية ledger:read.

## عكس حركة
`POST /v1/couriers/ledger/CL-REFERENCE/reverse` — صلاحية ledger:reverse.
```json
{"reason":"تصحيح قيد تجريبي مكرر"}
```

## سجل المراجعة
`GET /v1/admin/audit?limit=100` — صلاحية audit:read.

## الأدوار
| الدور | الصلاحيات الأساسية |
|---|---|
| super_admin | إدارة المستخدمين، قراءة/إضافة/عكس القيود، سجل المراجعة |
| company_manager | قراءة/إضافة/عكس القيود وسجل المراجعة |
| branch_manager | قراءة/إضافة/عكس القيود داخل الفرع المعيّن |
| treasury | قراءة/إضافة القيود داخل الفرع المعيّن |
| auditor | قراءة الدفاتر وسجل المراجعة |
| courier | قراءة دفتر المندوب المرتبط بالحساب فقط |

> هذه صلاحيات API تجريبية وليست اعتمادًا تشغيليًا نهائيًا. لا تربطها بحسابات حقيقية قبل مراجعة أمنية وربط قاعدة بيانات إنتاجية وتفعيل HTTPS وحدود محاولات الدخول.
