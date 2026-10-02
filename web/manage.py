"""Command-line administration for the symposium website.

  python manage.py init-db            create the database, limited MySQL users and the first admin
  python manage.py create-admin       add another administrator
  python manage.py seed-demo          load the demo data set (same as Admin > Demo / go live)
  python manage.py go-live            remove all demo data (same as the admin button)
  python manage.py backup             write a backup file now
  python manage.py run                start the production server (waitress) on port 8000

init-db asks for the MySQL root password once. It is NOT stored anywhere; the website
connects with the limited 'symposium_app' user whose password is generated and saved
in instance/config.ini.
"""
import argparse
import getpass
import os
import re
import secrets
import sys

import mysql.connector

from webapp import config

DEFAULT_DEPARTMENTS = [
    "Computer Science and Engineering", "Information Technology", "Electronics and Communication Engineering",
    "Electrical and Electronics Engineering", "Mechanical Engineering", "Civil Engineering",
    "Artificial Intelligence and Data Science", "Computer Science and Business Systems",
    "Master of Computer Applications", "Other",
]
DEFAULT_CATEGORIES = ["Technical", "Non-Technical", "Workshop", "Online"]

RO_USER_COLUMNS = "user_id, full_name, email, phone, role, is_active, email_verified, last_login, created_at, is_demo"
RO_TABLES = ["college", "department", "venue", "event_category", "participant_profile", "event", "event_staff",
             "coupon", "registration", "team_member", "payment", "bank_txn", "judge_score", "event_result",
             "feedback", "news_item", "audit_log", "app_setting"]
RO_VIEWS = ["v_latest_payment", "v_event_summary", "v_registration_details", "v_participant_details",
            "v_college_leaderboard", "v_score_board"]


def split_sql(script: str) -> list[str]:
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
            stmt = "\n".join(buf).rstrip()[: -len(delim)].strip()
            if stmt:
                statements.append(stmt)
            buf = []
    if "".join(buf).strip():
        statements.append("\n".join(buf).strip())
    return statements


def ident(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_]{1,64}", name):
        sys.exit(f"Invalid name: {name!r} (letters, digits and _ only)")
    return name


def init_db(args):
    cfg = config.load()
    m = cfg["mysql"]
    dbname = ident(args.database or m["database"])
    root_pw = os.environ.get("MYSQL_ROOT_PASSWORD") or getpass.getpass(f"MySQL password for '{args.root_user}': ")
    root = mysql.connector.connect(host=m["host"], port=int(m["port"]), user=args.root_user, password=root_pw)
    cur = root.cursor()
    cur.execute("SHOW DATABASES LIKE %s", (dbname,))
    if cur.fetchone():
        if not args.force:
            ans = input(f"Database '{dbname}' exists. ERASE it and start again? Type YES: ")
            if ans != "YES":
                sys.exit("Aborted.")
        cur.execute(f"DROP DATABASE `{dbname}`")
    cur.execute(f"CREATE DATABASE `{dbname}` CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci")
    cur.execute(f"USE `{dbname}`")
    with open(config.SCHEMA_PATH, encoding="utf-8") as fh:
        statements = split_sql(fh.read())
    for stmt in statements:
        cur.execute(stmt)
    print(f"Created database '{dbname}' ({len(statements)} statements).")

    # limited MySQL users - the website never connects as root
    host = args.app_host
    app_user, ro_user = ident(m["user"]), ident(m["readonly_user"])
    app_pw, ro_pw = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    for user, pw in ((app_user, app_pw), (ro_user, ro_pw)):
        cur.execute(f"DROP USER IF EXISTS '{user}'@'{host}'")
        cur.execute(f"CREATE USER '{user}'@'{host}' IDENTIFIED BY %s", (pw,))
    cur.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE, EXECUTE ON `{dbname}`.* TO '{app_user}'@'{host}'")
    for t in RO_TABLES + RO_VIEWS:
        cur.execute(f"GRANT SELECT ON `{dbname}`.`{t}` TO '{ro_user}'@'{host}'")
    cur.execute(f"GRANT SELECT ({RO_USER_COLUMNS}) ON `{dbname}`.`app_user` TO '{ro_user}'@'{host}'")
    for fn in ("fn_seats_left", "fn_event_price"):
        cur.execute(f"GRANT EXECUTE ON FUNCTION `{dbname}`.`{fn}` TO '{ro_user}'@'{host}'")
    root.commit()
    print(f"Created MySQL users '{app_user}' (read/write) and '{ro_user}' (read-only console, no password hashes).")

    m["database"], m["password"], m["readonly_password"] = dbname, app_pw, ro_pw
    config.save(cfg)
    print(f"Saved connection details to {config.CONFIG_PATH}")

    seed_base(cur)
    root.commit()
    if not args.no_admin:
        create_admin(cur, args)
        root.commit()
    root.close()
    print("\nDone. Start the site with:  python manage.py run   (or python run_dev.py for development)")


