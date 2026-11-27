import json
import os
from typing import Any
from urllib.parse import quote

import httpx

ENDPOINT = os.getenv("APPWRITE_ENDPOINT", "").rstrip("/")
PROJECT = os.getenv("APPWRITE_PROJECT_ID", "")
API_KEY = os.getenv("APPWRITE_API_KEY", "")
DATABASE = os.getenv("APPWRITE_DATABASE_ID", "")
BUCKET = os.getenv("APPWRITE_WORKSPACE_BUCKET_ID", "")
COLLECTIONS = {
    "chats": os.getenv("APPWRITE_CHATS_COLLECTION_ID", ""),
    "projects": os.getenv("APPWRITE_PROJECTS_COLLECTION_ID", ""),
    "settings": os.getenv("APPWRITE_SETTINGS_COLLECTION_ID", ""),
}


class ConfigurationError(RuntimeError):
    pass


def _ready(*, database=False, bucket=False, key=False):
    if not ENDPOINT or not PROJECT:
        raise ConfigurationError("Appwrite is not configured yet. Add the Appwrite endpoint and project ID as environment variables.")
    if key and not API_KEY:
        raise ConfigurationError("Set APPWRITE_API_KEY in your hosting environment before using this feature.")
    if database and (not DATABASE or not all(COLLECTIONS.values())):
        raise ConfigurationError("Configure the Appwrite database ID and chats, projects, and settings collection IDs.")
    if bucket and not BUCKET:
        raise ConfigurationError("Configure APPWRITE_WORKSPACE_BUCKET_ID to use workspace file storage.")


def _headers(session=None, admin=False):
    headers = {"X-Appwrite-Project": PROJECT, "Content-Type": "application/json"}
    if session:
        headers["X-Appwrite-Session"] = session
    if admin and API_KEY:
        headers["X-Appwrite-Key"] = API_KEY
    return headers


def _request(method, path, *, session=None, admin=False, params=None, json_body=None, files=None, data=None, headers=None):
    _ready(key=admin)
    h = _headers(session=session, admin=admin)
    if files is not None:
        h.pop("Content-Type", None)
    if headers:
        h.update(headers)
    response = httpx.request(method, f"{ENDPOINT}{path}", headers=h, params=params, json=json_body, files=files, data=data, timeout=60)
    if response.status_code >= 400:
        try:
            detail = response.json().get("message", response.text)
        except Exception:
            detail = response.text
        raise RuntimeError(f"Appwrite ({response.status_code}): {detail}")
    if not response.content:
        return {}
    return response.json()


def create_account(name: str, email: str, password: str):
    _ready()
    return _request("POST", "/account", json_body={"userId": "unique()", "email": email, "password": password, "name": name})


def login(email: str, password: str):
    _ready()
    return _request("POST", "/account/sessions/email", json_body={"email": email, "password": password})


def account(session: str):
    return _request("GET", "/account", session=session)


def logout(session: str):
    return _request("DELETE", "/account/sessions/current", session=session)


def password_recovery(email: str, url: str):
    _ready()
    if not url:
        raise ConfigurationError("Set APPWRITE_RECOVERY_URL to your deployed website URL.")
    return _request("POST", "/account/recovery", json_body={"email": email, "url": url})


def password_reset(user_id: str, secret: str, password: str):
    _ready()
    return _request("PUT", "/account/recovery", json_body={"userId": user_id, "secret": secret, "password": password, "passwordAgain": password})


def password_change(session: str, current: str, new: str):
    return _request("PATCH", "/account/password", session=session, json_body={"password": current, "newPassword": new})


def _collection(kind):
    _ready(database=True, key=True)
    if kind not in COLLECTIONS:
        raise ValueError("Unknown Appwrite collection")
    return f"/databases/{quote(DATABASE, safe='')}/collections/{quote(COLLECTIONS[kind], safe='')}/documents"


def _doc_path(kind, doc_id):
    return f"{_collection(kind)}/{quote(doc_id, safe='')}"


