"""Appwrite-backed persistence for DOJA AI.

Create the TablesDB attributes and storage bucket in the Appwrite Console before
starting the service. Secrets are read only from the server environment.
"""

import json
import os
import re
from pathlib import Path
from urllib.parse import quote

import requests

APPWRITE_ENDPOINT = os.getenv("APPWRITE_ENDPOINT", "https://nyc.cloud.appwrite.io/v1").rstrip("/")
APPWRITE_PROJECT_ID = os.getenv("APPWRITE_PROJECT_ID", "")
APPWRITE_API_KEY = os.getenv("APPWRITE_API_KEY", "")
APPWRITE_DATABASE_ID = os.getenv("APPWRITE_DATABASE_ID", "")
APPWRITE_PROJECTS_TABLE_ID = os.getenv("APPWRITE_PROJECTS_TABLE_ID", "doja_projects")
APPWRITE_SETTINGS_TABLE_ID = os.getenv("APPWRITE_SETTINGS_TABLE_ID", "doja_user_settings")
APPWRITE_WORKSPACE_BUCKET_ID = os.getenv("APPWRITE_WORKSPACE_BUCKET_ID", "doja_workspace")
APPWRITE_RECOVERY_URL = os.getenv("APPWRITE_RECOVERY_URL", "")
HTTP_TIMEOUT = 25


def init_db():
    required = {
        "APPWRITE_PROJECT_ID": APPWRITE_PROJECT_ID,
        "APPWRITE_API_KEY": APPWRITE_API_KEY,
        "APPWRITE_DATABASE_ID": APPWRITE_DATABASE_ID,
        "APPWRITE_RECOVERY_URL": APPWRITE_RECOVERY_URL,
    }
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise RuntimeError("Missing Appwrite environment variable(s): " + ", ".join(missing))


def _admin_headers():
    return {
        "X-Appwrite-Project": APPWRITE_PROJECT_ID,
        "X-Appwrite-Key": APPWRITE_API_KEY,
        "Content-Type": "application/json",
    }


def _session_headers(secret: str):
    return {
        "X-Appwrite-Project": APPWRITE_PROJECT_ID,
        "X-Appwrite-Session": secret,
        "Content-Type": "application/json",
    }


def _request(method, url, *, headers=None, json_body=None, params=None, files=None, data=None, timeout=HTTP_TIMEOUT):
    response = requests.request(
        method, url, headers=headers or _admin_headers(), json=json_body,
        params=params, files=files, data=data, timeout=timeout,
    )
    if not response.ok:
        # Avoid putting request payloads or credentials in logs/exceptions.
        try:
            detail = response.json().get("message", "Appwrite request failed")
        except (ValueError, AttributeError):
            detail = "Appwrite request failed"
        raise RuntimeError(f"Appwrite HTTP {response.status_code}: {detail}")
    if not response.content:
        return {}
    if "application/json" in response.headers.get("content-type", ""):
        return response.json()
    return response.content


def _rows_url(table_id, row_id=None):
    base = (f"{APPWRITE_ENDPOINT}/tablesdb/{quote(APPWRITE_DATABASE_ID, safe='')}/"
            f"tables/{quote(table_id, safe='')}/rows")
    return f"{base}/{quote(str(row_id), safe='')}" if row_id else base


def _list_rows(table_id, queries):
    params = [("queries[]", query) for query in queries]
    result = _request("GET", _rows_url(table_id), params=params)
    return result.get("rows", [])


def _create_user_row(username, email, password):
    # Appwrite is the account/auth provider. Passwords are never stored in our tables.
    del password
    result = _request(
        "POST", f"{APPWRITE_ENDPOINT}/users",
        json_body={"userId": "unique()", "email": email, "name": username},
    )
    return result


def create_user(username, email, password):
    try:
        username = username.strip()
        email = email.strip().lower()
        if not username or not email or len(password) < 8:
            return {"success": False, "error": "Enter a username, valid email, and password of at least 8 characters."}
        # The Users API creates the account with an initial password.
        result = _request(
            "POST", f"{APPWRITE_ENDPOINT}/users",
            json_body={"userId": "unique()", "email": email, "password": password, "name": username},
        )
        return {"success": True, "user_id": result["$id"], "username": username, "email": email}
    except RuntimeError as error:
        if "409" in str(error):
            return {"success": False, "error": "That email is already registered."}
        return {"success": False, "error": "Could not create the account. Check Appwrite configuration."}


