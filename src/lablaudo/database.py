#!/usr/bin/env python3
"""Database module for storing user credentials."""

import sqlite3
from typing import List, Tuple, Optional
from contextlib import contextmanager


class Database:
    """SQLite database for storing user credentials."""
    
    def __init__(self, db_path: str = "lablaudo.db"):
        self.db_path = db_path
        self.init_database()
    
    def init_database(self):
        """Initialize the database with required tables."""
        with self.get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS credentials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    username TEXT NOT NULL,
                    password TEXT NOT NULL,
                    active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_check TIMESTAMP,
                    last_status TEXT,
                    UNIQUE(chat_id, username)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS exams (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    credential_id INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    expected_date TEXT,
                    FOREIGN KEY (credential_id) REFERENCES credentials(id) ON DELETE CASCADE
                )
            """)
            # Migrate from old schemas if needed
            try:
                cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
                if cursor.fetchone():
                    conn.execute("""
                        INSERT OR IGNORE INTO credentials (chat_id, username, password, active, created_at, last_check, last_status)
                        SELECT telegram_id, username, password, active, created_at, last_check, last_status FROM users
                    """)
                    conn.execute("DROP TABLE users")
                    conn.commit()
            except sqlite3.Error:
                pass
            # Migrate old credentials table with telegram_id column
            try:
                cursor = conn.execute("PRAGMA table_info(credentials)")
                columns = [row[1] for row in cursor.fetchall()]
                if 'telegram_id' in columns and 'chat_id' not in columns:
                    conn.execute("ALTER TABLE credentials RENAME COLUMN telegram_id TO chat_id")
                    conn.commit()
            except sqlite3.Error:
                pass
            # Drop orphaned exam rows whose credential was deleted before
            # foreign keys were enforced.
            conn.execute(
                "DELETE FROM exams WHERE credential_id NOT IN (SELECT id FROM credentials)"
            )
            conn.commit()
    
    @contextmanager
    def get_connection(self):
        """Get a database connection with foreign keys enabled and automatic closing."""
        conn = sqlite3.connect(self.db_path)
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()
    
    def add_credential(self, chat_id: int, username: str, password: str) -> Optional[int]:
        """Add or update a credential for a chat (user or group). Returns credential id or None."""
        try:
            with self.get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO credentials (chat_id, username, password, active)
                    VALUES (?, ?, ?, 1)
                """, (chat_id, username, password))
                conn.commit()
                cursor = conn.execute(
                    "SELECT id FROM credentials WHERE chat_id = ? AND username = ?",
                    (chat_id, username),
                )
                row = cursor.fetchone()
                return row[0] if row else None
        except sqlite3.Error:
            return None
    
    def remove_credential(self, chat_id: int, credential_id: int) -> bool:
        """Remove a specific credential by id."""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM credentials WHERE id = ? AND chat_id = ?",
                    (credential_id, chat_id)
                )
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error:
            return False

    def remove_credential_by_username(self, chat_id: int, username: str) -> bool:
        """Remove a credential by username."""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM credentials WHERE chat_id = ? AND username = ?",
                    (chat_id, username)
                )
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error:
            return False
    
    
    def get_credentials(self, chat_id: int) -> List[Tuple[int, str, str]]:
        """Get all active credentials for a chat. Returns list of (id, username, password)."""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT id, username, password FROM credentials WHERE chat_id = ? AND active = 1",
                    (chat_id,)
                )
                return cursor.fetchall()
        except sqlite3.Error:
            return []
    
    def get_credential_by_id(self, credential_id: int) -> Optional[Tuple[int, str, str]]:
        """Get a credential by id. Returns (chat_id, username, password)."""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT chat_id, username, password FROM credentials WHERE id = ? AND active = 1",
                    (credential_id,)
                )
                result = cursor.fetchone()
                return result if result else None
        except sqlite3.Error:
            return None
    
    def get_all_active_credentials(self) -> List[Tuple[int, int, str, str]]:
        """Get all active credentials for periodic checking. Returns (credential_id, chat_id, username, password)."""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT id, chat_id, username, password FROM credentials WHERE active = 1"
                )
                return cursor.fetchall()
        except sqlite3.Error:
            return []
    
    def update_credential_status(self, credential_id: int, status: str):
        """Update a credential's last check status."""
        try:
            with self.get_connection() as conn:
                conn.execute("""
                    UPDATE credentials 
                    SET last_check = CURRENT_TIMESTAMP, last_status = ?
                    WHERE id = ?
                """, (status, credential_id))
                conn.commit()
        except sqlite3.Error:
            pass
    
    def get_credential_status(self, credential_id: int) -> Optional[str]:
        """Get a credential's last status."""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT last_status FROM credentials WHERE id = ?",
                    (credential_id,)
                )
                row = cursor.fetchone()
                return row[0] if row else None
        except sqlite3.Error:
            return None
    
    def save_exams(self, credential_id: int, exams: list):
        """Replace stored exams for a credential.

        Each exam should have 'name', 'status', and optionally 'expected_date' (ISO string or None).
        """
        try:
            with self.get_connection() as conn:
                conn.execute("DELETE FROM exams WHERE credential_id = ?", (credential_id,))
                for exam in exams:
                    conn.execute(
                        "INSERT INTO exams (credential_id, name, status, expected_date) VALUES (?, ?, ?, ?)",
                        (credential_id, exam["name"], exam["status"], exam.get("expected_date")),
                    )
                conn.commit()
        except sqlite3.Error:
            pass
    
    def get_exams(self, credential_id: int) -> List[Tuple[str, str, Optional[str]]]:
        """Get stored exams for a credential. Returns list of (name, status, expected_date)."""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT name, status, expected_date FROM exams WHERE credential_id = ?",
                    (credential_id,),
                )
                return cursor.fetchall()
        except sqlite3.Error:
            return []
    
    def get_credential_statuses(self, chat_id: int) -> List[Tuple[int, str, str, str]]:
        """Get all credential statuses for a chat. Returns (id, username, last_check, last_status)."""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT id, username, last_check, last_status FROM credentials WHERE chat_id = ? AND active = 1",
                    (chat_id,)
                )
                return cursor.fetchall()
        except sqlite3.Error:
            return []
    
    def deactivate_credential(self, credential_id: int):
        """Deactivate a credential (for login failures)."""
        try:
            with self.get_connection() as conn:
                conn.execute(
                    "UPDATE credentials SET active = 0 WHERE id = ?",
                    (credential_id,)
                )
                conn.commit()
        except sqlite3.Error:
            pass