def seed_base(cur):
    cur.executemany("INSERT IGNORE INTO department (dept_name) VALUES (%s)", [(d,) for d in DEFAULT_DEPARTMENTS])
    cur.executemany("INSERT IGNORE INTO event_category (category_name) VALUES (%s)", [(c,) for c in DEFAULT_CATEGORIES])
    print("Added default departments and event categories (editable in Admin > Venues & lists).")


def create_admin(cur, args):
    from webapp.security import hash_password, password_problems, valid_email
    email = args.admin_email or input("First admin e-mail: ").strip().lower()
    if not valid_email(email):
        sys.exit("Invalid e-mail.")
    name = args.admin_name or input("Admin full name: ").strip() or "Administrator"
    pw = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Admin password: ")
    problems = password_problems(pw)
    if problems:
        sys.exit("Password needs " + ", ".join(problems))
    cur.execute("INSERT INTO app_user (full_name, email, password_hash, role, email_verified) "
                "VALUES (%s, %s, %s, 'ADMIN', TRUE)", (name, email, hash_password(pw)))
    print(f"Admin account created: {email}")


def cmd_create_admin(args):
    from webapp import db
    cfg = config.load()
    db.init(config.mysql_params(cfg))
    with db.get().transaction() as cur:
        create_admin(cur, args)


def with_app(fn):
    def wrapper(args):
        from webapp import create_app
        app = create_app({"START_JOBS": False})
        with app.app_context(), app.test_request_context():
            return fn(args, app)
    return wrapper


@with_app
def cmd_seed_demo(args, app):
    from webapp.services import demo
    print(demo.load_demo(actor_id=None))


@with_app
def cmd_go_live(args, app):
    from webapp.services import demo
    if input("Delete ALL demo data and participants? Type GO LIVE: ") != "GO LIVE":
        sys.exit("Aborted.")
    print(demo.go_live(actor_id=None))


@with_app
def cmd_backup(args, app):
    from webapp.services import backups
    print("Backup written:", backups.create(app.config["CFG"], label="manual"))


def cmd_run(args):
    from waitress import serve

    from webapp import create_app
    app = create_app()
    print(f"Serving on http://{args.host}:{args.port}  (put HTTPS in front - see DEPLOY.md)")
    serve(app, host=args.host, port=args.port, threads=16)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init-db")
    i.add_argument("--root-user", default="root")
    i.add_argument("--database")
    i.add_argument("--app-host", default="localhost", help="host part of the MySQL users (default localhost)")
    i.add_argument("--admin-email")
    i.add_argument("--admin-name")
    i.add_argument("--no-admin", action="store_true")
    i.add_argument("--force", action="store_true", help="drop an existing database without asking")
    i.set_defaults(func=init_db)
    a = sub.add_parser("create-admin")
    a.add_argument("--admin-email")
    a.add_argument("--admin-name")
    a.set_defaults(func=cmd_create_admin)
    sub.add_parser("seed-demo").set_defaults(func=cmd_seed_demo)
    sub.add_parser("go-live").set_defaults(func=cmd_go_live)
    sub.add_parser("backup").set_defaults(func=cmd_backup)
    r = sub.add_parser("run")
    r.add_argument("--host", default="127.0.0.1")
    r.add_argument("--port", type=int, default=8000)
    r.set_defaults(func=cmd_run)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