def _resolve_email(identifier):
    identifier = identifier.strip()
    if "@" in identifier:
        return identifier.lower()
    # Usernames are Appwrite account names. Search the Users API, then authenticate by email.
    result = _request(
        "GET", f"{APPWRITE_ENDPOINT}/users",
        params=[("queries[]", f'search("name", {json.dumps(identifier)})'), ("limit", "10")],
    )
    matches = [u for u in result.get("users", []) if u.get("name", "").casefold() == identifier.casefold()]
    return matches[0].get("email") if len(matches) == 1 else None


def authenticate_user(username_or_email, password):
    email = _resolve_email(username_or_email)
    if not email:
        return {"success": False, "error": "Account not found or username is ambiguous."}
    try:
        result = _request(
            "POST", f"{APPWRITE_ENDPOINT}/account/sessions/email",
            headers={"X-Appwrite-Project": APPWRITE_PROJECT_ID, "Content-Type": "application/json"},
            json_body={"email": email, "password": password},
        )
        account = get_account_from_session(result.get("secret", ""))
        if not account:
            return {"success": False, "error": "Could not verify the Appwrite session."}
        return {
            "success": True,
            "user_id": account["$id"],
            "username": account.get("name", ""),
            "email": account.get("email", ""),
            "session_secret": result["secret"],
        }
    except RuntimeError:
        return {"success": False, "error": "Incorrect email/username or password."}


def get_account_from_session(session_secret):
    if not session_secret:
        return None
    try:
        return _request(
            "GET", f"{APPWRITE_ENDPOINT}/account",
            headers=_session_headers(session_secret),
        )
    except RuntimeError:
        return None


def delete_session(session_secret):
    if not session_secret:
        return
    try:
        _request("DELETE", f"{APPWRITE_ENDPOINT}/account/sessions/current", headers=_session_headers(session_secret))
    except RuntimeError:
        pass


def create_password_reset_token(email):
    # Appwrite emails a recovery link whose URL contains userId and secret.
    return _request(
        "POST", f"{APPWRITE_ENDPOINT}/account/recovery",
        headers={"X-Appwrite-Project": APPWRITE_PROJECT_ID, "Content-Type": "application/json"},
        json_body={"email": email.strip().lower(), "url": APPWRITE_RECOVERY_URL},
    )


def reset_password_with_token(token=None, new_password="", user_id=None, secret=None):
    # Accept a legacy token encoded as "userId:secret" as well as Appwrite's fields.
    if (not user_id or not secret) and isinstance(token, str) and ":" in token:
        user_id, secret = token.split(":", 1)
    if not user_id or not secret or len(new_password) < 8:
        return {"success": False, "error": "Invalid recovery link or password (minimum 8 characters)."}
    try:
        _request(
            "PUT", f"{APPWRITE_ENDPOINT}/account/recovery",
            headers={"X-Appwrite-Project": APPWRITE_PROJECT_ID, "Content-Type": "application/json"},
            json_body={"userId": user_id, "secret": secret, "password": new_password},
        )
        return {"success": True, "message": "Password reset successfully. Please sign in again."}
    except RuntimeError:
        return {"success": False, "error": "Invalid or expired reset link."}


def save_project(user_id, title, prompt, code_content, messages=None, language="html"):
    messages = messages if isinstance(messages, list) else []
    result = _request(
        "POST", _rows_url(APPWRITE_PROJECTS_TABLE_ID),
        json_body={
            "rowId": "unique()",
            "data": {
                "user_id": str(user_id), "title": str(title)[:500],
                "prompt": str(prompt)[:20000], "code_content": str(code_content)[:900000],
                "language": str(language)[:100], "messages": json.dumps(messages, ensure_ascii=False),
            },
        },
    )
    return result["$id"]


def get_user_projects(user_id):
    rows = _list_rows(APPWRITE_PROJECTS_TABLE_ID, [
        f'equal("user_id", {json.dumps(str(user_id))})', 'orderDesc("$createdAt")', 'limit(100)'
    ])
    return [{"id": row["$id"], "title": row.get("title", "Untitled"),
             "language": row.get("language", "html"), "date": row.get("$createdAt", "")}
            for row in rows]


def _get_project_row(project_id, user_id):
    try:
        row = _request("GET", _rows_url(APPWRITE_PROJECTS_TABLE_ID, project_id))
    except RuntimeError:
        return None
    return row if row.get("user_id") == str(user_id) else None


