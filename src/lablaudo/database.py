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
            conn.commit()
    
    @contextmanager
    def get_connection(self):
        """Get a database connection with automatic closing."""
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()
    
    def add_credential(self, chat_id: int, username: str, password: str) -> bool:
        """Add or update a credential for a chat (user or group)."""
        try:
            with self.get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO credentials (chat_id, username, password, active)
                    VALUES (?, ?, ?, 1)
                """, (chat_id, username, password))
                conn.commit()
                return True
        except sqlite3.Error:
            return False
    
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
