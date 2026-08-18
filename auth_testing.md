# Commerce OS Authentication Testing

1. Login as Master Admin with `admin@commerceos.local` / `Admin123!`.
2. Verify `/api/auth/me` returns `MASTER_ADMIN` and `/api/admin/overview` returns tenants and platform metrics.
3. Verify Master Admin cannot call `/api/dashboard` or see client order/inventory records.
4. Login as a tenant owner using the credentials in `/app/memory/test_credentials.md`.
5. Verify `/api/auth/me` returns `TENANT_OWNER` and the correct `tenant_id`.
6. Verify `/api/dashboard` returns only that tenant's products and orders.
7. Verify the owner cannot call `/api/admin/overview` or access another tenant by changing headers.
8. Verify logout clears the session and protected endpoints return 401.