def get_project(project_id, user_id):
    row = _get_project_row(project_id, user_id)
    if row is None:
        return None
    raw = row.get("messages", "")
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(data, list):
            return data
    except (ValueError, TypeError):
        pass
    return ([{"role": "user", "content": row["prompt"]}] if row.get("prompt") else []) + (
        [{"role": "assistant", "content": row["code_content"]}] if row.get("code_content") else []
    )


def delete_project(project_id, user_id):
    if _get_project_row(project_id, user_id) is not None:
        _request("DELETE", _rows_url(APPWRITE_PROJECTS_TABLE_ID, project_id))


def get_user_instructions(user_id):
    rows = _list_rows(APPWRITE_SETTINGS_TABLE_ID, [f'equal("user_id", {json.dumps(str(user_id))})', 'limit(2)'])
    return rows[0].get("custom_instructions", "") if rows else ""


def save_user_instructions(user_id, instructions):
    rows = _list_rows(APPWRITE_SETTINGS_TABLE_ID, [f'equal("user_id", {json.dumps(str(user_id))})', 'limit(2)'])
    payload = {"data": {"user_id": str(user_id), "custom_instructions": str(instructions)[:50000]}}
    if rows:
        _request("PATCH", _rows_url(APPWRITE_SETTINGS_TABLE_ID, rows[0]["$id"]), json_body=payload)
    else:
        payload["rowId"] = "unique()"
        _request("POST", _rows_url(APPWRITE_SETTINGS_TABLE_ID), json_body=payload)


def _workspace_dir(user_id):
    root = Path("workspace").resolve()
    user_dir = (root / str(user_id)).resolve()
    if root not in user_dir.parents:
        raise ValueError("Invalid workspace owner")
    user_dir.mkdir(parents=True, exist_ok=True)
    return user_dir


def _storage_url(file_id=None, view=False):
    base = f"{APPWRITE_ENDPOINT}/storage/buckets/{quote(APPWRITE_WORKSPACE_BUCKET_ID, safe='')}/files"
    if file_id:
        base += f"/{quote(str(file_id), safe='')}"
    return base + ("/view" if view else "")


def save_workspace_file(filename, content, user_id):
    safe_name = Path(filename).name
    if not safe_name or safe_name in {".", ".."}:
        raise ValueError("Invalid workspace filename")
    # Encode the owner in the object name; the bucket remains private.
    stored_name = f"{user_id}__{safe_name}"
    found = _request("GET", _storage_url(), params=[("queries[]", f'search("name", {json.dumps(stored_name)})'), ("limit", "100")])
    for old in found.get("files", []):
        if old.get("name") == stored_name:
            _request("DELETE", _storage_url(old["$id"]))
    response = requests.post(
        _storage_url(), headers={"X-Appwrite-Project": APPWRITE_PROJECT_ID, "X-Appwrite-Key": APPWRITE_API_KEY},
        data={"fileId": "unique()"}, files={"file": (stored_name, content)}, timeout=60,
    )
    if not response.ok:
        raise RuntimeError(f"Appwrite Storage upload failed (HTTP {response.status_code})")
    local = _workspace_dir(user_id) / safe_name
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_bytes(content)
    return response.json()


def list_workspace_files(user_id):
    result = _request("GET", _storage_url(), params=[("limit", "100")])
    directory = _workspace_dir(user_id)
    files = {}
    for meta in result.get("files", []):
        name = meta.get("name", "")
        prefix = f"{user_id}__"
        if not name.startswith(prefix):
            continue
        visible_name = name[len(prefix):]
        if not re.fullmatch(r"[^/\\]+", visible_name):
            continue
        try:
            data = _request("GET", _storage_url(meta["$id"], view=True))
            target = directory / visible_name
            target.write_bytes(data if isinstance(data, bytes) else data.encode())
            files[visible_name] = target.read_text(encoding="utf-8", errors="replace")
        except (RuntimeError, OSError):
            continue
    return files


def delete_workspace_file(filename, user_id):
    safe_name = Path(filename).name
    stored_name = f"{user_id}__{safe_name}"
    result = _request("GET", _storage_url(), params=[("queries[]", f'search("name", {json.dumps(stored_name)})'), ("limit", "100")])
    for meta in result.get("files", []):
        if meta.get("name") == stored_name:
            _request("DELETE", _storage_url(meta["$id"]))
    path = _workspace_dir(user_id) / safe_name
    if path.exists():
        path.unlink()


init_db()
