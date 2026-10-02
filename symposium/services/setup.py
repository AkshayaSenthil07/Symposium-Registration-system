"""Creates the database from database/schema.sql and loads sample data."""
import datetime as dt
import random

import mysql.connector

from symposium import config
from symposium.security import hash_password

DEMO_ADMIN = ("Symposium Admin", "admin@symposium.edu", "Admin@123")
DEMO_STUDENT = ("Demo Student", "student@symposium.edu", "Student@123")


def split_sql_script(script: str) -> list[str]:
    """Split a .sql file into statements, honouring DELIMITER changes."""
    statements, buf, delim = [], [], ";"
    for line in script.splitlines():
        stripped = line.strip()
        if not buf and (not stripped or stripped.startswith("--")):
            continue
        if stripped.upper().startswith("DELIMITER "):
            delim = stripped.split()[1]
            continue
        buf.append(line)
        if stripped.endswith(delim):
            stmt = "\n".join(buf).rstrip()
            stmt = stmt[: -len(delim)].strip()
            if stmt:
                statements.append(stmt)
            buf = []
    if "".join(buf).strip():
        statements.append("\n".join(buf).strip())
    return statements


def initialize(params: dict, with_sample: bool = True, log=print) -> None:
    db_name = params["database"]
    server_params = {k: v for k, v in params.items() if k != "database"}
    conn = mysql.connector.connect(**server_params)
    cur = conn.cursor()
    try:
        with open(config.SCHEMA_PATH, encoding="utf-8") as f:
            statements = split_sql_script(f.read())
        log(f"Creating database '{db_name}' ...")
        for stmt in statements:
            head = stmt.upper().split(None, 2)
            # the script targets `symposium_db`; honour the configured name instead
            if head[:2] == ["DROP", "DATABASE"]:
                stmt = f"DROP DATABASE IF EXISTS `{db_name}`"
            elif head[:2] == ["CREATE", "DATABASE"]:
                stmt = (f"CREATE DATABASE `{db_name}` CHARACTER SET utf8mb4 "
                        f"COLLATE utf8mb4_0900_ai_ci")
            elif head[0] == "USE":
                stmt = f"USE `{db_name}`"
            cur.execute(stmt)
        conn.commit()
        log(f"Executed {len(statements)} schema statements.")

        _seed_core(cur)
        conn.commit()
        if with_sample:
            log("Loading sample data (participants, registrations, results) ...")
            _seed_sample(conn, cur)
            conn.commit()
        log("Database ready.")
    finally:
        cur.close()
        conn.close()


# ---------------------------------------------------------------------------
# seed data
# ---------------------------------------------------------------------------
COLLEGES = [
    ("Government College of Technology", "Coimbatore"),
    ("Anna University - CEG", "Chennai"),
    ("PSG College of Technology", "Coimbatore"),
    ("Kumaraguru College of Technology", "Coimbatore"),
    ("Thiagarajar College of Engineering", "Madurai"),
    ("SSN College of Engineering", "Chennai"),
    ("Kongu Engineering College", "Erode"),
    ("Sri Krishna College of Engineering", "Coimbatore"),
]
DEPARTMENTS = [
    "Computer Science and Engineering", "Information Technology",
    "Electronics and Communication Engineering", "Electrical and Electronics Engineering",
    "Mechanical Engineering", "Civil Engineering",
    "Artificial Intelligence and Data Science", "Computer Science and Business Systems",
]
CATEGORIES = ["Technical", "Non-Technical", "Workshop", "Online"]
VENUES = [
    ("Main Auditorium", "Admin Block, Ground Floor", 500),
    ("Seminar Hall 1", "CSE Block, 1st Floor", 120),
    ("Seminar Hall 2", "IT Block, 2nd Floor", 100),
    ("Programming Lab 3", "CSE Block, 3rd Floor", 60),
    ("Open Air Theatre", "Central Lawn", 300),
]
SETTINGS = {
    "symposium_name": "TECHNOVA 2026",
    "tagline": "National Level Technical Symposium",
    "host_institution": "Department of Computer Science and Engineering",
    "contact_email": "technova@symposium.edu",
    "contact_phone": "9876543210",
}

FIRST = ["Aarav", "Diya", "Karthik", "Priya", "Arjun", "Sneha", "Vikram", "Meera", "Rahul",
         "Kavya", "Surya", "Ananya", "Harish", "Divya", "Naveen", "Lakshmi", "Pranav", "Nithya",
         "Gokul", "Swetha", "Ashwin", "Keerthana", "Manoj", "Deepika", "Sanjay", "Pooja",
         "Vignesh", "Janani", "Ajay", "Harini", "Rohit", "Shruthi", "Dinesh", "Abinaya",
         "Kishore", "Varsha", "Balaji", "Revathi"]
