"""Demo data (for presentations) and the "Go live" clean-up.

Every demo row is flagged is_demo (users, events, news, coupons), so going live removes exactly the
sample data and keeps real configuration (venues, categories, departments, settings, real staff).
"""
import datetime as dt
import os
import random

from webapp import config, db
from webapp.security import hash_password
from webapp.services import audit, registrations, settings
from webapp.util import now, today

DEMO_PASSWORD = "Demo@1234"
DEMO_DOMAIN = "demo.symposium"

COLLEGES = [("Government College of Technology", "Coimbatore"), ("Anna University - CEG", "Chennai"),
            ("PSG College of Technology", "Coimbatore"), ("Kumaraguru College of Technology", "Coimbatore"),
            ("Thiagarajar College of Engineering", "Madurai"), ("SSN College of Engineering", "Chennai"),
            ("Kongu Engineering College", "Erode"), ("Sri Krishna College of Engineering", "Coimbatore")]
VENUES = [("Main Auditorium", "Admin Block, Ground Floor", 500), ("Seminar Hall 1", "CSE Block, 1st Floor", 120),
          ("Seminar Hall 2", "IT Block, 2nd Floor", 100), ("Programming Lab 3", "CSE Block, 3rd Floor", 60),
          ("Open Air Theatre", "Central Lawn", 300)]
FIRST = ["Aarav", "Diya", "Karthik", "Priya", "Arjun", "Sneha", "Vikram", "Meera", "Rahul", "Kavya", "Surya",
         "Ananya", "Harish", "Divya", "Naveen", "Lakshmi", "Pranav", "Nithya", "Gokul", "Swetha", "Ashwin",
         "Keerthana", "Manoj", "Deepika", "Sanjay", "Pooja", "Vignesh", "Janani", "Ajay", "Harini", "Rohit",
         "Shruthi", "Dinesh", "Abinaya", "Varsha", "Balaji", "Revathi", "Tharun"]
LAST = ["Kumar", "Raman", "Subramanian", "Krishnan", "Iyer", "Sundar", "Rajan", "Murugan", "Venkatesh",
        "Natarajan", "Balan", "Srinivasan", "Prakash", "Ganesh"]


def _events(d0):
    d1, d2, d3 = d0 + dt.timedelta(days=1), d0 + dt.timedelta(days=2), d0 + dt.timedelta(days=3)
    # name, category, venue, date, start, end, fee, early, cap, tmin, tmax, coordinator, description
    return [
        ("AI & ML Hands-on Workshop", "Workshop", "Main Auditorium", d0, "09:30", "16:30", 300, 250, 120, 1, 1,
         "Dr. S. Anitha", "Full-day workshop on building machine-learning models with Python and scikit-learn."),
        ("Paper Presentation", "Technical", "Seminar Hall 1", d1, "09:30", "12:30", 200, 150, 60, 1, 2,
         "Ms. R. Kavitha", "Present your research paper before an expert panel. Teams of up to 2."),
        ("Tech Quiz", "Technical", "Seminar Hall 2", d1, "10:00", "11:30", 100, None, 80, 2, 2,
         "Mr. K. Arun", "Three rounds of rapid-fire questions on computing and technology. Teams of 2."),
        ("Code Sprint", "Technical", "Programming Lab 3", d1, "13:30", "17:00", 150, None, 50, 1, 1,
         "Mr. P. Suresh", "Competitive programming - solve algorithmic problems against the clock."),
        ("Connexions", "Non-Technical", "Seminar Hall 2", d1, "14:00", "15:30", 50, None, 60, 1, 2,
         "Ms. M. Divya", "Connect the pictures and guess the tech term."),
        ("Project Expo", "Technical", "Open Air Theatre", d2, "09:30", "13:00", 250, 200, 80, 1, 4,
         "Dr. V. Ramesh", "Showcase working hardware or software projects to industry judges. Teams up to 4."),
        ("Bug Hunt", "Technical", "Programming Lab 3", d2, "14:00", "16:00", 100, None, 40, 1, 1,
         "Mr. S. Vignesh", "Find and fix bugs in C, Python and Java programs."),
        ("Treasure Hunt", "Non-Technical", "Open Air Theatre", d2, "14:00", "17:00", 200, None, 30, 3, 4,
         "Mr. R. Manoj", "Campus-wide hunt with tech-themed clues. Teams of 3 to 4."),
        ("Web Design Challenge", "Technical", "Seminar Hall 1", d2, "10:00", "12:00", 100, None, 40, 1, 1,
         "Ms. J. Priya", "Design a responsive landing page from a brief in two hours."),
        ("Photography Contest", "Online", None, d3, "09:00", "18:00", 0, None, 200, 1, 1,
         "Mr. A. Kishore", "Theme: Technology in everyday life. Submit online - free entry!"),
    ]