def create_record(kind: str, owner: str, payload: dict):
    data = {"ownerId": owner, "payload": json.dumps(payload, ensure_ascii=False)}
    return _request("POST", _collection(kind), admin=True, json_body={"documentId": "unique()", "data": data, "permissions": [f'read("user:{owner}")', f'update("user:{owner}")', f'delete("user:{owner}")']})


def list_records(kind: str, owner: str):
    from urllib.parse import quote as q
    query = q(json.dumps({"method": "equal", "attribute": "ownerId", "values": [owner]}, separators=(",", ":")))
    result = _request("GET", _collection(kind), admin=True, params=[("queries[]", query), ("limit", "100")])
    return result.get("documents", [])


def get_record(kind: str, owner: str, doc_id: str):
    doc = _request("GET", _doc_path(kind, doc_id), admin=True)
    if doc.get("ownerId") != owner:
        raise PermissionError("Record not found or access denied.")
    return doc


def update_record(kind: str, owner: str, doc_id: str, payload: dict):
    get_record(kind, owner, doc_id)
    return _request("PATCH", _doc_path(kind, doc_id), admin=True, json_body={"data": {"ownerId": owner, "payload": json.dumps(payload, ensure_ascii=False)}})


def delete_record(kind: str, owner: str, doc_id: str):
    get_record(kind, owner, doc_id)
    return _request("DELETE", _doc_path(kind, doc_id), admin=True)


def save_chat(owner: str, record: dict):
    chat_id = record.pop("id", "")
    if chat_id:
        try:
            return update_record("chats", owner, chat_id, record)
        except RuntimeError as exc:
            if "404" not in str(exc):
                raise
    return create_record("chats", owner, record)


def get_settings(owner: str):
    matches = list_records("settings", owner)
    if not matches:
        return {"theme": "dark", "model": "", "instructions": ""}
    payload = json.loads(matches[0].get("payload", "{}"))
    payload["_id"] = matches[0]["$id"]
    return payload


def put_settings(owner: str, values: dict):
    current = get_settings(owner)
    doc_id = current.pop("_id", None)
    current.update(values)
    if doc_id:
        update_record("settings", owner, doc_id, current)
    else:
        create_record("settings", owner, current)
    current.pop("_id", None)
    return current


def _bucket_path(owner: str, suffix=""):
    _ready(bucket=True, key=True)
    return f"/storage/buckets/{quote(BUCKET, safe='')}/files{suffix}"


def storage_upload(owner: str, name: str, content: bytes, mime: str):
    path = _bucket_path(owner)
    permissions = [f'read("user:{owner}")', f'delete("user:{owner}")']
    return _request("POST", path, admin=True, params=[("fileId", "unique()"), *[("permissions[]", p) for p in permissions]], files={"file": (name, content, mime)})


def storage_list(owner: str):
    result = _request("GET", _bucket_path(owner), admin=True, params={"limit": 100})
    return [{"id": item["$id"], "name": item.get("name", "file"), "size": item.get("sizeOriginal", 0), "mime": item.get("mimeType", "application/octet-stream")} for item in result.get("files", [])]


def storage_download(owner: str, file_id: str):
    path = _bucket_path(owner, f"/{quote(file_id, safe='')}/download")
    _ready(key=True)
    response = httpx.get(f"{ENDPOINT}{path}", headers={"X-Appwrite-Project": PROJECT, "X-Appwrite-Key": API_KEY}, timeout=60)
    if response.status_code >= 400:
        raise RuntimeError(f"Appwrite download failed ({response.status_code}).")
    name = response.headers.get("content-disposition", "").split("filename=")[-1].strip('"') or file_id
    return name, response.content, response.headers.get("content-type", "application/octet-stream")


def storage_delete(owner: str, file_id: str):
    return _request("DELETE", _bucket_path(owner, f"/{quote(file_id, safe='')}"), admin=True)
