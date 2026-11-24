import os
import secrets
import json
from typing import Optional

import requests

APPWRITE_ENDPOINT = os.getenv("APPWRITE_ENDPOINT", "https://nyc.cloud.appwrite.io/v1").rstrip("/")
APPWRITE_PROJECT_ID = os.getenv("APPWRITE_PROJECT_ID", "")
APPWRITE_API_KEY = os.getenv("APPWRITE_API_KEY", "")
APPWRITE_DATABASE_ID = os.getenv("APPWRITE_DATABASE_ID", "")
APPWRITE_PROJECTS_TABLE_ID = os.getenv("APPWRITE_PROJECTS_TABLE_ID", "doja_projects")
APPWRITE_SETTINGS_TABLE_ID = os.getenv("APPWRITE_SETTINGS_TABLE_ID", "doja_user_settings")
APPWRITE_WORKSPACE_BUCKET_ID = os.getenv("APPWRITE_WORKSPACE_BUCKET_ID", "doja_workspace")


def init_db():
    """Appwrite tables and indexes are provisioned in the Appwrite Console."""
    if not APPWRITE_PROJECT_ID:
        raise RuntimeError("APPWRITE_PROJECT_ID is not configured")
    if not APPWRITE_API_KEY:
        raise RuntimeError("APPWRITE_API_KEY is not configured")


def _server_headers():
    return {
        "X-Appwrite-Project": APPWRITE_PROJECT_ID,
        "X-Appwrite-Key": APPWRITE_API_KEY,
        "Content-Type": "application/json",
    }


def _rows_url(table_id: str, row_id: str = None):
    url = f"{APPWRITE_ENDPOINT}/databases/tablesdb/{APPWRITE_DATABASE_ID}/tables/{table_id}/rows"
    return f"{url}/{row_id}" if row_id else url


def _request(method: str, url: str, *, headers=None, json_body=None, params=None, timeout=20):
    response = requests.request(
        method,
        url,
        headers={**_server_headers(), **(headers or {})},
        json=json_body,
        params=params,
        timeout=timeout,
    )
    if not response.ok:
        raise RuntimeError(f"Appwrite error {response.status_code}: {response.text}")
    return response.json() if response.text else {}


def create_user(username, email, password):
    try:
        account_url = f"{APPWRITE_ENDPOINT}/account"
        data = _request(
            "POST",
            account_url,
            headers={"X-Appwrite-Project": APPWRITE_PROJECT_ID, "Content-Type": "application/json"},
            json_body={"userId": "unique()", "email": email, "password": password, "name": username},
        )
        return {"success": True, "user_id": data["$id"], "username": username, "email": email}
    except RuntimeError as error:
        text = str(error).lower()
        if "email" in text or "409" in text:
            return {"success": False, "error": "This Gmail/email is already registered."}
        return {"success": False, "error": "Could not create account."}


def authenticate_user(username_or_email, password):
    """Create a real Appwrite account session and return a session secret for the HttpOnly cookie."""
    url = f"{APPWRITE_ENDPOINT}/account/sessions/email"
    data = _request(
        "POST",
        url,
        headers={"X-Appwrite-Project": APPWRITE_PROJECT_ID, "Content-Type": "application/json"},
        json_body={"email": username_or_email.lower(), "password": password},
    )
    account = get_account_from_session(data["secret"])
    if not account:
        return {"success": False, "error": "Account authentication failed."}
    return {
        "success": True,
        "user_id": account["$id"],
        "username": account.get("name", ""),
        "email": account.get("email", ""),
        "session_secret": data["secret"],
    }


def get_account_from_session(session_secret: str) -> Optional[dict]:
    if not session_secret:
        return None
    try:
        return _request(
            "GET",
            f"{APPWRITE_ENDPOINT}/account",
            headers={
                "X-Appwrite-Project": APPWRITE_PROJECT_ID,
                "X-Appwrite-Session": session_secret,
                "Content-Type": "application/json",
            },
        )
    except RuntimeError:
        return None


def delete_session(session_secret: str):
    if not session_secret:
        return
    try:
        _request(
            "DELETE",
            f"{APPWRITE_ENDPOINT}/account/sessions/current",
            headers={
                "X-Appwrite-Project": APPWRITE_PROJECT_ID,
                "X-Appwrite-Session": session_secret,
                "Content-Type": "application/json",
            },
        )
    except RuntimeError:
        pass


