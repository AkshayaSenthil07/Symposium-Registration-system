"""Application configuration stored in config.ini (kept out of version control)."""
import configparser
import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.ini")
SCHEMA_PATH = os.path.join(BASE_DIR, "database", "schema.sql")
EXPORT_DIR = os.path.join(BASE_DIR, "exports")

DEFAULTS = {
    "mysql": {
        "host": "localhost",
        "port": "3306",
        "user": "root",
        "password": "",
        "database": "symposium_db",
    },
    "app": {
        "appearance": "dark",
    },
}


def load() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg.read_dict(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        cfg.read(CONFIG_PATH, encoding="utf-8")
    return cfg


def exists() -> bool:
    return os.path.exists(CONFIG_PATH)


def save(cfg: configparser.ConfigParser) -> None:
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        cfg.write(f)


def mysql_params(cfg: configparser.ConfigParser) -> dict:
    s = cfg["mysql"]
    return {
        "host": s.get("host", "localhost"),
        "port": s.getint("port", 3306),
        "user": s.get("user", "root"),
        "password": s.get("password", ""),
        "database": s.get("database", "symposium_db"),
    }


def export_path(filename: str) -> str:
    os.makedirs(EXPORT_DIR, exist_ok=True)
    return os.path.join(EXPORT_DIR, filename)


def open_file(path: str) -> None:
    """Open a generated file with the OS default application."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # noqa: S606 - opening our own export
        elif sys.platform == "darwin":
            os.system(f'open "{path}"')
        else:
            os.system(f'xdg-open "{path}"')
    except OSError:
        pass
