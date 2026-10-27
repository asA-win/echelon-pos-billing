# Echelon POS — Retail & Textile Billing Suite

A responsive POS and billing web application built for a textile/retail store. Includes role-based sign-in, inventory CRUD, staff and supplier management, sales checkout, printable receipts, returns/refunds, ledger, reports, and a mobile-first admin experience.

## Demo accounts
- **Admin:** `admin` / `Admin@123`
- **Billing staff:** `staff` / `Staff@123`

Change demo passwords and `SECRET_KEY` before deploying anywhere public. This is a demonstration/assessment build; review security, tax rules, refund policies, and operational requirements before production use.

## Run locally
Requires Python 3.10+.

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000. SQLite database `pos.db` is created automatically and populated with sample products and suppliers on first run.

## Portals and routes
- `/login` — authentication
- `/dashboard` — admin overview
- `/products` — product CRUD and stock
- `/staff` — staff accounts and role management
- `/suppliers` — supplier directory
- `/billing` — staff POS and checkout
- `/transactions` — sales history
- `/receipt/<sale_id>` — printable invoice
- `/returns` — return/refund processing
- `/ledger` — income/refund ledger
- `/reports` — sales, category, and top-product reports
- `/mobile` — mobile-first admin dashboard (responsive layout)
- `/mobile/products`, `/mobile/staff`, etc. — mobile entry paths redirect to the same responsive functional pages

## Deployment
Deploy to a Python host (Render, Railway, or similar) using `requirements.txt` and `Procfile`. Set a strong `SECRET_KEY`; configure persistent disk/storage for `pos.db` or replace SQLite with a managed database before production. A live URL and public GitHub repository are not created by this ZIP; deploy and push the included source to provide those submission items.

## Design / architecture
- Flask server-rendered UI with lightweight JavaScript for checkout and charts
- SQLite relational schema with foreign keys
- Password hashing via PBKDF2-HMAC-SHA256
- Server-side role checks and checkout stock validation
- Responsive navigation and dedicated `/mobile` admin route
- Sales update stock atomically; returns restore stock and write a negative ledger entry
