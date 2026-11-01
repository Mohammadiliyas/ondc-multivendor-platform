# ONDC-Integrated Multi-Vendor E-Commerce Platform

A Django REST Framework marketplace prototype with buyer shopping, vendor onboarding, platform administration, split vendor fulfilment, and a development-only ONDC/Beckn adapter.

> **Status:** Active development. Core buyer/vendor/admin workflows and split fulfilment are implemented. Payment processing, production-grade deployment hardening, live ONDC network connectivity, and ONDC conformance are not yet complete. Passing CI does not mean production readiness.

## Technology

- Python 3.12+
- Django 5.1 / Django REST Framework
- JWT authentication (Simple JWT)
- MySQL for configured environments; SQLite fallback for local development and CI
- Responsive HTML/CSS/JavaScript storefront
- GitHub Actions CI
- OpenAPI schema and Swagger UI

## User roles

- **Buyer:** register, browse approved products, checkout, view own orders, and cancel while fulfilment has not progressed beyond confirmation.
- **Vendor:** apply for a store, wait for admin approval, manage own products, view only own order lines, and update own fulfilment/tracking.
- **Platform admin:** approve/suspend vendors, manage categories, inspect platform orders, and review audit activity.

A buyer order containing products from multiple vendors creates one vendor fulfilment record per vendor. Each vendor sees only its own line items. The buyer sees the combined order.

## Local setup

1. Install Python 3.12+.
2. Create and activate a virtual environment.
3. Install packages: `pip install -r requirements.txt`.
4. Copy `.env.example` to `.env` and configure a strong secret and database credentials.
5. Apply migrations: `python manage.py migrate`.
6. Create a platform administrator: `python manage.py createsuperuser`.
7. Run locally: `python manage.py runserver`.

If `MYSQL_DATABASE` is set, Django uses MySQL. Otherwise it uses SQLite.

## Main routes

| Route | Purpose |
|---|---|
| `/` | Storefront |
| `/admin/` | Django administration |
| `/api/docs/` | Swagger UI |
| `/api/schema/` | OpenAPI schema |
| `/api/health/` | Health check |
| `/api/auth/register/` | Buyer account registration |
| `/api/token/` | JWT login |
| `/api/products/` | Public catalogue / vendor-owned product management |
| `/api/vendors/` | Vendor applications and admin approval/suspension |
| `/api/dashboard/vendor/` | Vendor dashboard metrics |
| `/api/orders/create/` | Buyer checkout |
| `/api/orders/` | Buyer order history (staff can inspect all) |
| `/api/orders/<id>/cancel/` | Buyer/admin cancellation under fulfilment rules |
| `/api/vendor/fulfillments/` | Vendor-specific fulfilment list |
| `/api/vendor/fulfillments/<id>/status/` | Update own fulfilment and tracking reference |
| `/api/admin/dashboard/` | Admin platform metrics |
| `/api/admin/audit-logs/` | Admin audit history |
| `/api/ondc/catalog/` | Mock ONDC-style catalogue only |

## Checkout and fulfilment rules

- Stock is reserved inside a database transaction.
- Order items preserve product name and price at checkout.
- Checkout accepts an idempotency key.
- Vendor fulfilment records are created for each distinct vendor in the order.
- Vendors cannot access another vendor's fulfilment or update another vendor's status.
- Parent order status advances as vendor fulfilments progress.
- Buyer/admin cancellation restores stock only before any vendor has started packing or shipping.

## Payments and external services

The current checkout does **not** collect money. It creates a marketplace order only. Payment gateway integration must be configured separately with a merchant account, verified webhook signatures, idempotency, refund handling, and reconciliation. Never store card details in this application.

Analytics/error monitoring can be added through an application SDK and server-side configuration. Connecting an assistant plugin does not automatically install that SDK into this Django application.

## ONDC status

The `/api/ondc/catalog/` endpoint is a mock adapter for development. It is **not live ONDC connectivity** and does not establish ONDC conformance.

A real integration requires selecting the ONDC domain and participant role, completing network onboarding and subscriber identity setup, implementing the applicable Beckn/ONDC APIs and message flows, signing and verifying requests, handling callbacks, observability, and conformance testing against the current official specifications.

## Verification

GitHub Actions runs dependency installation, `python manage.py check`, and `python manage.py test`. Check the latest workflow result before treating a commit as verified.

## Security notes

- Do not commit `.env`, production secrets, private keys, payment credentials, or ONDC signing keys.
- Use HTTPS in deployed environments.
- Use a production database with backups and restricted network access.
- Configure CORS/CSRF trusted origins and allowed hosts for the actual deployment domain.
- Review authentication, rate limiting, audit retention, data privacy, and operational monitoring before public launch.
