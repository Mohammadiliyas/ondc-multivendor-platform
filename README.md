# ONDC-Integrated Multi-Vendor E-Commerce Platform

Django + Django REST Framework MVP for a multi-vendor seller platform, with role-based access, vendor approval, inventory, order workflows, a responsive storefront, and a clearly marked **mock ONDC adapter**.

The requested primary database is MySQL. SQLite remains the default for a zero-setup local smoke run; set the `MYSQL_*` environment variables to use MySQL.

## Included
- Buyer, Vendor, Platform Admin roles
- JWT access/refresh token endpoints
- Vendor registration/profile approval workflow
- Vendor-isolated product management and searchable public catalog
- Stock-aware order creation in a database transaction
- Order status updates and role-filtered order visibility
- Internal catalog mapping and mock ONDC callback endpoints
- Django Admin, tests, Dockerfile, and Render Blueprint

## Run locally
1. Install Python 3.12+ and (for MySQL) a MySQL 8.x server plus the build prerequisites required by `mysqlclient`.
2. Create and activate a virtual environment.
3. `pip install -r requirements.txt`
4. `cp .env.example .env` (Windows: `copy .env.example .env`). Change `DJANGO_SECRET_KEY` and configure `MYSQL_*` values if using MySQL. If no MySQL variables are set, local development uses SQLite.
5. `python manage.py migrate`
6. `python manage.py createsuperuser`
7. `python manage.py runserver`

API base: `http://127.0.0.1:8000/api/`

## Main endpoints
- `GET /api/health/`
- `POST /api/auth/register/`
- `POST /api/token/` and `POST /api/token/refresh/`
- `GET /api/categories/`
- `GET /api/products/?search=phone&category=Electronics`
- `POST /api/vendors/`
- `POST /api/admin/vendors/{id}/approve/` and `/suspend/`
- `POST /api/products/`
- `POST /api/orders/create/`
- `GET /api/orders/`
- `POST /api/orders/{id}/status/`
- `GET /api/ondc/catalog/`
- Mock callback endpoints: `/api/ondc/on_search/`, `on_select/`, `on_init/`, `on_confirm/`, `on_status/`, `on_cancel/`

For authenticated requests use `Authorization: Bearer <access_token>`.

## Test
`python manage.py test`

## Important limitations before production
This is an API-first functional MVP scaffold, not a certified ONDC network participant. ONDC production participation requires network onboarding/registry details, subscriber IDs, Beckn protocol compliance, cryptographic signing and verification, callbacks, logs, and conformance testing. Payment gateway, logistics integration, email/SMS, and real ONDC credentials are not configured. Multi-vendor parent-order status changes are admin-only until per-vendor shipment workflows are implemented. Do not use mock callback endpoints as a production ONDC integration.

Before deployment set a strong secret, correct `ALLOWED_HOSTS`, production database, HTTPS, backups, logging, and security review.

## API documentation
- Swagger UI: `/api/docs/`
- OpenAPI schema: `/api/schema/`
- Postman collection: `postman_collection.json`
- Architecture: `docs/architecture.md`

## Verification status
Python syntax and storefront JavaScript syntax were checked in the build environment. Django runtime checks and automated tests have not yet been run because Django dependencies could not be downloaded in that environment.
