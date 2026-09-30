# Live website build - progress tracker

Branch: `live-version`. The desktop version (tag `v1-evaluation`) stays untouched.
Database: `symposium_live` (separate from the desktop version's `symposium_db`).

## Decisions (agreed with the team)
- Website for everyone (participants, admin, cashier, coordinator). Flask + MySQL + mysql-connector.
- Payments: UPI QR direct to the college account (free; UTR + bank-statement matching),
  Razorpay (optional; UPI + net banking, no cards), cash at desk. Mock gateway for the demo.
- QR tickets and QR check-in. No SMS. Students cannot cancel; only admin cancels / refunds.
- Flash news ticker on the home page; "Updated" tag on changed events.
- Also: waitlist, coupons, early-bird price, deadlines, team events, judges' scoring,
  feedback, e-mail (outbox in demo mode, SMTP in live mode), certificate verification.
- Reliability: backups (manual + scheduled), reconnect, logging, tests.
- Security: CSRF, secure sessions, headers/CSP, rate limits, hashed passwords,
  e-mail verification, limited MySQL users (no root), secrets only in instance/config.ini.
- Everything editable from Admin screens; "Load demo data" and "Go live" buttons.
- Never push to GitHub without permission.

## Stages
- [x] A. Skeleton: config, DB layer, schema, security basics, layout, public pages, news ticker, auth
- [x] B. Participant: event registration (team, coupon, early bird, waitlist), payments, QR ticket, receipt
- [x] C. Staff/admin core: dashboard, events (venue clash, change notices), registrations, desk walk-in,
        payment verification + bank CSV reconciliation, QR check-in, staff roles
- [x] D. Results & scoring, certificates + verify page, feedback, news admin, coupons admin, e-mail
- [x] E. Settings (branding, payments, e-mail), reports, SQL console, audit, backups, demo data / go live
- [ ] F. Tests (incl. concurrency), security review, responsive check, docs (README, DEPLOY, ADMIN GUIDE)

## Log
- 2026-09-30: Stage A done - schema (symposium_live + limited MySQL users), config, DB pool with reconnect, security (CSRF, headers/CSP, rate limits, PBKDF2, tokens), public pages + flash-news ticker, auth (signup/verify/login lockout/forgot/reset/change password). Smoke-tested.
- 2026-09-30: Stage B done - registration transaction (row lock, team size, coupons, early bird, clash, limits, waitlist), UPI QR + UTR submission, mock/Razorpay gateway with signature + amount verification + webhook, cash hold, QR ticket, PDF receipt/certificate, notifications, participant pages. Tested (ticket QR needs staff.checkin from stage C).
- 2026-09-30: WIP - staff + admin blueprints, reports, cashdesk (UTR verify, bank CSV reconcile), backups, demo/go-live services written. NEXT: staff/admin templates, then test stages C-E.
- 2026-09-30: Stages C, D, E done - staff/admin UI (dashboard + SVG charts, QR check-in with camera, desk walk-ins, payments verify/reject, bank CSV reconcile, cash report, registrations + CSV + attendance PDF, scoring/publish, events with venue clash + change announcements, news, participants, staff roles, coupons, lists, feedback, 10 reports, read-only SQL console, audit, outbox, settings incl. gateway/SMTP, backups + restore, demo data / go live). 85-page crawl for 4 roles: 0 failures; action tests all pass. NEXT: Stage F (pytest suite + concurrency, security review, responsive check, docs).