LAST = ["Kumar", "Raman", "Subramanian", "Krishnan", "Iyer", "Sundar", "Rajan", "Murugan",
        "Venkatesh", "Natarajan", "Balan", "Srinivasan", "Prakash", "Ganesh"]


def _events(today: dt.date):
    d0, d1, d2, d3 = (today + dt.timedelta(days=n) for n in (9, 10, 11, 12))
    # name, category, venue, date, start, end, fee, max, coordinator, description
    return [
        ("AI & ML Hands-on Workshop", "Workshop", "Main Auditorium", d0, "09:30", "16:30", 300, 120,
         "Dr. S. Anitha", "Full-day workshop on building ML models with Python and scikit-learn."),
        ("Paper Presentation", "Technical", "Seminar Hall 1", d1, "09:30", "12:30", 150, 60,
         "Ms. R. Kavitha", "Present your research paper before an expert panel. Teams of up to 2."),
        ("Tech Quiz", "Technical", "Seminar Hall 2", d1, "10:00", "11:30", 50, 80,
         "Mr. K. Arun", "Three rounds of rapid-fire questions on computing, science and technology."),
        ("Code Sprint", "Technical", "Programming Lab 3", d1, "13:30", "17:00", 200, 50,
         "Mr. P. Suresh", "Competitive programming contest - solve algorithmic problems against the clock."),
        ("Connexions", "Non-Technical", "Seminar Hall 2", d1, "14:00", "15:30", 50, 60,
         "Ms. M. Divya", "Connect the pictures and guess the tech term. Teams of 2."),
        ("Project Expo", "Technical", "Open Air Theatre", d2, "09:30", "13:00", 250, 80,
         "Dr. V. Ramesh", "Showcase working hardware or software projects to industry judges."),
        ("Bug Hunt", "Technical", "Programming Lab 3", d2, "14:00", "16:00", 100, 40,
         "Mr. S. Vignesh", "Find and fix as many bugs as possible in C / Python / Java programs."),
        ("Treasure Hunt", "Non-Technical", "Open Air Theatre", d2, "14:00", "17:00", 50, 100,
         "Mr. R. Manoj", "Campus-wide hunt with tech-themed clues. Teams of up to 4."),
        ("Web Design Challenge", "Technical", "Seminar Hall 1", d2, "10:00", "12:00", 100, 40,
         "Ms. J. Priya", "Design a responsive landing page from a given brief in two hours."),
        ("Photography Contest", "Online", None, d3, "09:00", "18:00", 0, 200,
         "Mr. A. Kishore", "Theme: 'Technology in everyday life'. Submit online - free entry!"),
    ]


def _seed_core(cur) -> None:
    cur.executemany("INSERT INTO college (college_name, city) VALUES (%s, %s)", COLLEGES)
    cur.executemany("INSERT INTO department (dept_name) VALUES (%s)", [(d,) for d in DEPARTMENTS])
    cur.executemany("INSERT INTO event_category (category_name) VALUES (%s)", [(c,) for c in CATEGORIES])
    cur.executemany("INSERT INTO venue (venue_name, location, capacity) VALUES (%s, %s, %s)", VENUES)
    cur.executemany("INSERT INTO app_setting VALUES (%s, %s)", list(SETTINGS.items()))
    name, email, pwd = DEMO_ADMIN
    cur.execute("INSERT INTO app_user (full_name, email, phone, password_hash, role) "
                "VALUES (%s, %s, %s, %s, 'ADMIN')", (name, email, "9876543210", hash_password(pwd)))


def _lookup(cur, sql):
    cur.execute(sql)
    return {row[1]: row[0] for row in cur.fetchall()}


