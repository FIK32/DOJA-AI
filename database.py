import json
import os
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


def init_db():
    missing = [name for name, value in {"APPWRITE_PROJECT_ID": APPWRITE_PROJECT_ID, "APPWRITE_API_KEY": APPWRITE_API_KEY, "APPWRITE_DATABASE_ID": APPWRITE_DATABASE_ID}.items() if not value]
    if missing:
        raise RuntimeError("Missing Appwrite environment variable(s): " + ", ".join(missing))


def _admin_headers():
    return {"X-Appwrite-Project": APPWRITE_PROJECT_ID, "X-Appwrite-Key": APPWRITE_API_KEY}


def _session_headers(secret):
    return {"X-Appwrite-Project": APPWRITE_PROJECT_ID, "X-Appwrite-Session": secret}


def _request(method, url, headers=None, json_body=None, params=None, timeout=25):
    response = requests.request(method, url, headers=headers or _admin_headers(), json=json_body, params=params, timeout=timeout)
    if not response.ok:
        try:
            message = response.json().get("message", "Appwrite request failed")
        except Exception:
            message = "Appwrite request failed"
        raise RuntimeError(f"Appwrite HTTP {response.status_code}: {message}")
    if not response.content:
        return {}
    return response.json() if "application/json" in response.headers.get("content-type", "") else response.content


def _rows_url(table_id, row_id=None):
    url = f"{APPWRITE_ENDPOINT}/tablesdb/{quote(APPWRITE_DATABASE_ID, safe='')}/tables/{quote(table_id, safe='')}/rows"
    return f"{url}/{quote(str(row_id), safe='')}" if row_id else url


def _storage_url(file_id=None, view=False):
    url = f"{APPWRITE_ENDPOINT}/storage/buckets/{quote(APPWRITE_WORKSPACE_BUCKET_ID, safe='')}/files"
    if file_id:
        url += f"/{quote(str(file_id), safe='')}"
    return url + ("/view" if view else "")


def create_user(username, email, password):
    username, email = username.strip(), email.strip().lower()
    if not username or not email or len(password) < 8:
        return {"success": False, "error": "Enter a username, valid email, and password of at least 8 characters."}
    try:
        user = _request("POST", f"{APPWRITE_ENDPOINT}/users", json_body={"userId": "unique()", "email": email, "password": password, "name": username})
        return {"success": True, "user_id": user["$id"], "username": username, "email": email}
    except RuntimeError as error:
        if "409" in str(error):
            return {"success": False, "error": "That email is already registered."}
        return {"success": False, "error": "Could not create the Appwrite account."}


def _resolve_email(identifier):
    identifier = identifier.strip()
    if "@" in identifier:
        return identifier.lower()
    result = _request("GET", f"{APPWRITE_ENDPOINT}/users", params=[("queries[]", f'search("name", {json.dumps(identifier)})'), ("limit", "10")])
    matches = [u for u in result.get("users", []) if u.get("name", "").casefold() == identifier.casefold()]
    return matches[0].get("email") if len(matches) == 1 else None


def authenticate_user(username_or_email, password):
    email = _resolve_email(username_or_email)
    if not email:
        return {"success": False, "error": "Account not found or username is ambiguous."}
    try:
        session = _request("POST", f"{APPWRITE_ENDPOINT}/account/sessions/email", headers={"X-Appwrite-Project": APPWRITE_PROJECT_ID}, json_body={"email": email, "password": password})
        account = get_account_from_session(session["secret"])
        if not account:
            return {"success": False, "error": "Could not verify the Appwrite session."}
        return {"success": True, "user_id": account["$id"], "username": account.get("name", ""), "email": account.get("email", ""), "session_secret": session["secret"]}
    except RuntimeError:
        return {"success": False, "error": "Incorrect email/username or password."}


def get_account_from_session(secret):
    if not secret:
        return None
    try:
        return _request("GET", f"{APPWRITE_ENDPOINT}/account", headers=_session_headers(secret))
    except RuntimeError:
        return None


def delete_session(secret):
    if not secret:
        return
    try:
        _request("DELETE", f"{APPWRITE_ENDPOINT}/account/sessions/current", headers=_session_headers(secret))
    except RuntimeError:
        pass


def change_password(session_secret, old_password, new_password):
    if len(new_password) < 8:
        return {"success": False, "error": "Password must contain at least 8 characters."}
    try:
        _request("PATCH", f"{APPWRITE_ENDPOINT}/account/password", headers=_session_headers(session_secret), json_body={"password": new_password, "oldPassword": old_password})
        return {"success": True, "message": "Password updated successfully."}
    except RuntimeError:
        return {"success": False, "error": "Current password is incorrect or the session expired."}


def create_password_reset_token(email, recovery_url):
    if not recovery_url:
        raise RuntimeError("APPWRITE_RECOVERY_URL is not configured")
    return _request("POST", f"{APPWRITE_ENDPOINT}/account/recovery", headers={"X-Appwrite-Project": APPWRITE_PROJECT_ID}, json_body={"email": email.strip().lower(), "url": recovery_url})


