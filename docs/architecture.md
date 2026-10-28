# Architecture

```mermaid
flowchart TD
  Buyer[Buyer / Buyer App] --> API[Django REST API]
  Vendor[Vendor Dashboard / Seller] --> API
  Admin[Platform Admin] --> API
  API --> Store[(MySQL / SQLite dev)]
  API --> Adapter[ONDC / Beckn Adapter]
  Adapter --> Sandbox[ONDC Sandbox - future integration]
```

The current `ondc/catalog/` route is a mock catalog mapping for development. It is not a live ONDC participant integration. Production requires onboarding, domain-specific compliance, subscriber identity, signing and verification, callbacks, and conformance tests.
