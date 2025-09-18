import sqlite3
import json
import logging
from datetime import datetime
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, asdict

logger = logging.getLogger(__name__)


@dataclass
class TicketSnapshot:
    """Represents a snapshot of a JIRA ticket at a point in time."""

    key: str
    status: str
    summary: str
    description: str
    assignee: str
    last_updated: str

    @classmethod
    def from_jira_issue(cls, issue):
        """Create a snapshot from a JIRA issue object."""
        # Safely handle summary field that might be None or non-string
        summary = issue.fields.summary or "No summary"
        if not isinstance(summary, str):
            summary = str(summary)

        return cls(
            key=issue.key,
            status=issue.fields.status.name,
            summary=summary,
            description=issue.fields.description or "",
            assignee=(
                issue.fields.assignee.displayName
                if issue.fields.assignee
                else "Unassigned"
            ),
            last_updated=issue.fields.updated,
        )

    def has_changes(self, other: "TicketSnapshot") -> List[str]:
        """Compare with another snapshot and return list of changed fields."""
        changes = []
        if self.status != other.status:
            changes.append(f"Status: {other.status} → {self.status}")
        if self.summary != other.summary:
            changes.append(f"Summary changed")
        if self.description != other.description:
            changes.append(f"Description changed")
        if self.assignee != other.assignee:
            changes.append(f"Assignee: {other.assignee} → {self.assignee}")
        return changes

    @classmethod
    def from_dict(cls, data: dict):
        """Create a snapshot from a dictionary."""
        return cls(**data)

    def to_dict(self) -> dict:
        """Convert snapshot to dictionary."""
        return asdict(self)


