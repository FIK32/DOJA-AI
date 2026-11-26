"""Appwrite-only data layer for DOJA AI. No SQLite is used."""
import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.query import Query
from appwrite.id import ID


load_dotenv()


client = Client().set_endpoint(os.getenv("APPWRITE_ENDPOINT", "https://cloud.appwrite.io/v1")) \
    .set_project(os.getenv("APPWRITE_PROJECT_ID", "")) \
    .set_key(os.getenv("APPWRITE_API_KEY", ""))
db = Databases(client)
DATABASE_ID = os.getenv("APPWRITE_DATABASE_ID", "")
COLLECTIONS = {
    "users": os.getenv("APPWRITE_USERS_COLLECTION", "users"),
    "sessions": os.getenv("APPWRITE_SESSIONS_COLLECTION", "sessions"),
    "conversations": os.getenv("APPWRITE_CONVERSATIONS_COLLECTION", "conversations"),
    "messages": os.getenv("APPWRITE_MESSAGES_COLLECTION", "messages"),
    "projects": os.getenv("APPWRITE_PROJECTS_COLLECTION", "projects"),
    "settings": os.getenv("APPWRITE_SETTINGS_COLLECTION", "settings"),
}


def _collection(name):
    if not DATABASE_ID or not COLLECTIONS.get(name):
        raise RuntimeError("Appwrite database/collection environment variables are missing.")
    return COLLECTIONS[name]


def create(name, data, document_id=None):
    return db.create_document(DATABASE_ID, _collection(name), document_id or ID.unique(), data)


def get(name, document_id):
    return db.get_document(DATABASE_ID, _collection(name), document_id)


def update(name, document_id, data):
    return db.update_document(DATABASE_ID, _collection(name), document_id, data)

def delete(name, document_id):
    return db.delete_document(DATABASE_ID, _collection(name), document_id)

def list_docs(name, queries=None, limit=100):
    q = list(queries or [])
    q.append(Query.limit(limit))
    return db.list_documents(DATABASE_ID, _collection(name), q).get("documents", [])

def find_one(name, field, value):
    docs = list_docs(name, [Query.equal(field, value)], limit=1)
    return docs[0] if docs else None

def now_iso():
    return datetime.now(timezone.utc).isoformat()
