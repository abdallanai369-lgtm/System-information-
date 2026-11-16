# Deployment checklist

- [ ] Change every password and secret in `.env`; never commit `.env`.
- [ ] Use managed PostgreSQL with automated backups for production.
- [ ] Put API behind HTTPS reverse proxy and firewall; do not expose database port.
- [ ] Implement authentication, password hashing, MFA and company/branch-scoped RBAC before public deployment.
- [ ] Review and test migration and restore procedure.
- [ ] Connect frontend to API and migrate local browser data only after validation and backup.
- [ ] Add idempotency keys and transactional payment allocation before accepting live payments.
- [ ] Obtain tax/legal review for Egyptian e-invoice integration.
