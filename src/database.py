"""Database management for storing commit history and stats."""

import sqlite3
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime, date


logger = logging.getLogger(__name__)


class Database:
    """SQLite database for commit history and statistics."""

    def __init__(self, db_path: str = "database/scheduler.db"):
        """Initialize database connection.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = None
        self._connect()
        self._create_tables()

    def _connect(self):
        """Create database connection."""
        try:
            self.conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
            self.conn.row_factory = sqlite3.Row
            logger.info(f"Connected to database: {self.db_path}")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise

    def _create_tables(self):
        """Create database tables if they don't exist."""
        try:
            cursor = self.conn.cursor()

            # Commits table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS commits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    hash TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    files_changed INTEGER DEFAULT 0,
                    success BOOLEAN DEFAULT 1,
                    used_ollama BOOLEAN DEFAULT 0,
                    theme TEXT,
                    error_message TEXT,
                    push_success BOOLEAN DEFAULT 0
                )
            """)

            # Stats table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date DATE NOT NULL UNIQUE,
                    total_commits INTEGER DEFAULT 0,
                    successful_commits INTEGER DEFAULT 0,
                    ollama_used INTEGER DEFAULT 0,
                    template_used INTEGER DEFAULT 0
                )
            """)

            # Settings table for key-value config (tokens, etc.)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_commits_timestamp ON commits(timestamp DESC)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_stats_date ON stats(date DESC)")

            self.conn.commit()
            logger.info("Database tables initialized")
        except Exception as e:
            logger.error(f"Failed to create tables: {e}")
            raise

    def add_commit(self, commit_hash: str, message: str, files_changed: int,
                   success: bool, used_ollama: bool, theme: str = "",
                   error_message: str = "", push_success: bool = False) -> int:
        """Add a commit record to the database.

        Args:
            commit_hash: Git commit hash
            message: Commit message
            files_changed: Number of files changed
            success: Whether commit was successful
            used_ollama: Whether Ollama was used for message
            theme: Theme used (if any)
            error_message: Error message if failed
            push_success: Whether push was successful

        Returns:
            ID of inserted record
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO commits (hash, message, files_changed, success, used_ollama, theme, error_message, push_success)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (commit_hash, message, files_changed, success, used_ollama, theme, error_message, push_success))

            commit_id = cursor.lastrowid
            self.conn.commit()

            # Update daily stats
            self._update_daily_stats(success, used_ollama)

            logger.info(f"Added commit to database: {commit_hash}")
            return commit_id
        except Exception as e:
            logger.error(f"Failed to add commit: {e}")
            return -1

    def _update_daily_stats(self, success: bool, used_ollama: bool):
        """Update daily statistics.

        Args:
            success: Whether commit was successful
            used_ollama: Whether Ollama was used
        """
        try:
            today = date.today().isoformat()
            cursor = self.conn.cursor()

            # Check if today's stats exist
            cursor.execute("SELECT id FROM stats WHERE date = ?", (today,))
            exists = cursor.fetchone()

            if exists:
                # Update existing
                cursor.execute("""
                    UPDATE stats
                    SET total_commits = total_commits + 1,
                        successful_commits = successful_commits + ?,
                        ollama_used = ollama_used + ?,
                        template_used = template_used + ?
                    WHERE date = ?
                """, (1 if success else 0, 1 if used_ollama else 0, 0 if used_ollama else 1, today))
            else:
                # Insert new
                cursor.execute("""
                    INSERT INTO stats (date, total_commits, successful_commits, ollama_used, template_used)
                    VALUES (?, 1, ?, ?, ?)
                """, (today, 1 if success else 0, 1 if used_ollama else 0, 0 if used_ollama else 1))

            self.conn.commit()
        except Exception as e:
            logger.error(f"Failed to update daily stats: {e}")

    def get_recent_commits(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent commits.

        Args:
            limit: Maximum number of commits to return

        Returns:
            List of commit dictionaries
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM commits
                ORDER BY timestamp DESC
                LIMIT ?
            """, (limit,))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get recent commits: {e}")
            return []

    def get_commit_count(self) -> int:
        """Get total number of commits.

        Returns:
            Total commit count
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM commits")
            result = cursor.fetchone()
            return result['count'] if result else 0
        except Exception as e:
            logger.error(f"Failed to get commit count: {e}")
            return 0

    def get_success_rate(self) -> float:
        """Get overall success rate.

        Returns:
            Success rate as percentage
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful
                FROM commits
            """)
            result = cursor.fetchone()

            if result and result['total'] > 0:
                return (result['successful'] / result['total']) * 100
            return 0.0
        except Exception as e:
            logger.error(f"Failed to get success rate: {e}")
            return 0.0

    def get_ollama_usage_rate(self) -> float:
        """Get Ollama usage rate.

        Returns:
            Ollama usage rate as percentage
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN used_ollama = 1 THEN 1 ELSE 0 END) as ollama_used
                FROM commits
            """)
            result = cursor.fetchone()

            if result and result['total'] > 0:
                return (result['ollama_used'] / result['total']) * 100
            return 0.0
        except Exception as e:
            logger.error(f"Failed to get Ollama usage rate: {e}")
            return 0.0

    def get_daily_stats(self, days: int = 7) -> List[Dict[str, Any]]:
        """Get daily statistics for the last N days.

        Args:
            days: Number of days to retrieve

        Returns:
            List of daily stat dictionaries
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM stats
                ORDER BY date DESC
                LIMIT ?
            """, (days,))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to get daily stats: {e}")
            return []

    def get_commit_types(self) -> Dict[str, int]:
        """Get count of commits by type (feat, fix, chore, etc.).

        Returns:
            Dictionary of commit type counts
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT message FROM commits WHERE success = 1")
            rows = cursor.fetchall()

            types = {}
            for row in rows:
                message = row['message']
                # Extract type from conventional commit format
                if ':' in message:
                    commit_type = message.split(':')[0].strip().lower()
                    # Remove scope if present (e.g., "feat(api)" -> "feat")
                    if '(' in commit_type:
                        commit_type = commit_type.split('(')[0]
                    types[commit_type] = types.get(commit_type, 0) + 1

            return types
        except Exception as e:
            logger.error(f"Failed to get commit types: {e}")
            return {}

    def get_last_commit(self) -> Optional[Dict[str, Any]]:
        """Get the most recent commit.

        Returns:
            Last commit dictionary or None
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM commits
                ORDER BY timestamp DESC
                LIMIT 1
            """)
            row = cursor.fetchone()
            return dict(row) if row else None
        except Exception as e:
            logger.error(f"Failed to get last commit: {e}")
            return None

    def search_commits(self, search_term: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Search commits by message content.

        Args:
            search_term: Search term
            limit: Maximum results

        Returns:
            List of matching commits
        """
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                SELECT * FROM commits
                WHERE message LIKE ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (f"%{search_term}%", limit))

            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except Exception as e:
            logger.error(f"Failed to search commits: {e}")
            return []

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Get a setting value by key."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
            row = cursor.fetchone()
            return row["value"] if row else default
        except Exception as e:
            logger.error(f"Failed to get setting {key}: {e}")
            return default

    def set_setting(self, key: str, value: str) -> bool:
        """Upsert a setting value."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("""
                INSERT INTO settings (key, value, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
            """, (key, value))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to set setting {key}: {e}")
            return False

    def delete_setting(self, key: str) -> bool:
        """Delete a setting by key."""
        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM settings WHERE key = ?", (key,))
            self.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to delete setting {key}: {e}")
            return False

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            logger.info("Database connection closed")