def has_live_data() -> bool:
    return bool(db.get().value("SELECT COUNT(*) FROM app_user WHERE role = 'PARTICIPANT' AND NOT is_demo"))


def load_demo(actor_id) -> str:
    if has_live_data():
        raise db.DatabaseError("Real participants exist. Demo data can only be loaded on a site that is not live.")
    if db.get().value("SELECT COUNT(*) FROM event WHERE is_demo"):
        raise db.DatabaseError("Demo data is already loaded. Use 'Go live' to remove it first.")
    rng = random.Random(2026)
    pw = hash_password(DEMO_PASSWORD)
    t = now()
    d0 = today() + dt.timedelta(days=12)
    with db.get().transaction() as cur:
        cur.executemany("INSERT IGNORE INTO college (college_name, city) VALUES (%s, %s)", COLLEGES)
        cur.executemany("INSERT IGNORE INTO venue (venue_name, location, capacity) VALUES (%s, %s, %s)", VENUES)
        cur.execute("SELECT category_id, category_name FROM event_category")
        cats = {r["category_name"]: r["category_id"] for r in cur.fetchall()}
        for c in ("Technical", "Non-Technical", "Workshop", "Online"):
            if c not in cats:
                cur.execute("INSERT INTO event_category (category_name) VALUES (%s)", (c,))
                cats[c] = cur.lastrowid
        cur.execute("SELECT venue_id, venue_name FROM venue")
        venues = {r["venue_name"]: r["venue_id"] for r in cur.fetchall()}
        cur.execute("SELECT college_id FROM college")
        college_ids = [r["college_id"] for r in cur.fetchall()]
        cur.execute("SELECT dept_id FROM department")
        dept_ids = [r["dept_id"] for r in cur.fetchall()]

        event_ids = []
        for (name, cat, venue, date, start, end, fee, early, cap, tmin, tmax, coord, desc) in _events(d0):
            cur.execute("INSERT INTO event (event_name, category_id, description, rules, prizes, venue_id, event_date, "
                        "start_time, end_time, registration_fee, early_bird_fee, early_bird_until, registration_deadline, "
                        "max_participants, team_min, team_max, coordinator_name, coordinator_phone, is_demo) "
                        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,TRUE)",
                        (name, cats[cat], desc, "1. Bring your college ID card.\n2. Report 15 minutes early.\n"
                         "3. Judges' decision is final.", "1st Rs.3000 · 2nd Rs.2000 · 3rd Rs.1000",
                         venues.get(venue), date, start, end, fee, early, t + dt.timedelta(days=5) if early else None,
                         dt.datetime.combine(date, dt.time(8, 0)) - dt.timedelta(days=1), cap, tmin, tmax, coord,
                         f"9{rng.randint(100000000, 999999999)}"))
            event_ids.append(cur.lastrowid)
        # a completed warm-up event with results
        cur.execute("INSERT INTO event (event_name, category_id, description, event_date, start_time, end_time, "
                    "registration_fee, max_participants, coordinator_name, status, is_demo) "
                    "VALUES ('Pre-Symposium Coding Contest', %s, 'Online warm-up contest held before the symposium.', "
                    "%s, '18:00', '20:00', 0, 100, 'Mr. A. Kishore', 'OPEN', TRUE)", (cats["Online"], today() - dt.timedelta(days=6)))
        past_event = cur.lastrowid

        staff = {}
        for role, email, name in (("ADMIN", "admin", "Demo Admin"), ("CASHIER", "cashier", "Demo Cashier"),
                                  ("COORDINATOR", "coordinator", "Demo Coordinator")):
            cur.execute("INSERT INTO app_user (full_name, email, phone, password_hash, role, email_verified, is_demo) "
                        "VALUES (%s, %s, %s, %s, %s, TRUE, TRUE)", (name, f"{email}@{DEMO_DOMAIN}",
                                                                    f"98765432{len(staff)}0", pw, role))
            staff[role] = cur.lastrowid
        for eid in (event_ids[1], event_ids[3], past_event):
            cur.execute("INSERT INTO event_staff (event_id, user_id) VALUES (%s, %s)", (eid, staff["COORDINATOR"]))

        people = []
        cur.execute("INSERT INTO app_user (full_name, email, phone, password_hash, email_verified, is_demo) "
                    "VALUES ('Demo Student', %s, '9000000001', %s, TRUE, TRUE)", (f"student@{DEMO_DOMAIN}", pw))
        demo_student = cur.lastrowid
        cur.execute("INSERT INTO participant_profile VALUES (%s, %s, %s, 3, 'Other')", (demo_student, college_ids[0], dept_ids[0]))
        used = set()
        for i in range(42):
            while True:
                f, l = rng.choice(FIRST), rng.choice(LAST)
                if (f, l) not in used:
                    used.add((f, l))
                    break
            cur.execute("INSERT INTO app_user (full_name, email, phone, password_hash, email_verified, is_demo, created_at) "
                        "VALUES (%s, %s, %s, %s, TRUE, TRUE, NOW() - INTERVAL %s DAY)",
                        (f"{f} {l}", f"{f}.{l}{i}@{DEMO_DOMAIN}".lower(), f"9{rng.randint(100000000, 999999999)}",
                         pw, rng.randint(1, 20)))
            uid = cur.lastrowid
            cur.execute("INSERT INTO participant_profile VALUES (%s, %s, %s, %s, %s)",
                        (uid, rng.choice(college_ids), rng.choice(dept_ids), rng.randint(1, 4), rng.choice(["Male", "Female"])))
            people.append(uid)

        cur.executemany("INSERT INTO coupon (code, discount_type, discount_value, event_id, max_uses, valid_until, is_demo) "
                        "VALUES (%s, %s, %s, %s, %s, %s, TRUE)",
                        [("EARLY20", "PERCENT", 20, None, 100, t + dt.timedelta(days=10)),
                         ("CITFAM", "FLAT", 50, None, None, None),
                         ("EXPO100", "FLAT", 100, event_ids[5], 20, None)])
        news = [("Registrations are open! Early-bird prices end in 5 days.", "IMPORTANT", "/events"),
                ("Paper Presentation: abstract submission closes one day before the event.", "INFO", None),
                ("Free Photography Contest - submit your best shot online.", "INFO", "/events"),
                ("Spot registrations available at the registration desk near the main gate.", "INFO", None)]
        for msg, pri, link in news:
            cur.execute("INSERT INTO news_item (message, priority, link_url, starts_at, is_demo, created_by) "
                        "VALUES (%s, %s, %s, NOW() - INTERVAL 1 HOUR, TRUE, %s)", (msg, pri, link, staff["ADMIN"]))

        # past event: registrations, attendance, scores, published results
        past_regs = []
        for uid in [demo_student] + rng.sample(people, 14):
            cur.execute("INSERT INTO registration (user_id, event_id, status, fee_amount, ticket_code, attended, "
                        "checked_in_at, registered_at) VALUES (%s, %s, 'PENDING', 0, %s, TRUE, %s, NOW() - INTERVAL 9 DAY)",
                        (uid, past_event, _code(rng), dt.datetime.combine(today() - dt.timedelta(days=6), dt.time(18, 5))))
            rid = cur.lastrowid
            cur.execute("INSERT INTO payment (reg_id, amount, method, status, paid_at) VALUES (%s, 0, 'FREE', 'SUCCESS', NOW())", (rid,))
            past_regs.append(rid)
        for rid in past_regs:
            cur.execute("INSERT INTO judge_score (reg_id, judge_id, score) VALUES (%s, %s, %s)",
                        (rid, staff["COORDINATOR"], rng.randint(45, 98)))
            if rng.random() < 0.6:
                cur.execute("INSERT INTO feedback (reg_id, rating, comments) VALUES (%s, %s, %s)",
                            (rid, rng.choice([4, 5, 5, 3, 4]), rng.choice([None, "Well organised!", "Loved the problems.",
                                                                           "Could use more time."])))
        cur.execute("SELECT reg_id FROM judge_score WHERE reg_id IN (" + ",".join(["%s"] * len(past_regs)) + ") "
                    "ORDER BY score DESC LIMIT 3", tuple(past_regs))
        podium = [r["reg_id"] for r in cur.fetchall()]
        podium[1] = past_regs[0]                      # the demo student wins 2nd place
        if podium[0] == past_regs[0]:
            podium[0] = past_regs[1]
        for pos, rid in enumerate(podium, 1):
            cur.execute("INSERT INTO event_result VALUES (%s, %s, %s)", (past_event, pos, rid))
        cur.execute("UPDATE event SET status = 'COMPLETED', results_published = TRUE WHERE event_id = %s", (past_event,))
    settings.save({"data_mode": "demo", "upi_id": settings.get("upi_id") or "technova.demo@okaxis",
                   "upi_payee_name": settings.get("upi_payee_name") or "CIT CSE Association",
                   "symposium_dates": settings.get("symposium_dates") or
                   f"{d0.strftime('%d')}-{(d0 + dt.timedelta(days=3)).strftime('%d %B %Y')}",
                   "venue_address": settings.get("venue_address") or "Coimbatore Institute of Technology, Coimbatore - 641014",
                   "contact_phone": settings.get("contact_phone") or "9876543210"})

    # live registrations through the real service (exercises every rule)
    methods = ["UPI_QR"] * 4 + ["GATEWAY"] * 3 + ["CASH"] * 2
    bank_lines, utr_seq = [], 412600000000
    for uid in [demo_student] + people:
        picks = [event_ids[1], event_ids[5]] if uid == demo_student else rng.sample(event_ids, rng.randint(1, 3))
        for eid in picks:
            e = db.get().one("SELECT team_min, team_max FROM event WHERE event_id = %s", (eid,))
            size = rng.randint(e["team_min"], e["team_max"])
            members = [{"name": f"{rng.choice(FIRST)} {rng.choice(LAST)}"} for _ in range(size - 1)]
            team = f"Team {rng.choice(LAST)}" if e["team_max"] > 1 else ""
            method = rng.choice(methods)
            try:
                res = registrations.register(uid, eid, team, members, rng.choice(["", "", "", "EARLY20"]), method,
                                             source="ONLINE" if rng.random() < .85 else "DESK",
                                             cash_collected_by=staff["CASHIER"] if method == "CASH" and rng.random() < .6 else None)
            except registrations.RegistrationError:
                continue
            if res["status"] != "PENDING":
                continue
            p = registrations.open_payment(res["reg_id"])
            roll = rng.random()
            if method == "UPI_QR":
                utr_seq += rng.randint(3, 999)
                registrations.submit_utr(res["reg_id"], uid, str(utr_seq))
                if roll < .55:                              # already verified by the cashier
                    db.get().run("UPDATE payment SET status = 'SUCCESS', paid_at = NOW(), collected_by = %s, "
                                 "note = 'Matched with bank statement' WHERE payment_id = %s", (staff["CASHIER"], p["payment_id"]))
                elif roll < .85:                            # in the sample bank statement, not yet reconciled
                    bank_lines.append((str(utr_seq), p["amount"]))
            elif method == "GATEWAY" and roll < .8:
                db.get().run("UPDATE payment SET status = 'SUCCESS', paid_at = NOW(), gateway_order_id = %s, "
                             "gateway_payment_id = %s, note = 'Paid online (demo)' WHERE payment_id = %s",
                             (f"order_DEMO{p['payment_id']:08d}", f"pay_DEMO{p['payment_id']:08d}", p["payment_id"]))
    # spread registration dates over two weeks for the trend chart
    db.get().run("UPDATE registration SET registered_at = NOW() - INTERVAL FLOOR(RAND(7) * 13) DAY "
                 "- INTERVAL FLOOR(RAND(3) * 600) MINUTE WHERE event_id IN (" + ",".join(["%s"] * len(event_ids)) + ")",
                 tuple(event_ids))
    # keep unpaid demo seats on hold for a week so the demo does not "decay" after an hour
    db.get().run("UPDATE registration SET hold_expires_at = NOW() + INTERVAL 7 DAY "
                 "WHERE status = 'PENDING' AND hold_expires_at IS NOT NULL")
    _write_bank_statement(bank_lines, rng)
    audit.log(actor_id, "DEMO_LOADED", f"{len(people) + 1} participants, {len(event_ids) + 1} events")
    return f"Demo data loaded: {len(people) + 1} participants, {len(event_ids) + 1} events. Password for every demo account: {DEMO_PASSWORD}"


