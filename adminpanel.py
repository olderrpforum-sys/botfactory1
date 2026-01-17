import os
import sqlite3
import secrets
import hashlib
import hmac
import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Tuple

from dotenv import load_dotenv
from flask import Flask, jsonify, request, g, render_template_string

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = Path(os.environ.get("ADMINPANEL_DB_PATH", BASE_DIR / "adminpanel.db"))

ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
TOKEN_TTL_MINUTES = int(os.environ.get("ADMIN_TOKEN_TTL_MINUTES", "720"))
ADMIN_ALLOWED_IPS = {
    ip.strip()
    for ip in os.environ.get("ADMIN_ALLOWED_IPS", "").split(",")
    if ip.strip()
}

app = Flask(__name__)


def _client_ip() -> str:
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or ""


def _is_admin_ip_allowed() -> bool:
    if not ADMIN_ALLOWED_IPS:
        return True
    return _client_ip() in ADMIN_ALLOWED_IPS


@app.before_request
def _restrict_admin_access():
    if request.path.startswith("/admin") and not _is_admin_ip_allowed():
        return jsonify({"error": "forbidden"}), 403


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        if not DB_PATH.exists():
            init_db()
        db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        needs_init = db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='users'"
        ).fetchone() is None
        if needs_init:
            db.close()
            init_db()
            db = sqlite3.connect(DB_PATH)
            db.row_factory = sqlite3.Row
        g.db = db
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _hash_password(password: str, salt: Optional[bytes] = None) -> str:
    if salt is None:
        salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return f"{salt.hex()}:{digest.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt_hex, digest_hex = stored.split(":", 1)
        salt = bytes.fromhex(salt_hex)
        digest = bytes.fromhex(digest_hex)
    except ValueError:
        return False
    test_digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120000)
    return hmac.compare_digest(digest, test_digest)


