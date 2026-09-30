# Symposium website (live version)

The internet-ready version of the Symposium Management System. Participants register and pay
online; organisers run the registration desk, verify payments, check people in with QR codes,
score events and publish results. It uses the same database ideas as the desktop app (tag
`v1-evaluation`), which is kept unchanged for the college evaluation.

| Layer | Technology |
|---|---|
| Web app | Python **Flask** (server-rendered pages, works on phones) |
| Database | **MySQL 8.0** through **mysql-connector-python** (connection pool) |
| Payments | UPI QR direct to the college account, Razorpay (UPI + net banking), cash at desk |
| Documents | fpdf2 (tickets, receipts, certificates, attendance sheets), qrcode |

## Quick start (on your computer)

```bash
cd web
pip install -r requirements.txt
python manage.py init-db          # asks for the MySQL root password once, then your first admin
python manage.py seed-demo        # optional: load the demo data set
python run_dev.py                 # http://127.0.0.1:5000
```

Demo accounts (after `seed-demo`), password `Demo@1234`:
`admin@demo.symposium`, `cashier@demo.symposium`, `coordinator@demo.symposium`, `student@demo.symposium`.

## What it does

**Public site:** home page with a rolling **flash-news banner**, events with seat bars, schedule,
results and college leaderboard, certificate verification, and the terms, privacy and refund pages
that payment gateways require.

**Participants:**
- Sign up with e-mail verification.
- Register for individual or **team** events, with **coupons** and **early-bird** prices.
- **Waitlist** when an event is full, with automatic promotion when a seat frees up.
- Pay by **UPI QR** (then submit the UPI reference), **online** (Razorpay) or **at the desk**.
- Instant **QR ticket** and PDF receipt; certificate after attendance.
- Feedback and profile.
- Participants cannot cancel. Only admins cancel and refund.

**Staff roles:**

| Role | Can do |
|---|---|
| Admin | Everything |
| Cashier | Registration desk (walk-ins), payment verification, bank-statement matching, cash report, check-in |
| Coordinator / judge | Check-in, registrations and scoring, only for their assigned events |

**Admin:**
- **Events:** venue clash check; changes to date, time or venue are **announced automatically** in the flash news and by e-mail.
- **Content and people:** news, participants, staff accounts, coupons, venues and lists, feedback.
- **Insights:** 10 reports (CSV/PDF), a read-only **SQL console**, audit log, e-mail outbox.
- **System:** settings (branding, rules, UPI ID, gateway keys, SMTP, policies), **backups and restore**, and **demo data / go live**.

## Security
- **Passwords and accounts:**
  - Passwords are PBKDF2-SHA256 hashed with a per-user salt.
  - Accounts lock after 5 failed attempts.
  - Sessions rotate on login and are revoked when the password changes.
  - Staff must change their temporary password on first sign-in.
- **Request protection:**
  - CSRF tokens on every form.
  - Strict Content-Security-Policy with no inline scripts; X-Frame-Options, nosniff and HSTS on HTTPS.
  - Rate limits on login, sign-up, password reset, payment reference submission and the SQL console.
- **Data access:**
  - Every query is parameterised.
  - The site connects as a limited MySQL user, not root. The SQL console uses a second read-only user that cannot see password hashes.
  - Participants can only open their own registrations.
- **Payments:**
  - The amount always comes from the database.
  - Gateway callbacks and webhooks are HMAC-verified and checked against the Razorpay API.
  - The demo gateway is disabled on a live site.
  - Each UPI reference can be used only once.
- **Other:**
  - Secrets live only in `instance/config.ini`, which is git-ignored.
  - Uploads are type-checked. CSV exports are protected against formula injection.

## Tests

```bash
set MYSQL_ROOT_PASSWORD=your_root_password      (PowerShell: $env:MYSQL_ROOT_PASSWORD="...")
python -m pytest -q
```

37 tests run against a throw-away `symposium_test` database. They cover:
- Registration rules, including a concurrency test where 20 people race for 5 seats.
- Payments, reconciliation, webhook forgery and the live-site gateway lock.
- Security headers, CSRF, lock-out and role access.
- Backup and restore, and go-live.

More documents: [DEPLOY.md](DEPLOY.md) (putting it on the internet) · [ADMIN_GUIDE.md](ADMIN_GUIDE.md) (running the symposium).