def _code(rng):
    from webapp.security import TICKET_ALPHABET
    return "".join(rng.choice(TICKET_ALPHABET) for _ in range(12))


def _write_bank_statement(lines, rng):
    """A sample statement in a typical Indian bank CSV layout, to demo reconciliation."""
    os.makedirs(config.UPLOAD_DIR, exist_ok=True)
    path = os.path.join(config.UPLOAD_DIR, "sample_bank_statement.csv")
    out = ["Account Statement - CIT CSE Association (sample)", "Account No: XXXXXXXX4521", "",
           "Txn Date,Value Date,Description,Ref No./Cheque No.,Debit,Credit,Balance"]
    bal = 50000
    for utr, amt in lines + [("412699999999", 500)]:          # one extra credit that matches nothing
        bal += float(amt)
        d = (today() - dt.timedelta(days=rng.randint(0, 3))).strftime("%d/%m/%Y")
        payer = f"{rng.choice(FIRST).upper()}{rng.choice(LAST).upper()[:4]}@okicici"
        out.append(f"{d},{d},UPI/{utr}/{payer}/Symposium fee,{utr},,{float(amt):.2f},{bal:.2f}")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out) + "\n")
    return path


def go_live(actor_id) -> str:
    admins = db.get().value("SELECT COUNT(*) FROM app_user WHERE role = 'ADMIN' AND is_active AND NOT is_demo")
    if not admins:
        raise db.DatabaseError("Create at least one real administrator account (Admin > Staff accounts) before "
                               "going live - the demo admin account will be deleted.")
    with db.get().transaction() as cur:
        cur.execute("SET @restoring = 1")                  # no audit spam from triggers while clearing
        for sql in ("DELETE FROM registration", "DELETE FROM bank_txn", "DELETE FROM email_outbox",
                    "DELETE FROM user_token WHERE user_id IN (SELECT user_id FROM app_user WHERE is_demo OR role = 'PARTICIPANT')",
                    "DELETE FROM news_item WHERE is_demo", "DELETE FROM coupon WHERE is_demo",
                    "DELETE FROM event WHERE is_demo",
                    "DELETE FROM app_user WHERE is_demo OR role = 'PARTICIPANT'",
                    "DELETE FROM college WHERE college_id NOT IN (SELECT college_id FROM participant_profile)"):
            cur.execute(sql)
        cur.execute("UPDATE coupon SET used_count = 0")
        cur.execute("SET @restoring = NULL")
    settings.save({"data_mode": "live"})
    audit.log(actor_id, "GO_LIVE", "All demo data and participants removed")
    return "The site is now live: all demo data and participant records were removed."