def init_db() -> None:
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            login TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL,
            created_at TEXT NOT NULL,
            last_login TEXT
        );
        CREATE TABLE IF NOT EXISTS access_codes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            issued_to TEXT,
            expires_at TEXT,
            revoked_at TEXT,
            created_at TEXT NOT NULL,
            created_by TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS machines (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint TEXT UNIQUE NOT NULL,
            first_seen_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS code_usages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code_id INTEGER NOT NULL,
            machine_id INTEGER NOT NULL,
            used_at TEXT NOT NULL,
            revoked_at TEXT,
            FOREIGN KEY(code_id) REFERENCES access_codes(id),
            FOREIGN KEY(machine_id) REFERENCES machines(id)
        );
        CREATE TABLE IF NOT EXISTS admin_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        );
        """
    )
    db.commit()
    db.close()

    ensure_default_admin()


def ensure_default_admin() -> None:
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    row = db.execute("SELECT id FROM users WHERE login = ?", (ADMIN_USERNAME,)).fetchone()
    if row is None:
        db.execute(
            "INSERT INTO users (login, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            (ADMIN_USERNAME, _hash_password(ADMIN_PASSWORD), "admin", _utc_now()),
        )
        db.commit()
    db.close()


def create_access_code(
    db: sqlite3.Connection,
    issued_to: Optional[str] = None,
    expires_in_days: Optional[int] = None,
    created_by: str = "cli",
) -> Tuple[str, Optional[str]]:
    code = secrets.token_urlsafe(10)
    expires_at = None
    if expires_in_days:
        expires_at = (datetime.now(timezone.utc) + timedelta(days=expires_in_days)).isoformat(
            timespec="seconds"
        )
    db.execute(
        """
        INSERT INTO access_codes (code, issued_to, expires_at, revoked_at, created_at, created_by)
        VALUES (?, ?, ?, NULL, ?, ?)
        """,
        (code, issued_to, expires_at, _utc_now(), created_by),
    )
    db.commit()
    return code, expires_at


def require_admin() -> sqlite3.Row:
    token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
    if not token:
        return None
    db = get_db()
    row = db.execute(
        """
        SELECT admin_sessions.token, admin_sessions.expires_at, users.login, users.role
        FROM admin_sessions
        JOIN users ON users.id = admin_sessions.user_id
        WHERE admin_sessions.token = ?
        """,
        (token,),
    ).fetchone()
    if row is None:
        return None
    if _parse_utc(row["expires_at"]) < datetime.now(timezone.utc):
        return None
    return row


@app.route("/health")
def health():
    return jsonify({"status": "ok"})


@app.route("/")
def index():
    return render_template_string(
        """
        <h1>BotFactory Admin Panel</h1>
        <p>Use the API endpoints via curl/Postman.</p>
        <ul>
          <li>POST /admin/login</li>
          <li>POST /admin/codes</li>
          <li>GET /admin/codes</li>
          <li>POST /admin/codes/&lt;id&gt;/revoke</li>
          <li>POST /admin/codes/&lt;id&gt;/extend</li>
          <li>GET /admin/machines</li>
          <li>GET /admin/usages</li>
        </ul>
        """
    )


@app.route("/admin/login", methods=["POST"])
def admin_login():
    payload = request.get_json(silent=True) or {}
    login = payload.get("login", "")
    password = payload.get("password", "")
    db = get_db()
    row = db.execute("SELECT id, login, password_hash FROM users WHERE login = ?", (login,)).fetchone()
    if row is None or not _verify_password(password, row["password_hash"]):
        return jsonify({"error": "invalid_credentials"}), 401
    db.execute("UPDATE users SET last_login = ? WHERE id = ?", (_utc_now(), row["id"]))
    token = secrets.token_urlsafe(32)
    expires_at = (datetime.now(timezone.utc) + timedelta(minutes=TOKEN_TTL_MINUTES)).isoformat(
        timespec="seconds"
    )
    db.execute(
        "INSERT INTO admin_sessions (token, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
        (token, row["id"], _utc_now(), expires_at),
    )
    db.commit()
    return jsonify({"token": token, "expires_at": expires_at})


@app.route("/admin/codes", methods=["POST"])
def create_code():
    admin = require_admin()
    if admin is None:
        return jsonify({"error": "unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    issued_to = payload.get("issued_to")
    expires_in_days = payload.get("expires_in_days")
    db = get_db()
    code, expires_at = create_access_code(
        db,
        issued_to=issued_to,
        expires_in_days=int(expires_in_days) if expires_in_days else None,
        created_by=admin["login"],
    )
    return jsonify({"code": code, "expires_at": expires_at})


@app.route("/admin/codes", methods=["GET"])
def list_codes():
    if require_admin() is None:
        return jsonify({"error": "unauthorized"}), 401
    db = get_db()
    rows = db.execute("SELECT * FROM access_codes ORDER BY created_at DESC").fetchall()
    return jsonify([dict(row) for row in rows])


@app.route("/admin/codes/<int:code_id>/revoke", methods=["POST"])
def revoke_code(code_id: int):
    if require_admin() is None:
        return jsonify({"error": "unauthorized"}), 401
    db = get_db()
    db.execute("UPDATE access_codes SET revoked_at = ? WHERE id = ?", (_utc_now(), code_id))
    db.execute("UPDATE code_usages SET revoked_at = ? WHERE code_id = ?", (_utc_now(), code_id))
    db.commit()
    return jsonify({"status": "revoked"})


@app.route("/admin/codes/<int:code_id>/extend", methods=["POST"])
def extend_code(code_id: int):
    if require_admin() is None:
        return jsonify({"error": "unauthorized"}), 401
    payload = request.get_json(silent=True) or {}
    days = int(payload.get("days", 0))
    if days <= 0:
        return jsonify({"error": "invalid_days"}), 400
    db = get_db()
    row = db.execute("SELECT expires_at FROM access_codes WHERE id = ?", (code_id,)).fetchone()
    if row is None:
        return jsonify({"error": "not_found"}), 404
    if row["expires_at"]:
        base = _parse_utc(row["expires_at"])
    else:
        base = datetime.now(timezone.utc)
    new_exp = (base + timedelta(days=days)).isoformat(timespec="seconds")
    db.execute("UPDATE access_codes SET expires_at = ? WHERE id = ?", (new_exp, code_id))
    db.commit()
    return jsonify({"expires_at": new_exp})


@app.route("/admin/machines", methods=["GET"])
def list_machines():
    if require_admin() is None:
        return jsonify({"error": "unauthorized"}), 401
    db = get_db()
    rows = db.execute("SELECT * FROM machines ORDER BY last_seen_at DESC").fetchall()
    return jsonify([dict(row) for row in rows])


@app.route("/admin/usages", methods=["GET"])
def list_usages():
    if require_admin() is None:
        return jsonify({"error": "unauthorized"}), 401
    db = get_db()
    rows = db.execute(
        """
        SELECT code_usages.id, access_codes.code, machines.fingerprint, code_usages.used_at, code_usages.revoked_at
        FROM code_usages
        JOIN access_codes ON access_codes.id = code_usages.code_id
        JOIN machines ON machines.id = code_usages.machine_id
        ORDER BY code_usages.used_at DESC
        """
    ).fetchall()
    return jsonify([dict(row) for row in rows])


@app.route("/client/redeem", methods=["POST"])
def client_redeem():
    payload = request.get_json(silent=True) or {}
    code = payload.get("code", "").strip()
    fingerprint = payload.get("fingerprint", "").strip()
    if not code or not fingerprint:
        return jsonify({"error": "missing_fields"}), 400
    db = get_db()
    code_row = db.execute("SELECT * FROM access_codes WHERE code = ?", (code,)).fetchone()
    if code_row is None:
        return jsonify({"error": "invalid_code"}), 404
    if code_row["revoked_at"]:
        return jsonify({"error": "revoked"}), 403
    if code_row["expires_at"] and _parse_utc(code_row["expires_at"]) < datetime.now(timezone.utc):
        return jsonify({"error": "expired"}), 403

    machine = db.execute("SELECT * FROM machines WHERE fingerprint = ?", (fingerprint,)).fetchone()
    if machine is None:
        db.execute(
            "INSERT INTO machines (fingerprint, first_seen_at, last_seen_at) VALUES (?, ?, ?)",
            (fingerprint, _utc_now(), _utc_now()),
        )
        db.commit()
        machine = db.execute("SELECT * FROM machines WHERE fingerprint = ?", (fingerprint,)).fetchone()
    else:
        db.execute("UPDATE machines SET last_seen_at = ? WHERE id = ?", (_utc_now(), machine["id"]))
        db.commit()

    usage = db.execute(
        "SELECT id, used_at, machine_id FROM code_usages WHERE code_id = ?",
        (code_row["id"],),
    ).fetchone()
    activated_at = None
    if usage is None:
        activated_at = _utc_now()
        db.execute(
            "INSERT INTO code_usages (code_id, machine_id, used_at, revoked_at) VALUES (?, ?, ?, NULL)",
            (code_row["id"], machine["id"], activated_at),
        )
        db.commit()
    elif usage["machine_id"] != machine["id"]:
        return jsonify({"error": "already_used"}), 403
    else:
        activated_at = usage["used_at"]

    return jsonify(
        {
            "status": "active",
            "expires_at": code_row["expires_at"],
            "activated_at": activated_at,
        }
    )


@app.route("/client/status", methods=["POST"])
def client_status():
    payload = request.get_json(silent=True) or {}
    code = payload.get("code", "").strip()
    fingerprint = payload.get("fingerprint", "").strip()
    if not code or not fingerprint:
        return jsonify({"error": "missing_fields"}), 400
    db = get_db()
    code_row = db.execute("SELECT * FROM access_codes WHERE code = ?", (code,)).fetchone()
    if code_row is None:
        return jsonify({"error": "invalid_code"}), 404
    if code_row["revoked_at"]:
        return jsonify({"error": "revoked"}), 403
    if code_row["expires_at"] and _parse_utc(code_row["expires_at"]) < datetime.now(timezone.utc):
        return jsonify({"error": "expired"}), 403

    machine = db.execute("SELECT * FROM machines WHERE fingerprint = ?", (fingerprint,)).fetchone()
    if machine is None:
        return jsonify({"error": "machine_unknown"}), 403

    usage = db.execute(
        "SELECT id, revoked_at FROM code_usages WHERE code_id = ? AND machine_id = ?",
        (code_row["id"], machine["id"]),
    ).fetchone()
    if usage is None or usage["revoked_at"]:
        return jsonify({"error": "not_redeemed"}), 403

    return jsonify({"status": "active", "expires_at": code_row["expires_at"]})


def _build_cli_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="BotFactory admin panel utilities")
    subparsers = parser.add_subparsers(dest="command")
    gen = subparsers.add_parser("generate-code", help="Generate a one-time access code")
    gen.add_argument("--issued-to", dest="issued_to", default=None)
    gen.add_argument("--days", dest="days", type=int, default=None)
    return parser


def _handle_cli() -> int:
    parser = _build_cli_parser()
    args = parser.parse_args()
    if not args.command:
        return 1
    if args.command == "generate-code":
        init_db()
        db = sqlite3.connect(DB_PATH)
        code, expires_at = create_access_code(
            db,
            issued_to=args.issued_to,
            expires_in_days=args.days,
            created_by="cli",
        )
        print(json.dumps({"code": code, "expires_at": expires_at}, ensure_ascii=False))
        return 0
    return 1


if __name__ == "__main__":
    if len(sys.argv) > 1:
        raise SystemExit(_handle_cli())
    init_db()
    app.run(host="0.0.0.0", port=int(os.environ.get("ADMINPANEL_PORT", "8000")))
