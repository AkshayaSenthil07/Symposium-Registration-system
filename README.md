# Symposium Management System

A desktop application for running a college technical symposium: participants sign up, browse
events, register and pay, and download receipts and certificates. Organisers manage events, verify
payments, mark attendance, announce winners and see live analytics.

| Layer | Technology |
|---|---|
| Frontend | Python GUI - **CustomTkinter** (modern Tkinter), matplotlib charts |
| Backend | **MySQL 8.0** |
| Connectivity | **mysql-connector-python** (connection pool, parameterised queries) |
| Documents | fpdf2 (PDF receipts, certificates, attendance sheets) |

---

## Features

### Login & security
- Single login screen for both roles. The role comes from the database, not a tab the user picks.
- Passwords stored as **PBKDF2-SHA256 hashes with a per-user salt** (never plain text).
- **Account lock-out** for 5 minutes after 5 wrong passwords.
- Self-service participant sign-up with validation and a password-strength meter.
- Change password, admin password reset (temporary password), enable/disable accounts.
- All SQL is parameterised (`%s` placeholders), which prevents SQL injection.

### Participant portal
- **Explore Events**: event cards with category filter, search, live seats-left bar and coordinator details.
- **Register & pay** (demo gateway): UPI, card, net banking, or *pay at desk*. Registration is a
  single atomic stored-procedure call.
- **Time-clash detection**: you can't book two events that overlap.
- **My Registrations**: download the PDF receipt, cancel (refund is automatic), and download a
  participation or merit certificate once your attendance is marked.
- **Results & Leaderboard**: winners of each event and the college championship table.
- **Profile**: edit your details and change your password.

### Admin console
- **Dashboard**: KPI cards, registrations-by-event bar chart, revenue donut, 14-day trend line and upcoming events.
- **Events**: create, edit, open/close, complete, cancel and delete events, with a calendar date picker and validation.
- **Registrations**: filter and search, bulk **attendance marking**, cash-payment verification,
  cancel & refund, **attendance sheet PDF** with a signature column, CSV export.
- **Participants**: search, view a participant's registrations, reset their password, enable or disable their account.
- **Results & Prizes**: award 1st/2nd/3rd place and generate all certificates in one click.
- **Reports**: 9 analytical reports (joins, GROUP BY/HAVING, sub-queries), each exportable to CSV or PDF.
- **SQL Console**: run ad-hoc SELECT / SHOW / EXPLAIN queries inside a READ ONLY transaction (useful for the viva).
- **Master Data**: venues, categories, colleges, departments.
- **Audit Log**: every login, registration, payment and status change. Many entries are written by triggers.
- **Settings**: symposium name and branding, admin accounts, database info.
- Light / dark theme toggle.

---

## Database design

**12 tables (3NF)**: `college`, `department`, `venue`, `event_category`, `app_setting`, `app_user`,
`participant_profile`, `event`, `registration`, `payment`, `event_result`, `audit_log`

```
college ─┐                      event_category ─┐   venue ─┐
department ─┤                                   │          │
            ▼                                   ▼          ▼
app_user 1──1 participant_profile        event (category_id, venue_id)
    │ 1                                      │ 1
    │                                        │
    └──────────< registration >──────────────┘      (UNIQUE user_id + event_id)
                    │ 1          │ 1
                    ▼            ▼
                 payment      event_result (PK event_id + position)
app_user 1──< audit_log
```

| DBMS concept | Where |
|---|---|
| PK / composite PK | every table; `event_result(event_id, position)` |
| Foreign keys with CASCADE / RESTRICT / SET NULL | `registration→event` cascade, `profile→college` restrict, `event→venue` set null |
| UNIQUE | e-mail, event name, `(user_id, event_id)` stops double registration |
| CHECK | capacity > 0, fee ≥ 0, end_time > start_time, phone regex, e-mail pattern, year 1-5, position 1-3 |
| Indexes | `event(event_date)`, `event(status)`, `registration(event_id, status)`, … |
| Views (5) | `v_event_summary`, `v_registration_details`, `v_participant_details`, `v_college_leaderboard`, `v_latest_payment` |
| Stored function | `fn_seats_left(event_id)` |
| Stored procedures + TRANSACTIONS | `sp_register_participant` (row locking with `SELECT … FOR UPDATE`, capacity, clash, payment), `sp_cancel_registration` |
| Triggers (7) | lower-case e-mails, block full/closed events, payment → confirm registration, refund → cancel, audit trail, event deletion log |
| Error handling | `SIGNAL SQLSTATE '45000'` messages shown directly in the GUI |

See [`database/schema.sql`](database/schema.sql) and the viva-ready
[`database/sample_queries.sql`](database/sample_queries.sql).

---

## Setup

1. **Install MySQL 8.0** and make sure the server is running.
2. **Install Python packages** (Python 3.10+):
   ```bash
   pip install -r requirements.txt
   ```
3. **Run the app**:
   ```bash
   python main.py
   ```
   On first launch a **Database Setup** screen asks for your MySQL username and password. Click
   **Initialise Database** to create everything and load sample data. Your settings are saved to
   `config.ini`, which is git-ignored so your password is never committed.

   *Alternative:* copy `config.example.ini` to `config.ini`, fill in your password, and run
   `python setup_database.py` (use `--empty` for no sample data).

### Demo accounts (sample data)
| Role | E-mail | Password |
|---|---|---|
| Admin | `admin@symposium.edu` | `Admin@123` |
| Participant | `student@symposium.edu` | `Student@123` |

All other sample participants also use `Student@123`.

---

## Project structure

```
main.py                     entry point
setup_database.py           CLI database initialiser
config.example.ini          template for config.ini
database/
  schema.sql                tables, indexes, views, function, procedures, triggers
  sample_queries.sql        demo queries for the viva
symposium/
  config.py  db.py  security.py
  services/                 business logic (no GUI code)
    auth.py  catalog.py  registrations.py  reports.py  pdf.py  setup.py
  ui/                       CustomTkinter screens
    app.py  shell.py  widgets.py  theme.py  charts.py
    setup_view.py  auth_views.py
    admin/pages.py          dashboard, events, registrations, ... settings
    participant/pages.py    explore, my registrations, leaderboard, profile
exports/                    generated PDFs / CSVs (git-ignored)
```

## Suggested demo flow
1. Log in as **admin**. Walk through the dashboard charts, then create an event with the calendar picker.
2. Sign out and **create a new participant account**. Register for two events. Try a third that overlaps in time and the database refuses it.
3. Pay one event "at desk", sign in as admin and **verify the cash payment**. The trigger confirms the registration.
4. Mark attendance, award a prize, then sign in as the participant and download the **merit certificate**.
5. Open **SQL Console**, show triggers and procedures, run `EXPLAIN`, and show the **Audit Log**.
