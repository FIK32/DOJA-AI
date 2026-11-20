import sqlite3
import bcrypt
import secrets
import time

DB_NAME = "doja_studio.db"

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS reset_tokens (
            token TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            expires_at REAL NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            prompt TEXT NOT NULL,
            code_content TEXT,
            language TEXT DEFAULT 'html',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            custom_instructions TEXT DEFAULT '',
            FOREIGN KEY (user_id) REFERENCES users (id)
        )
    """)

    conn.commit()
    conn.close()

def create_user(username, email, password):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")
    try:
        cursor.execute("INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)", (username, email, hashed))
        conn.commit()
        return {"success": True, "user_id": cursor.lastrowid, "username": username, "email": email}
    except sqlite3.IntegrityError as e:
        if "email" in str(e):
            return {"success": False, "error": "This Gmail/email is already registered."}
        return {"success": False, "error": "Username already exists."}
    finally:
        conn.close()

def authenticate_user(username_or_email, password):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    identifier = username_or_email.strip().lower()
    # Case-insensitive query matches regardless of uppercase or lowercase letters
    cursor.execute("""
        SELECT id, username, email, password_hash 
        FROM users 
        WHERE LOWER(username) = ? OR LOWER(email) = ?
    """, (identifier, identifier))
    row = cursor.fetchone()
    conn.close()
    if not row:
        return {"success": False, "error": "User account not found."}
    user_id, username, email, hashed = row
    if bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8")):
        return {"success": True, "user_id": user_id, "username": username, "email": email}
    return {"success": False, "error": "Incorrect password."}
def create_password_reset_token(email):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE email = ?", (email,))
    if not cursor.fetchone():
        conn.close()
        return None
    token = secrets.token_urlsafe(32)
    expires_at = time.time() + 3600
    cursor.execute("INSERT INTO reset_tokens (token, email, expires_at) VALUES (?, ?, ?)", (token, email, expires_at))
    conn.commit()
    conn.close()
    return token

def reset_password_with_token(token, new_password):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT email, expires_at FROM reset_tokens WHERE token = ?", (token,))
    row = cursor.fetchone()
    if not row:
        conn.close()
        return {"success": False, "error": "Invalid or expired reset link."}
    email, expires_at = row
    if time.time() > expires_at:
        cursor.execute("DELETE FROM reset_tokens WHERE token = ?", (token,))
        conn.commit()
        conn.close()
        return {"success": False, "error": "Reset link has expired."}
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(new_password.encode("utf-8"), salt).decode("utf-8")
    cursor.execute("UPDATE users SET password_hash = ? WHERE email = ?", (hashed, email))
    cursor.execute("DELETE FROM reset_tokens WHERE token = ?", (token,))
    conn.commit()
    conn.close()
    return {"success": True, "message": "Password reset successfully!"}

def save_project(user_id, title, prompt, code_content, language="html"):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO projects (user_id, title, prompt, code_content, language) VALUES (?, ?, ?, ?, ?)",
                   (user_id, title, prompt, code_content, language))
    conn.commit()
    conn.close()

def get_user_projects(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT id, title, language, created_at FROM projects WHERE user_id = ? ORDER BY created_at DESC", (user_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"id": r[0], "title": r[1], "language": r[2], "date": r[3]} for r in rows]

def delete_project(project_id, user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM projects WHERE id = ? AND user_id = ?", (project_id, user_id))
    conn.commit()
    conn.close()

def save_user_instructions(user_id, instructions):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO user_settings (user_id, custom_instructions) VALUES (?, ?)", (user_id, instructions))
    conn.commit()
    conn.close()

def get_user_instructions(user_id):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT custom_instructions FROM user_settings WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else ""

init_db()
