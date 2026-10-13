from __future__ import annotations
import os
import random
import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from flask import Flask, current_app, g
from werkzeug.security import check_password_hash, generate_password_hash

DATABASE_NAME = "database.db"

ROLE_STUDENT = "student"
ROLE_FACULTY = "faculty"
ROLE_ADMIN = "admin"


@dataclass
class Complaint:
    id: int
    ticket_id: str
    email: str
    prn_or_faculty_id: str
    category: str
    description: str
    image_path: str | None
    status: str
    created_at: str
    submitted_by_role: str = ROLE_STUDENT


@dataclass
class User:
    id: int
    name: str
    email: str
    password: str
    role: str


@dataclass
class ComplaintStatusUpdate:
    id: int
    complaint_id: int
    status: str
    note: str
    created_at: str
    updated_by: str


def _database_path() -> Path:
    return Path(current_app.root_path) / DATABASE_NAME


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = sqlite3.connect(str(_database_path()))
        g.db.row_factory = sqlite3.Row
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _ensure_column(table_name: str, column_name: str, column_sql: str):
    db = get_db()
    columns = [row[1] for row in db.execute(f"PRAGMA table_info({table_name})").fetchall()]
    if column_name not in columns:
        db.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_sql}")


def init_db():
    db = get_db()
    print("DB PATH:", _database_path())
    db.execute("""
        CREATE TABLE IF NOT EXISTS complaints (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id TEXT UNIQUE,
            email TEXT NOT NULL,
            prn_or_faculty_id TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            image_path TEXT,
            status TEXT NOT NULL DEFAULT 'Not Resolved',
            created_at TEXT NOT NULL,
            submitted_by_role TEXT NOT NULL DEFAULT 'student'
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'student'
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS complaint_status_updates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            complaint_id INTEGER NOT NULL,
            status TEXT NOT NULL,
            note TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_by TEXT NOT NULL DEFAULT 'admin',
            FOREIGN KEY (complaint_id) REFERENCES complaints(id) ON DELETE CASCADE
        )
    """)
    _ensure_column("complaints", "submitted_by_role", "TEXT NOT NULL DEFAULT 'student'")
    _ensure_column("users", "name", "TEXT")
    db.commit()
    create_default_admin()


def init_app(app: Flask):
    app.teardown_appcontext(close_db)
    with app.app_context():
        init_db()


def _row_to_complaint(row):
    return Complaint(
        id=row["id"],
        ticket_id=row["ticket_id"],
        email=row["email"],
        prn_or_faculty_id=row["prn_or_faculty_id"],
        category=row["category"],
        description=row["description"],
        image_path=row["image_path"],
        status=row["status"],
        created_at=row["created_at"],
        submitted_by_role=row.get("submitted_by_role", ROLE_STUDENT),
    )


def _row_to_user(row):
    return User(
        id=row["id"],
        name=row["name"],
        email=row["email"],
        password=row["password"],
        role=row["role"],
    )


def _row_to_status_update(row):
    return ComplaintStatusUpdate(
        id=row["id"],
        complaint_id=row["complaint_id"],
        status=row["status"],
        note=row["note"],
        created_at=row["created_at"],
        updated_by=row["updated_by"],
    )


def create_default_admin():
    db = get_db()
    email = os.environ.get("ADMIN_EMAIL", "").strip().lower()
    password = os.environ.get("ADMIN_PASSWORD", "")
    name = os.environ.get("ADMIN_NAME", "System Administrator").strip()
    if not email or not password:
        current_app.logger.warning(
            "No admin account was bootstrapped; set ADMIN_EMAIL and ADMIN_PASSWORD."
        )
        return

    if not db.execute(
        "SELECT 1 FROM users WHERE email = ? AND role = ?",
        (email, ROLE_ADMIN),
    ).fetchone():
        db.execute(
            "INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)",
            (name or "System Administrator", email, generate_password_hash(password), ROLE_ADMIN),
        )
        db.commit()


def create_user(name, email, password, role=ROLE_STUDENT):
    db = get_db()
    db.execute(
        "INSERT INTO users (name, email, password, role) VALUES (?, ?, ?, ?)",
        (name, email.lower().strip(), generate_password_hash(password), role),
    )
    db.commit()


def verify_user(email, password, role):
    db = get_db()
    row = db.execute(
        "SELECT id, name, email, password, role FROM users WHERE email = ? AND role = ?",
        (email.lower().strip(), role),
    ).fetchone()
    if not row:
        return None
    stored_password = row["password"]
    if stored_password.startswith(("scrypt:", "pbkdf2:")):
        if not check_password_hash(stored_password, password):
            return None
    else:
        if stored_password != password:
            return None
        db.execute(
            "UPDATE users SET password = ? WHERE id = ?",
            (generate_password_hash(password), row["id"]),
        )
        db.commit()
    return _row_to_user(row)


def generate_ticket_id():
    return str(random.randint(1000, 9999))


