# Staging deployment on Render

This project is prepared for a Docker-based Render web service and a managed Render PostgreSQL database.

## Before creating resources

1. Choose the Render workspace that should own this marketplace.
2. Create a PostgreSQL database in that same workspace and the Singapore region (close to India).
3. Create a Docker web service connected to `https://github.com/Mohammadiliyas/ondc-multivendor-platform`, using the repository's `Dockerfile` and default branch.
4. Attach the database's **internal** connection string as `DATABASE_URL`.

## Required web-service environment variables

- `DJANGO_SECRET_KEY`: generate a unique, high-entropy secret; never commit it.
- `DJANGO_DEBUG=False`
- `ALLOWED_HOSTS`: include the Render hostname, e.g. `your-service.onrender.com`.
- `CSRF_TRUSTED_ORIGINS`: include the HTTPS origin, e.g. `https://your-service.onrender.com`.
- `DATABASE_URL`: Render PostgreSQL internal connection string.
- `PLATFORM_COMMISSION_PERCENT=10`
- `UNPAID_ORDER_EXPIRY_MINUTES=30`

Do not set Razorpay keys until a merchant account is opened. Checkout remains unavailable until test credentials are configured.

## Deployment behaviour

The container collects static assets during image build. At container startup it runs Django migrations and then starts Gunicorn. The health endpoint is `/api/health/`.

## Scheduled unpaid-order expiry

Create a separate Render Cron Job from the same repository and branch, using Docker runtime and the repository Dockerfile. Override its command to:

```sh
python manage.py expire_unpaid_orders
```

Use a schedule such as `*/5 * * * *` (every five minutes). Copy the same `DATABASE_URL`, `DJANGO_SECRET_KEY`, and relevant marketplace settings into the cron job environment. Do not run this command as a second web-server process.

## First staging smoke tests

- `GET /api/health/` returns HTTP 200.
- `GET /` loads the storefront and static styles.
- `GET /api/docs/` loads API documentation.
- Create a test buyer and a test vendor; verify vendor approval and tenant isolation.
- Create a test product, place an unpaid test order, and confirm stock is reserved.
- Run the expiry command against an intentionally expired test order and verify stock is restored.
- Verify no real payment is attempted; Razorpay merchant credentials have not been configured.

## Important

This is a staging deployment checklist, not a production-readiness certification. Before real customers or real money, complete security review, backups/restore test, monitoring, privacy/legal requirements, payment and refund reconciliation, and ONDC sandbox/conformance testing.
