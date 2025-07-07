#!/usr/bin/env python3
"""Database module for storing user credentials."""

import sqlite3
import os
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
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id INTEGER PRIMARY KEY,
                    username TEXT NOT NULL,
                    password TEXT NOT NULL,
                    active INTEGER DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_check TIMESTAMP,
                    last_status TEXT
                )
            """)
            conn.commit()
    
    @contextmanager
    def get_connection(self):
        """Get a database connection with automatic closing."""
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
        finally:
            conn.close()
    
    def add_user(self, telegram_id: int, username: str, password: str) -> bool:
        """Add or update user credentials."""
        try:
            with self.get_connection() as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO users (telegram_id, username, password, active)
                    VALUES (?, ?, ?, 1)
                """, (telegram_id, username, password))
                conn.commit()
                return True
        except sqlite3.Error:
            return False
    
    def remove_user(self, telegram_id: int) -> bool:
        """Remove user from database."""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "DELETE FROM users WHERE telegram_id = ?", 
                    (telegram_id,)
                )
                conn.commit()
                return cursor.rowcount > 0
        except sqlite3.Error:
            return False
    
    def get_user(self, telegram_id: int) -> Optional[Tuple[str, str]]:
        """Get user credentials by telegram_id."""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT username, password FROM users WHERE telegram_id = ? AND active = 1",
                    (telegram_id,)
                )
                result = cursor.fetchone()
                return result if result else None
        except sqlite3.Error:
            return None
    
    def get_all_active_users(self) -> List[Tuple[int, str, str]]:
        """Get all active users for periodic checking."""
        try:
            with self.get_connection() as conn:
                cursor = conn.execute(
                    "SELECT telegram_id, username, password FROM users WHERE active = 1"
                )
                return cursor.fetchall()
        except sqlite3.Error:
            return []
    
    def update_user_status(self, telegram_id: int, status: str):
        """Update user's last check status."""
        try:
            with self.get_connection() as conn:
                conn.execute("""
                    UPDATE users 
                    SET last_check = CURRENT_TIMESTAMP, last_status = ?
                    WHERE telegram_id = ?
                """, (status, telegram_id))
                conn.commit()
        except sqlite3.Error:
            pass
    
    def deactivate_user(self, telegram_id: int):
        """Deactivate user (for login failures)."""
        try:
            with self.get_connection() as conn:
                conn.execute(
                    "UPDATE users SET active = 0 WHERE telegram_id = ?",
                    (telegram_id,)
                )
                conn.commit()
        except sqlite3.Error:
            pass