def reset_password_with_token(token, new_password, user_id="", secret=""):
    if (not user_id or not secret) and isinstance(token, str) and ":" in token:
        user_id, secret = token.split(":", 1)
    if not user_id or not secret or len(new_password) < 8:
        return {"success": False, "error": "Invalid recovery link or password (minimum 8 characters)."}
    try:
        _request("PUT", f"{APPWRITE_ENDPOINT}/account/recovery", headers={"X-Appwrite-Project": APPWRITE_PROJECT_ID}, json_body={"userId": user_id, "secret": secret, "password": new_password})
        return {"success": True, "message": "Password reset successfully. Please sign in again."}
    except RuntimeError:
        return {"success": False, "error": "Invalid or expired reset link."}


def _list_rows(table_id, queries):
    result = _request("GET", _rows_url(table_id), params=[("queries[]", query) for query in queries])
    return result.get("rows", [])


def save_project(user_id, title, prompt, code_content, messages=None, language="html"):
    messages = messages if isinstance(messages, list) else []
    result = _request("POST", _rows_url(APPWRITE_PROJECTS_TABLE_ID), json_body={"rowId":"unique()","data":{"user_id":str(user_id),"title":str(title)[:500],"prompt":str(prompt)[:20000],"code_content":str(code_content)[:900000],"language":str(language)[:100],"messages":json.dumps(messages, ensure_ascii=False)}})
    return result["$id"]


def get_user_projects(user_id):
    rows = _list_rows(APPWRITE_PROJECTS_TABLE_ID, [f'equal("user_id", {json.dumps(str(user_id))})','orderDesc("$createdAt")','limit(100)'])
    return [{"id":row["$id"],"title":row.get("title","Untitled"),"language":row.get("language","html"),"date":row.get("$createdAt","")} for row in rows]


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
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(parsed, list):
            return parsed
    except (ValueError, TypeError):
        pass
    messages = []
    if row.get("prompt"):
        messages.append({"role":"user","content":row["prompt"]})
    if row.get("code_content"):
        messages.append({"role":"assistant","content":row["code_content"]})
    return messages


def delete_project(project_id, user_id):
    if _get_project_row(project_id, user_id) is not None:
        _request("DELETE", _rows_url(APPWRITE_PROJECTS_TABLE_ID, project_id))


def get_user_instructions(user_id):
    rows = _list_rows(APPWRITE_SETTINGS_TABLE_ID, [f'equal("user_id", {json.dumps(str(user_id))})','limit(2)'])
    return rows[0].get("custom_instructions", "") if rows else ""


def save_user_instructions(user_id, instructions):
    rows = _list_rows(APPWRITE_SETTINGS_TABLE_ID, [f'equal("user_id", {json.dumps(str(user_id))})','limit(2)'])
    payload = {"data":{"user_id":str(user_id),"custom_instructions":str(instructions)[:50000]}}
    if rows:
        _request("PATCH", _rows_url(APPWRITE_SETTINGS_TABLE_ID, rows[0]["$id"]), json_body=payload)
    else:
        payload["rowId"] = "unique()"
        _request("POST", _rows_url(APPWRITE_SETTINGS_TABLE_ID), json_body=payload)


def _workspace_dir(user_id):
    root = Path("workspace").resolve()
    directory = (root / str(user_id)).resolve()
    if root not in directory.parents:
        raise ValueError("Invalid workspace owner")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def save_workspace_file(filename, content, user_id):
    safe_name = Path(filename).name
    if not safe_name or safe_name in {".",".."}:
        raise ValueError("Invalid workspace filename")
    stored_name = f"{user_id}__{safe_name}"
    existing = _request("GET", _storage_url(), params=[("queries[]",f'search("name", {json.dumps(stored_name)})'),("limit","100")])
    for old in existing.get("files", []):
        if old.get("name") == stored_name:
            _request("DELETE", _storage_url(old["$id"]))
    response = requests.post(_storage_url(), headers={"X-Appwrite-Project":APPWRITE_PROJECT_ID,"X-Appwrite-Key":APPWRITE_API_KEY}, data={"fileId":"unique()"}, files={"file":(stored_name,content)}, timeout=60)
    if not response.ok:
        raise RuntimeError(f"Appwrite Storage upload failed (HTTP {response.status_code})")
    local = _workspace_dir(user_id) / safe_name
    local.write_bytes(content)
    return response.json()


def list_workspace_files(user_id):
    result = _request("GET", _storage_url(), params=[("limit","100")])
    directory = _workspace_dir(user_id)
    output = {}
    prefix = f"{user_id}__"
    for meta in result.get("files", []):
        name = meta.get("name", "")
        if not name.startswith(prefix):
            continue
        visible = name[len(prefix):]
        if "/" in visible or "\\" in visible:
            continue
        try:
            data = _request("GET", _storage_url(meta["$id"], view=True))
            content = data if isinstance(data, bytes) else str(data).encode()
            local = directory / visible
            local.write_bytes(content)
            output[visible] = local.read_text(encoding="utf-8", errors="replace")
        except (RuntimeError, OSError):
            continue
    return output


init_db()
