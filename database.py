import os
import secrets
import time
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import bcrypt
import psycopg
from psycopg import IntegrityError


DATABASE_URL = os.getenv("DATABASE_URL", "").strip()


def connect_db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")

    if "sslmode=" not in DATABASE_URL:
        parts = urlsplit(DATABASE_URL)
        query = dict(parse_qsl(parts.query))
        query["sslmode"] = "require"
        parts = parts._replace(query=urlencode(query))
        return psycopg.connect(urlunsplit(parts))

    return psycopg.connect(DATABASE_URL)


def init_db():
    with connect_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id SERIAL PRIMARY KEY,
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
                    expires_at DOUBLE PRECISION NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS projects (
                    id SERIAL PRIMARY KEY,
                    user_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    prompt TEXT NOT NULL,
                    code_content TEXT,
                    language TEXT DEFAULT 'html',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id INTEGER PRIMARY KEY,
                    custom_instructions TEXT DEFAULT '',
                    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
                )
            """)

        conn.commit()


def create_user(username, email, password):
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    try:
        with connect_db() as conn:
            with conn.cursor() as cursor:
                cursor.execute("""
                    INSERT INTO users (username, email, password_hash)
                    VALUES (%s, %s, %s)
                    RETURNING id
                """, (username, email, hashed))

                user_id = cursor.fetchone()[0]

        return {
            "success": True,
            "user_id": user_id,
            "username": username,
            "email": email,
        }

    except IntegrityError as error:
        message = str(error).lower()

        if "email" in message:
            return {
                "success": False,
                "error": "This Gmail/email is already registered.",
            }

        return {
            "success": False,
            "error": "Username already exists.",
        }


def authenticate_user(username_or_email, password):
    identifier = username_or_email.strip().lower()

    with connect_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, username, email, password_hash
                FROM users
                WHERE LOWER(username) = %s OR LOWER(email) = %s
            """, (identifier, identifier))

            row = cursor.fetchone()

    if not row:
        return {"success": False, "error": "User account not found."}

    user_id, username, email, hashed = row

    if bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8")):
        return {
            "success": True,
            "user_id": user_id,
            "username": username,
            "email": email,
        }

    return {"success": False, "error": "Incorrect password."}


def create_password_reset_token(email):
    with connect_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT id FROM users WHERE LOWER(email) = LOWER(%s)",
                (email,),
            )

            if not cursor.fetchone():
                return None

            token = secrets.token_urlsafe(32)
            expires_at = time.time() + 3600

            cursor.execute("""
                INSERT INTO reset_tokens (token, email, expires_at)
                VALUES (%s, %s, %s)
            """, (token, email, expires_at))

        conn.commit()

    return token


def reset_password_with_token(token, new_password):
    with connect_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT email, expires_at
                FROM reset_tokens
                WHERE token = %s
            """, (token,))

            row = cursor.fetchone()

            if not row:
                return {
                    "success": False,
                    "error": "Invalid or expired reset link.",
                }

            email, expires_at = row

            if time.time() > expires_at:
                cursor.execute(
                    "DELETE FROM reset_tokens WHERE token = %s",
                    (token,),
                )
                conn.commit()

                return {
                    "success": False,
                    "error": "Reset link has expired.",
                }

            salt = bcrypt.gensalt()
            hashed = bcrypt.hashpw(
                new_password.encode("utf-8"),
                salt,
            ).decode("utf-8")

            cursor.execute(
                "UPDATE users SET password_hash = %s WHERE email = %s",
                (hashed, email),
            )

            cursor.execute(
                "DELETE FROM reset_tokens WHERE token = %s",
                (token,),
            )

        conn.commit()

    return {
        "success": True,
        "message": "Password reset successfully!",
    }


def save_project(user_id, title, prompt, code_content, language="html"):
    with connect_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO projects
                    (user_id, title, prompt, code_content, language)
                VALUES (%s, %s, %s, %s, %s)
            """, (user_id, title, prompt, code_content, language))

        conn.commit()


def get_user_projects(user_id):
    with connect_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT id, title, language, created_at
                FROM projects
                WHERE user_id = %s
                ORDER BY created_at DESC
            """, (user_id,))

            rows = cursor.fetchall()

    return [
        {
            "id": row[0],
            "title": row[1],
            "language": row[2],
            "date": row[3],
        }
        for row in rows
    ]


def delete_project(project_id, user_id):
    with connect_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                DELETE FROM projects
                WHERE id = %s AND user_id = %s
            """, (project_id, user_id))

        conn.commit()


def save_user_instructions(user_id, instructions):
    with connect_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                INSERT INTO user_settings (user_id, custom_instructions)
                VALUES (%s, %s)
                ON CONFLICT (user_id)
                DO UPDATE SET custom_instructions = EXCLUDED.custom_instructions
            """, (user_id, instructions))

        conn.commit()


def get_user_instructions(user_id):
    with connect_db() as conn:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT custom_instructions
                FROM user_settings
                WHERE user_id = %s
            """, (user_id,))

            row = cursor.fetchone()

    return row[0] if row else ""


init_db()
