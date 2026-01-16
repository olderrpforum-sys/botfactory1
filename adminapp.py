import json
import os
import platform
import socket
import uuid
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests

ADMIN_API_BASE = os.environ.get("ADMIN_API_BASE", "http://127.0.0.1:8000")
LICENSE_FILE = Path(os.environ.get("BOTFACTORY_LICENSE_FILE", Path.home() / ".botfactory_license.json"))


def _device_fingerprint() -> str:
    raw = "|".join(
        [
            socket.gethostname(),
            platform.system(),
            platform.release(),
            platform.version(),
            platform.machine(),
            hex(uuid.getnode()),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def load_license() -> Optional[dict]:
    if not LICENSE_FILE.exists():
        return None
    return json.loads(LICENSE_FILE.read_text(encoding="utf-8"))


def save_license(data: dict) -> None:
    LICENSE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _request_json(path: str, payload: dict) -> dict:
    response = requests.post(f"{ADMIN_API_BASE}{path}", json=payload, timeout=15)
    try:
        data = response.json()
    except ValueError:
        data = {"error": "invalid_response"}
    if not response.ok:
        data.setdefault("status_code", response.status_code)
    return data


def redeem_code(code: str) -> dict:
    payload = {"code": code, "fingerprint": _device_fingerprint(), "app_version": "1.0.0"}
    return _request_json("/client/redeem", payload)


def check_status(code: str) -> dict:
    payload = {"code": code, "fingerprint": _device_fingerprint()}
    return _request_json("/client/status", payload)


def require_license() -> dict:
    data = load_license()
    if data:
        result = check_status(data["code"])
        if result.get("status") == "active":
            return result
        if result.get("error") == "invalid_response":
            return {"error": "offline_or_invalid"}
        return result
    code = input("Введите код доступа: ").strip()
    result = redeem_code(code)
    save_license(
        {
            "code": code,
            "activated_at": result.get("activated_at")
            or datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
    )
    return result


if __name__ == "__main__":
    result = require_license()
    print("License status:", result)
