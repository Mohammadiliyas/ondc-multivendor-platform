# ONDC-Integrated Multi-Vendor E-Commerce Platform

Django starter scaffold for a multi-vendor marketplace with a product catalog and a clearly marked **mock ONDC catalog adapter**.

> **Development status:** This repository is an initial scaffold, not a complete or production-ready marketplace. Full authentication/role enforcement, vendor CRUD workflows, order checkout, payment/logistics integrations, production ONDC signing/callbacks, and production deployment still need implementation and verification.

## Technology
- Python / Django
- Django REST Framework dependencies included for API expansion
- MySQL when `MYSQL_DATABASE` is configured; SQLite otherwise for local development
- Django Admin
- GitHub Actions CI scaffold

## Quick start
1. Install Python 3.12+.
2. Create and activate a virtual environment.
3. Install dependencies: `pip install -r requirements.txt`
4. Copy `.env.example` to `.env`; change the secret and configure database variables.
5. Run `python manage.py migrate`
6. Create an admin user: `python manage.py createsuperuser`
7. Start the server: `python manage.py runserver`

## Current endpoints
- `GET /api/health/` — health check
- `GET /api/catalog/` — active products from approved vendors; optional `?search=term`
- `GET /api/ondc/catalog/` — development-only mock ONDC-style catalog mapping

Django Admin is available at `/admin/`.

## Environment variables
See `.env.example`. If `MYSQL_DATABASE` is set, configure the matching MySQL host, port, user, password and database. If it is unset, SQLite is used.

## ONDC status
The ONDC catalog endpoint is only a mock adapter for development. It does **not** establish live ONDC connectivity or conformance. Production participation requires choosing the relevant ONDC domain and participant role, onboarding and subscriber identity, implementing current Beckn/ONDC protocol requirements, signing and verification, callbacks, observability, and conformance testing.

## Verification
GitHub Actions is configured to install dependencies and run Django checks and tests. The checks have not yet been confirmed passing. Validate the project in CI before deployment; never commit real credentials or production secrets.
