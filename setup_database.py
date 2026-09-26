"""Command-line database setup.

    python setup_database.py            # schema + sample data
    python setup_database.py --empty    # schema + admin account only

WARNING: drops and recreates the configured database.
"""
import sys

from symposium import config
from symposium.services.setup import DEMO_ADMIN, DEMO_STUDENT, initialize

if __name__ == "__main__":
    if not config.exists():
        sys.exit("config.ini not found - copy config.example.ini to config.ini and fill in "
                 "your MySQL password (or just run main.py and use the setup screen).")
    params = config.mysql_params(config.load())
    answer = input(f"This will ERASE and recreate database '{params['database']}'. Continue? [y/N] ")
    if answer.strip().lower() != "y":
        sys.exit("Aborted.")
    with_sample = "--empty" not in sys.argv
    initialize(params, with_sample=with_sample)
    print(f"\nAdmin login   : {DEMO_ADMIN[1]} / {DEMO_ADMIN[2]}")
    if with_sample:
        print(f"Student login : {DEMO_STUDENT[1]} / {DEMO_STUDENT[2]}")