def create_password_reset_token(email):
    try:
        _request(
            "POST",
            f"{APPWRITE_ENDPOINT}/account/recovery",
            headers={"X-Appwrite-Project": APPWRITE_PROJECT_ID, "Content-Type": "application/json"},
            json_body={"email": email, "url": os.getenv("APPWRITE_RECOVERY_URL", "/?reset_token=")},
        )
        return None
    except RuntimeError:
        return None


def reset_password_with_token(token, new_password):
    try:
        _request(
            "PUT",
            f"{APPWRITE_ENDPOINT}/account/recovery",
            headers={"X-Appwrite-Project": APPWRITE_PROJECT_ID, "Content-Type": "application/json"},
            json_body={"userId": token, "secret": token, "password": new_password},
        )
        return {"success": True, "message": "Password reset successfully!"}
    except RuntimeError:
        return {"success": False, "error": "Invalid or expired reset link."}


def save_project(user_id: str, title: str, prompt: str, code_content: str, messages=None, language="html"):
    if not isinstance(messages, list):
        messages = []
    data = {
        "rowId": "unique()",
        "data": {
            "user_id": str(user_id),
            "title": str(title)[:500],
            "prompt": str(prompt)[:20000],
            "code_content": str(code_content)[:1000000],
            "language": str(language)[:100],
            "messages": json.dumps(messages)[:4000000],
        },
    }
    result = _request("POST", _rows_url(APPWRITE_PROJECTS_TABLE_ID), json_body=data)
    return result["$id"]


def get_user_projects(user_id: str):
    result = _request(
        "GET",
        _rows_url(APPWRITE_PROJECTS_TABLE_ID),
        params=[
            ("queries[]", f'equal("user_id", "{user_id}")'),
            ("queries[]", 'orderDesc("$createdAt")'),
        ],
    )
    projects = []
    for row in result.get("rows", result.get("documents", [])):
        projects.append({
            "id": row["$id"],
            "title": row.get("title", "Untitled"),
            "language": row.get("language", "html"),
            "date": row.get("$createdAt", ""),
        })
    return projects


def get_project(project_id: str, user_id: str):
    try:
        row = _request("GET", _rows_url(APPWRITE_PROJECTS_TABLE_ID, project_id))
    except RuntimeError:
        return None
    if row.get("user_id") != str(user_id):
        return None
    raw = row.get("messages", "")
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    messages = []
    if row.get("prompt"):
        messages.append({"role": "user", "content": row["prompt"]})
    if row.get("code_content"):
        messages.append({"role": "assistant", "content": row["code_content"]})
    return messages


def delete_project(project_id: str, user_id: str):
    row = get_project(project_id, user_id)
    if row is None:
        return
    _request("DELETE", _rows_url(APPWRITE_PROJECTS_TABLE_ID, project_id))


def save_user_instructions(user_id: str, instructions: str):
    rows = _request(
        "GET",
        _rows_url(APPWRITE_SETTINGS_TABLE_ID),
        params=[("queries[]", f'equal("user_id", "{user_id}")')],
    )
    existing = (rows.get("rows", rows.get("documents", [])) or [None])[0]
    data = {"data": {"user_id": str(user_id), "custom_instructions": str(instructions)[:50000]}}
    if existing:
        _request("PATCH", _rows_url(APPWRITE_SETTINGS_TABLE_ID, existing["$id"]), json_body=data)
    else:
        data["rowId"] = "unique()"
        _request("POST", _rows_url(APPWRITE_SETTINGS_TABLE_ID), json_body=data)


def get_user_instructions(user_id: str):
    rows = _request(
        "GET",
        _rows_url(APPWRITE_SETTINGS_TABLE_ID),
        params=[("queries[]", f'equal("user_id", "{user_id}")')],
    )
    items = rows.get("rows", rows.get("documents", []))
    return items[0].get("custom_instructions", "") if items else ""


def save_workspace_file(filename: str, content: bytes, user_id: str):
    safe_name = os.path.basename(filename).replace("\\", "_")
    url = f"{APPWRITE_ENDPOINT}/storage/buckets/{APPWRITE_WORKSPACE_BUCKET_ID}/files"
    data = {"fileId": "unique()", "permissions": [f'read("user:{user_id}")', f'update("user:{user_id}")', f'delete("user:{user_id}")']}
    result = requests.post(
        url,
        headers={"X-Appwrite-Project": APPWRITE_PROJECT_ID, "X-Appwrite-Key": APPWRITE_API_KEY},
        data=data,
        files={"file": (safe_name, content)},
        timeout=60,
    )
    if not result.ok:
        raise RuntimeError(f"Appwrite storage error {result.status_code}: {result.text}")
    return result.json()


init_db()