def insert_complaint(email, prn_or_faculty_id, category, description, image_path, submitted_by_role=ROLE_STUDENT):
    db = get_db()
    ticket_id = generate_ticket_id()

    while db.execute(
        "SELECT 1 FROM complaints WHERE ticket_id = ?", (ticket_id,)
    ).fetchone():
        ticket_id = generate_ticket_id()

    created_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    cursor = db.execute(
        """
        INSERT INTO complaints (
            ticket_id, email, prn_or_faculty_id, category,
            description, image_path, status, created_at, submitted_by_role
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            ticket_id, email, prn_or_faculty_id,
            category, description, image_path,
            "Not Resolved", created_at, submitted_by_role
        ),
    )
    complaint_id = cursor.lastrowid
    db.execute(
        "INSERT INTO complaint_status_updates (complaint_id, status, note, created_at, updated_by) VALUES (?, ?, ?, ?, ?)",
        (complaint_id, "Not Resolved", "Complaint filed by user.", created_at, submitted_by_role),
    )
    db.commit()
    return ticket_id


def update_complaint(complaint_id, category=None, description=None, prn_or_faculty_id=None, image_path=None):
    db = get_db()
    current = get_complaint_by_id(complaint_id)
    if current is None:
        return False

    if category is not None:
        current.category = category
    if description is not None:
        current.description = description
    if prn_or_faculty_id is not None:
        current.prn_or_faculty_id = prn_or_faculty_id
    if image_path is not None:
        current.image_path = image_path

    db.execute(
        """
        UPDATE complaints
        SET category = ?, description = ?, prn_or_faculty_id = ?, image_path = ?
        WHERE id = ?
        """,
        (current.category, current.description, current.prn_or_faculty_id, current.image_path, complaint_id),
    )
    db.commit()
    return True


def delete_complaint(complaint_id):
    db = get_db()
    db.execute("DELETE FROM complaint_status_updates WHERE complaint_id = ?", (complaint_id,))
    db.execute("DELETE FROM complaints WHERE id = ?", (complaint_id,))
    db.commit()
    return True


def get_complaint_by_id(complaint_id):
    db = get_db()
    row = db.execute(
        """
        SELECT id, ticket_id, email, prn_or_faculty_id, category,
               description, image_path, status, created_at, submitted_by_role
        FROM complaints
        WHERE id = ?
        """,
        (complaint_id,),
    ).fetchone()

    if not row:
        return None

    return _row_to_complaint(row)


def get_complaint_by_ticket(ticket_id):
    db = get_db()
    row = db.execute(
        """
        SELECT id, ticket_id, email, prn_or_faculty_id, category,
               description, image_path, status, created_at, submitted_by_role
        FROM complaints
        WHERE ticket_id = ?
        """,
        (ticket_id,),
    ).fetchone()

    if not row:
        return None

    return _row_to_complaint(row)


def get_status_history(complaint_id):
    db = get_db()
    rows = db.execute(
        """
        SELECT id, complaint_id, status, note, created_at, updated_by
        FROM complaint_status_updates
        WHERE complaint_id = ?
        ORDER BY created_at DESC
        """,
        (complaint_id,),
    ).fetchall()
    return [_row_to_status_update(row) for row in rows]


def add_status_update(complaint_id, status, note='', updated_by='admin'):
    db = get_db()
    complaint = get_complaint_by_id(complaint_id)
    if complaint is None:
        return None

    created_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        "INSERT INTO complaint_status_updates (complaint_id, status, note, created_at, updated_by) VALUES (?, ?, ?, ?, ?)",
        (complaint_id, status, note, created_at, updated_by),
    )
    db.execute(
        "UPDATE complaints SET status = ? WHERE id = ?",
        (status, complaint_id),
    )
    db.commit()
    return True


def get_complaints(category=None, status=None):
    db = get_db()
    query = """
        SELECT id, ticket_id, email, prn_or_faculty_id, category,
               description, image_path, status, created_at, submitted_by_role
        FROM complaints
    """
    params = []
    conditions = []

    if category:
        conditions.append("category = ?")
        params.append(category)

    if status:
        conditions.append("status = ?")
        params.append(status)

    if conditions:
        query += " WHERE " + " AND ".join(conditions)

    query += " ORDER BY created_at DESC"
    rows = db.execute(query, params).fetchall()
    return [_row_to_complaint(r) for r in rows]


def get_categories():
    db = get_db()
    rows = db.execute("SELECT DISTINCT category FROM complaints ORDER BY category").fetchall()
    return [row["category"] for row in rows]


def get_category_counts():
    db = get_db()
    rows = db.execute("""
        SELECT category, COUNT(*) as count
        FROM complaints
        GROUP BY category
    """).fetchall()

    return [(row["category"], row["count"]) for row in rows]


def get_status_counts():
    db = get_db()
    row = db.execute("""
        SELECT
            SUM(CASE WHEN status='Resolved' THEN 1 ELSE 0 END),
            SUM(CASE WHEN status='Not Resolved' THEN 1 ELSE 0 END)
        FROM complaints
    """).fetchone()

    return row[0] or 0, row[1] or 0


def mark_complaint_resolved(complaint_id):
    db = get_db()
    complaint = get_complaint_by_id(complaint_id)
    if complaint is None:
        return False

    db.execute("UPDATE complaints SET status='Resolved' WHERE id=?", (complaint_id,))
    db.execute(
        "INSERT INTO complaint_status_updates (complaint_id, status, note, created_at, updated_by) VALUES (?, ?, ?, ?, ?)",
        (complaint_id, "Resolved", "Marked as resolved by admin.", datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), ROLE_ADMIN),
    )
    db.commit()
    return True