def _seed_sample(conn, cur) -> None:
    rng = random.Random(2026)
    today = dt.date.today()
    cats = _lookup(cur, "SELECT category_id, category_name FROM event_category")
    venues = _lookup(cur, "SELECT venue_id, venue_name FROM venue")
    college_ids = list(_lookup(cur, "SELECT college_id, college_name FROM college").values())
    dept_ids = list(_lookup(cur, "SELECT dept_id, dept_name FROM department").values())

    event_ids = []
    for (name, cat, venue, date, start, end, fee, cap, coord, desc) in _events(today):
        cur.execute(
            "INSERT INTO event (event_name, category_id, description, venue_id, event_date, "
            "start_time, end_time, registration_fee, max_participants, coordinator_name, "
            "coordinator_phone) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
            (name, cats[cat], desc, venues.get(venue), date, start, end, fee, cap, coord,
             f"9{rng.randint(100000000, 999999999)}"))
        event_ids.append(cur.lastrowid)

    # participants -------------------------------------------------------
    student_hash = hash_password(DEMO_STUDENT[2])
    users = []
    cur.execute("INSERT INTO app_user (full_name, email, phone, password_hash) VALUES (%s,%s,%s,%s)",
                (DEMO_STUDENT[0], DEMO_STUDENT[1], "9000000001", student_hash))
    demo_id = cur.lastrowid
    cur.execute("INSERT INTO participant_profile VALUES (%s,%s,%s,%s,%s)",
                (demo_id, college_ids[0], dept_ids[0], 3, "Other"))
    used = set()
    for i in range(45):
        while True:
            first, last = rng.choice(FIRST), rng.choice(LAST)
            if (first, last) not in used:
                used.add((first, last))
                break
        email = f"{first}.{last}{rng.randint(1, 99)}@student.edu".lower()
        cur.execute("INSERT INTO app_user (full_name, email, phone, password_hash, created_at) "
                    "VALUES (%s,%s,%s,%s, NOW() - INTERVAL %s DAY)",
                    (f"{first} {last}", email, f"9{rng.randint(100000000, 999999999)}",
                     student_hash, rng.randint(1, 20)))
        uid = cur.lastrowid
        cur.execute("INSERT INTO participant_profile VALUES (%s,%s,%s,%s,%s)",
                    (uid, rng.choice(college_ids), rng.choice(dept_ids), rng.randint(1, 4),
                     rng.choice(["Male", "Female"])))
        users.append(uid)
    conn.commit()

    # completed pre-symposium event with attendance + results -------------
    cur.execute(
        "INSERT INTO event (event_name, category_id, description, venue_id, event_date, start_time, "
        "end_time, registration_fee, max_participants, coordinator_name, status) VALUES "
        "(%s,%s,%s,NULL,%s,'18:00','20:00',0,100,'Mr. A. Kishore','OPEN')",
        ("Pre-Symposium Online Coding Contest", cats["Online"],
         "Warm-up online contest held a week before the symposium.", today - dt.timedelta(days=7)))
    past_event = cur.lastrowid
    past_regs = []
    for uid in [demo_id] + rng.sample(users, 14):
        cur.execute("INSERT INTO registration (user_id, event_id, status, attended, registered_at) "
                    "VALUES (%s,%s,'PENDING',%s, NOW() - INTERVAL %s DAY)",
                    (uid, past_event, rng.random() < 0.85 or uid == demo_id, rng.randint(8, 15)))
        rid = cur.lastrowid
        cur.execute("INSERT INTO payment (reg_id, amount, method, transaction_ref, status) "
                    "VALUES (%s, 0, 'FREE', %s, 'SUCCESS')", (rid, f"TXNPRE{rid:06d}"))
        past_regs.append((rid, uid))
    cur.execute("SELECT reg_id FROM registration WHERE event_id=%s AND attended ORDER BY reg_id",
                (past_event,))
    attended = [r[0] for r in cur.fetchall()]
    podium = [attended[3], attended[0], attended[5]]       # demo student finishes 2nd
    for pos, rid in enumerate(podium, start=1):
        cur.execute("INSERT INTO event_result VALUES (%s,%s,%s)", (past_event, pos, rid))
    cur.execute("UPDATE event SET status='COMPLETED' WHERE event_id=%s", (past_event,))
    conn.commit()

    # registrations through the stored procedure (exercises all rules) ----
    methods = ["UPI"] * 5 + ["CARD"] * 2 + ["NET_BANKING"] + ["CASH"] * 2
    for uid in [demo_id] + users:
        picks = rng.sample(event_ids, rng.randint(1, 4)) if uid != demo_id else event_ids[1:3]
        for eid in picks:
            try:
                team = rng.choice([None, None, f"Team {rng.choice(LAST)}"])
                cur.callproc("sp_register_participant", (uid, eid, team, rng.choice(methods), 0))
            except mysql.connector.Error:
                conn.rollback()        # clash / full - just skip, like a real user would
    conn.commit()

    # spread registration timestamps over the last two weeks (for the trend chart)
    cur.execute("SELECT reg_id FROM registration WHERE event_id <> %s", (past_event,))
    for (rid,) in cur.fetchall():
        days = rng.choice([0, 1, 1, 2, 2, 3, 4, 5, 6, 7, 8, 10, 12, 13])
        cur.execute("UPDATE registration SET registered_at = NOW() - INTERVAL %s DAY "
                    "- INTERVAL %s MINUTE WHERE reg_id=%s", (days, rng.randint(0, 600), rid))
        cur.execute("UPDATE payment SET paid_at = (SELECT registered_at FROM registration "
                    "WHERE reg_id=%s) WHERE reg_id=%s", (rid, rid))

    # a few cancellations (refund flow)
    cur.execute("SELECT reg_id, user_id FROM registration WHERE status='CONFIRMED' "
                "AND event_id <> %s AND user_id <> %s ORDER BY RAND(7) LIMIT 4", (past_event, demo_id))
    for rid, uid in cur.fetchall():
        cur.callproc("sp_cancel_registration", (rid, uid))
    conn.commit()