class DatabaseManager:
    """Manages SQLite database for JIRA watcher system."""

    def __init__(self, db_path: str = "jira_watcher.db"):
        self.db_path = db_path
        self.init_database()

    def init_database(self):
        """Initialize the database and create tables if they don't exist."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Create watchers table
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS watchers (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        ticket_id TEXT NOT NULL,
                        user_id INTEGER NOT NULL,
                        username TEXT NOT NULL,
                        discriminator TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        UNIQUE(ticket_id, user_id)
                    )
                """
                )

                # Create ticket_snapshots table
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS ticket_snapshots (
                        ticket_id TEXT PRIMARY KEY,
                        status TEXT NOT NULL,
                        summary TEXT NOT NULL,
                        description TEXT,
                        assignee TEXT,
                        last_updated TEXT NOT NULL,
                        snapshot_created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        snapshot_updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """
                )

                # Create indexes for better performance
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_watchers_ticket_id ON watchers(ticket_id)
                """
                )
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_watchers_user_id ON watchers(user_id)
                """
                )

                # Create reminders table
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS reminders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        user_id INTEGER NOT NULL,
                        username TEXT NOT NULL,
                        message TEXT NOT NULL,
                        reminder_time TIMESTAMP NOT NULL,
                        channel_id INTEGER NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        sent BOOLEAN DEFAULT FALSE
                    )
                """
                )

                # Create index for reminder queries
                cursor.execute(
                    """
                    CREATE INDEX IF NOT EXISTS idx_reminders_time ON reminders(reminder_time, sent)
                """
                )

                conn.commit()
                logger.info(f"Database initialized successfully at {self.db_path}")

        except sqlite3.Error as e:
            logger.error(f"Error initializing database: {e}")
            raise

    def add_watcher(
        self, ticket_id: str, user_id: int, username: str, discriminator: str
    ) -> bool:
        """Add a user to watch a specific ticket."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR IGNORE INTO watchers (ticket_id, user_id, username, discriminator)
                    VALUES (?, ?, ?, ?)
                """,
                    (ticket_id, user_id, username, discriminator),
                )

                # Check if the row was actually inserted
                rows_affected = cursor.rowcount
                conn.commit()

                if rows_affected > 0:
                    logger.info(
                        f"Added watcher: user {username}#{discriminator} watching {ticket_id}"
                    )
                    return True
                else:
                    logger.info(
                        f"User {username}#{discriminator} already watching {ticket_id}"
                    )
                    return True  # Still return True since they are watching

        except sqlite3.Error as e:
            logger.error(f"Error adding watcher: {e}")
            return False

    def remove_watcher(self, ticket_id: str, user_id: int) -> bool:
        """Remove a user from watching a specific ticket."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    DELETE FROM watchers WHERE ticket_id = ? AND user_id = ?
                """,
                    (ticket_id, user_id),
                )

                rows_affected = cursor.rowcount
                conn.commit()

                if rows_affected > 0:
                    logger.info(
                        f"Removed watcher: user {user_id} no longer watching {ticket_id}"
                    )
                    return True
                else:
                    logger.info(f"User {user_id} was not watching {ticket_id}")
                    return False

        except sqlite3.Error as e:
            logger.error(f"Error removing watcher: {e}")
            return False

    def get_watchers_for_ticket(self, ticket_id: str) -> List[Dict]:
        """Get all users watching a specific ticket."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT user_id, username, discriminator FROM watchers 
                    WHERE ticket_id = ?
                """,
                    (ticket_id,),
                )

                rows = cursor.fetchall()
                return [
                    {"user_id": row[0], "username": row[1], "discriminator": row[2]}
                    for row in rows
                ]

        except sqlite3.Error as e:
            logger.error(f"Error getting watchers for ticket {ticket_id}: {e}")
            return []

    def get_watched_tickets_for_user(self, user_id: int) -> List[str]:
        """Get all tickets being watched by a specific user."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT ticket_id FROM watchers WHERE user_id = ?
                """,
                    (user_id,),
                )

                rows = cursor.fetchall()
                return [row[0] for row in rows]

        except sqlite3.Error as e:
            logger.error(f"Error getting watched tickets for user {user_id}: {e}")
            return []

    def get_all_watched_tickets(self) -> List[str]:
        """Get all tickets being watched by any user."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT DISTINCT ticket_id FROM watchers
                """
                )

                rows = cursor.fetchall()
                return [row[0] for row in rows]

        except sqlite3.Error as e:
            logger.error(f"Error getting all watched tickets: {e}")
            return []

    def save_ticket_snapshot(self, snapshot: TicketSnapshot) -> bool:
        """Save or update a ticket snapshot."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT OR REPLACE INTO ticket_snapshots 
                    (ticket_id, status, summary, description, assignee, last_updated, snapshot_updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                    (
                        snapshot.key,
                        snapshot.status,
                        snapshot.summary,
                        snapshot.description,
                        snapshot.assignee,
                        snapshot.last_updated,
                    ),
                )

                conn.commit()
                logger.debug(f"Saved snapshot for ticket {snapshot.key}")
                return True

        except sqlite3.Error as e:
            logger.error(f"Error saving snapshot for ticket {snapshot.key}: {e}")
            return False

    def get_ticket_snapshot(self, ticket_id: str) -> Optional[TicketSnapshot]:
        """Get the stored snapshot for a ticket."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT ticket_id, status, summary, description, assignee, last_updated
                    FROM ticket_snapshots WHERE ticket_id = ?
                """,
                    (ticket_id,),
                )

                row = cursor.fetchone()
                if row:
                    return TicketSnapshot(
                        key=row[0],
                        status=row[1],
                        summary=row[2],
                        description=row[3] or "",
                        assignee=row[4] or "Unassigned",
                        last_updated=row[5],
                    )
                return None

        except sqlite3.Error as e:
            logger.error(f"Error getting snapshot for ticket {ticket_id}: {e}")
            return None

    def cleanup_orphaned_snapshots(self) -> int:
        """Remove snapshots for tickets that are no longer being watched."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    DELETE FROM ticket_snapshots 
                    WHERE ticket_id NOT IN (
                        SELECT DISTINCT ticket_id FROM watchers
                    )
                """
                )

                rows_affected = cursor.rowcount
                conn.commit()

                if rows_affected > 0:
                    logger.info(f"Cleaned up {rows_affected} orphaned ticket snapshots")

                return rows_affected

        except sqlite3.Error as e:
            logger.error(f"Error cleaning up orphaned snapshots: {e}")
            return 0

    def get_database_stats(self) -> Dict[str, int]:
        """Get statistics about the database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()

                # Count watchers
                cursor.execute("SELECT COUNT(*) FROM watchers")
                watcher_count = cursor.fetchone()[0]

                # Count unique users
                cursor.execute("SELECT COUNT(DISTINCT user_id) FROM watchers")
                user_count = cursor.fetchone()[0]

                # Count unique tickets being watched
                cursor.execute("SELECT COUNT(DISTINCT ticket_id) FROM watchers")
                watched_ticket_count = cursor.fetchone()[0]

                # Count snapshots
                cursor.execute("SELECT COUNT(*) FROM ticket_snapshots")
                snapshot_count = cursor.fetchone()[0]

                return {
                    "total_watchers": watcher_count,
                    "unique_users": user_count,
                    "watched_tickets": watched_ticket_count,
                    "snapshots": snapshot_count,
                }

        except sqlite3.Error as e:
            logger.error(f"Error getting database stats: {e}")
            return {
                "total_watchers": 0,
                "unique_users": 0,
                "watched_tickets": 0,
                "snapshots": 0,
            }

    def backup_database(self, backup_path: str) -> bool:
        """Create a backup of the database."""
        try:
            with sqlite3.connect(self.db_path) as source:
                with sqlite3.connect(backup_path) as backup:
                    source.backup(backup)

            logger.info(f"Database backed up to {backup_path}")
            return True

        except sqlite3.Error as e:
            logger.error(f"Error backing up database: {e}")
            return False

    def add_reminder(
        self,
        user_id: int,
        username: str,
        message: str,
        reminder_time: datetime,
        channel_id: int,
    ) -> bool:
        """Add a new reminder to the database."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    INSERT INTO reminders (user_id, username, message, reminder_time, channel_id)
                    VALUES (?, ?, ?, ?, ?)
                """,
                    (user_id, username, message, reminder_time.isoformat(), channel_id),
                )
                conn.commit()
                logger.info(f"Added reminder for user {user_id} at {reminder_time}")
                return True

        except sqlite3.Error as e:
            logger.error(f"Error adding reminder: {e}")
            return False

    def get_due_reminders(self) -> List[Dict]:
        """Get all reminders that are due and haven't been sent."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                current_time = datetime.now().isoformat()

                cursor.execute(
                    """
                    SELECT id, user_id, username, message, reminder_time, channel_id 
                    FROM reminders 
                    WHERE reminder_time <= ? AND sent = FALSE
                    ORDER BY reminder_time
                """,
                    (current_time,),
                )

                reminders = []
                for row in cursor.fetchall():
                    reminders.append(
                        {
                            "id": row[0],
                            "user_id": row[1],
                            "username": row[2],
                            "message": row[3],
                            "reminder_time": datetime.fromisoformat(row[4]),
                            "channel_id": row[5],
                        }
                    )

                return reminders

        except sqlite3.Error as e:
            logger.error(f"Error getting due reminders: {e}")
            return []

    def mark_reminder_sent(self, reminder_id: int) -> bool:
        """Mark a reminder as sent."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "UPDATE reminders SET sent = TRUE WHERE id = ?", (reminder_id,)
                )
                conn.commit()
                return True

        except sqlite3.Error as e:
            logger.error(f"Error marking reminder as sent: {e}")
            return False

    def get_user_reminders(self, user_id: int) -> List[Dict]:
        """Get all pending reminders for a user."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    """
                    SELECT id, message, reminder_time 
                    FROM reminders 
                    WHERE user_id = ? AND sent = FALSE
                    ORDER BY reminder_time
                """,
                    (user_id,),
                )

                reminders = []
                for row in cursor.fetchall():
                    reminders.append(
                        {
                            "id": row[0],
                            "message": row[1],
                            "reminder_time": datetime.fromisoformat(row[2]),
                        }
                    )

                return reminders

        except sqlite3.Error as e:
            logger.error(f"Error getting user reminders: {e}")
            return []

    def delete_reminder(self, reminder_id: int, user_id: int) -> bool:
        """Delete a reminder if it belongs to the user."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "DELETE FROM reminders WHERE id = ? AND user_id = ? AND sent = FALSE",
                    (reminder_id, user_id),
                )
                rows_affected = cursor.rowcount
                conn.commit()
                return rows_affected > 0

        except sqlite3.Error as e:
            logger.error(f"Error deleting reminder: {e}")
            return False
