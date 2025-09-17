import logging
import os
import asyncio
import discord
import json
from datetime import datetime, timedelta, time, timezone
from typing import Dict, List, Set
import sys
from dotenv import load_dotenv
from utils.jira import JIRA
from utils.bitbucket import Bitbucket
from logs.logger import logger
from utils.helper import process_issue
from utils.database import DatabaseManager, TicketSnapshot

load_dotenv()


# Load configuration
def load_config():
    """Load configuration from config.json."""
    try:
        with open("config.json", "r") as config_file:
            config = json.load(config_file)
            return config
    except FileNotFoundError:
        logger.error("config.json file not found")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Error parsing config.json: {e}")
        raise


def parse_time_string(time_str: str) -> time:
    """Parse time string in format HHMM to time object.

    Args:
        time_str: Time in format like '1000' for 10:00 AM or '1310' for 1:10 PM

    Returns:
        datetime.time object
    """
    if len(time_str) == 3:  # e.g., '900' for 9:00 AM
        time_str = "0" + time_str
    elif len(time_str) != 4:
        raise ValueError(f"Invalid time format: {time_str}. Expected HHMM format.")

    hour = int(time_str[:2])
    minute = int(time_str[2:])

    if hour > 23 or minute > 59:
        raise ValueError(f"Invalid time: {hour}:{minute:02d}")

    return time(hour, minute)


def get_next_scheduled_run(run_times: List[str]) -> datetime:
    """Get the next scheduled run time based on config.

    Args:
        run_times: List of time strings from config.json

    Returns:
        Next datetime when the script should run
    """
    now = datetime.now()
    today_times = []

    for time_str in run_times:
        try:
            parsed_time = parse_time_string(time_str)
            today_datetime = datetime.combine(now.date(), parsed_time)

            if today_datetime > now:
                today_times.append(today_datetime)
        except ValueError as e:
            logger.error(f"Invalid time in config: {time_str} - {e}")
            continue

    if today_times:
        return min(today_times)
    else:
        # All times for today have passed, get earliest time tomorrow
        tomorrow = now.date() + timedelta(days=1)
        try:
            earliest_time = min([parse_time_string(t) for t in run_times])
            return datetime.combine(tomorrow, earliest_time)
        except ValueError:
            # If all times are invalid, default to next hour
            return now + timedelta(hours=1)


# Load config at startup
config = load_config()
logger.info(
    f"Loaded config: watch_interval={config.get('watch_interval', 5)} min, "
    f"status_updater_interval={config.get('status_updater_interval', 60)} min, "
    f"run_on={config.get('run_on', ['1000'])}, "
    f"run_status_updater_on_interval={config.get('run_status_updater_on_interval', True)}"
)

# Configure detailed logging (logger setup is in logs/logger.py)
bot_logger = logging.getLogger(__name__)
bot_logger.info("Initializing Auto JIRA Status Updater System")
bot_logger.info("System components: Discord Bot + Hourly Worker Integration")


class DiscordLogHandler(logging.Handler):
    """Custom logging handler that sends logs to Discord."""

    def __init__(self, discord_client: discord.Client, channel_id: int):
        super().__init__()
        self.discord_client = discord_client
        self.channel_id = channel_id
        self.log_buffer = []

    def emit(self, record):
        """Capture log records in buffer."""
        if self.discord_client.is_ready():
            log_entry = self.format(record)
            self.log_buffer.append(log_entry)

    async def send_logs(self):
        """Send buffered logs to Discord channel."""
        if not self.log_buffer:
            return

        try:
            channel = self.discord_client.get_channel(self.channel_id)
            if not channel:
                print(
                    f"Warning: Could not find Discord channel with ID {self.channel_id}"
                )
                return

            # Combine logs into chunks (Discord message limit is 2000 chars)
            log_text = "\n".join(self.log_buffer)

            # Split into chunks if too long
            chunks = []
            if len(log_text) <= 1900:  # Leave some room for code block formatting
                chunks.append(log_text)
            else:
                # Split into smaller chunks
                lines = self.log_buffer
                current_chunk = ""

                for line in lines:
                    if len(current_chunk) + len(line) + 1 <= 1900:
                        current_chunk += line + "\n"
                    else:
                        if current_chunk:
                            chunks.append(current_chunk.strip())
                        current_chunk = line + "\n"

                if current_chunk:
                    chunks.append(current_chunk.strip())

            # Send each chunk
            for i, chunk in enumerate(chunks):
                if len(chunks) > 1:
                    await channel.send(
                        f"```\n📊 JIRA Status Updater Log (Part {i+1}/{len(chunks)})\n{'-'*50}\n{chunk}\n```"
                    )
                else:
                    await channel.send(
                        f"```\n📊 JIRA Status Updater Log\n{'-'*50}\n{chunk}\n```"
                    )

            # Clear buffer after sending
            self.log_buffer.clear()

        except Exception as e:
            print(f"Error sending logs to Discord: {e}")


class JIRAWatcher:
    """Manages JIRA ticket watching and change detection using SQLite."""

    def __init__(self, jira_client: JIRA, db_manager: DatabaseManager):
        self.jira = jira_client
        self.db = db_manager

    def add_watcher(self, ticket_id: str, user: discord.User) -> bool:
        """Add a user to watch a specific ticket."""
        # First, try to fetch the ticket to validate it exists
        try:
            issue = self.jira.client.issue(ticket_id)
            snapshot = TicketSnapshot.from_jira_issue(issue)

            # Save the initial snapshot
            self.db.save_ticket_snapshot(snapshot)

            # Add the watcher
            success = self.db.add_watcher(
                ticket_id=ticket_id,
                user_id=user.id,
                username=user.name,
                discriminator=(
                    user.discriminator if hasattr(user, "discriminator") else "0000"
                ),
            )

            if success:
                bot_logger.info(
                    f"Successfully added watcher for {ticket_id}: {user.name}"
                )

            return success

        except Exception as e:
            bot_logger.error(f"Failed to add watcher for {ticket_id}: {e}")
            return False

    def remove_watcher(self, ticket_id: str, user_id: int) -> bool:
        """Remove a user from watching a specific ticket."""
        success = self.db.remove_watcher(ticket_id, user_id)

        # Clean up orphaned snapshots
        if success:
            self.db.cleanup_orphaned_snapshots()

        return success

    def get_watched_tickets_for_user(self, user_id: int) -> List[str]:
        """Get all tickets being watched by a specific user."""
        return self.db.get_watched_tickets_for_user(user_id)

    async def check_for_changes(self, bot_client: discord.Client) -> List[Dict]:
        """Check all watched tickets for changes and return notifications to send."""
        notifications = []
        watched_tickets = self.db.get_all_watched_tickets()

        bot_logger.debug(f"Checking {len(watched_tickets)} watched tickets for changes")

        for ticket_id in watched_tickets:
            try:
                # Fetch current state from JIRA
                issue = self.jira.client.issue(ticket_id)
                current_snapshot = TicketSnapshot.from_jira_issue(issue)

                # Get stored snapshot
                old_snapshot = self.db.get_ticket_snapshot(ticket_id)

                if old_snapshot:
                    # Compare snapshots for changes
                    changes = current_snapshot.has_changes(old_snapshot)

                    if changes:
                        bot_logger.info(f"Changes detected in {ticket_id}: {changes}")

                        # Get all watchers for this ticket
                        watchers = self.db.get_watchers_for_ticket(ticket_id)

                        for watcher in watchers:
                            # Get Discord user object
                            try:
                                user = await bot_client.fetch_user(watcher["user_id"])
                                notifications.append(
                                    {
                                        "user": user,
                                        "ticket_id": ticket_id,
                                        "changes": changes,
                                        "url": f"{self.jira.host}/browse/{ticket_id}",
                                    }
                                )
                            except discord.NotFound:
                                bot_logger.warning(
                                    f"Could not find Discord user {watcher['user_id']}"
                                )
                            except Exception as e:
                                bot_logger.error(
                                    f"Error fetching Discord user {watcher['user_id']}: {e}"
                                )

                # Update snapshot regardless of changes
                self.db.save_ticket_snapshot(current_snapshot)

            except Exception as e:
                bot_logger.error(f"Error checking ticket {ticket_id}: {e}")

                # If ticket doesn't exist anymore, clean up watchers
                if (
                    "does not exist" in str(e).lower()
                    or "issue does not exist" in str(e).lower()
                ):
                    bot_logger.info(
                        f"Ticket {ticket_id} no longer exists, removing all watchers"
                    )
                    # Get all watchers for cleanup
                    watchers = self.db.get_watchers_for_ticket(ticket_id)
                    for watcher in watchers:
                        self.db.remove_watcher(ticket_id, watcher["user_id"])

        return notifications


class JIRAStatusWorker:
    """Worker that runs JIRA status updates and logs to Discord."""

    def __init__(
        self, discord_client: discord.Client, discord_handler: DiscordLogHandler
    ):
        self.discord_client = discord_client
        self.discord_handler = discord_handler
        self.db_manager = DatabaseManager("jira_watcher.db")
        self.last_backup = None

    async def run_status_update(self):
        """Run the JIRA status update process."""
        start_time = datetime.now()
        logger.info("Starting JIRA status update process")
        logger.info(f"Update initiated at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.debug(
            f"Environment variables loaded - ATLASSIAN_URL: {os.getenv('ATLASSIAN_URL')}"
        )

        try:
            # Initialize clients
            logger.debug("Initializing JIRA and Bitbucket API clients")
            jira = JIRA(
                host=os.getenv("ATLASSIAN_URL"),
                email=os.getenv("ATLASSIAN_EMAIL"),
                token=os.getenv("JIRA_TOKEN"),
            )

            bitbucket = Bitbucket(
                email=os.getenv("ATLASSIAN_EMAIL"),
                token=os.getenv("BITBUCKET_TOKEN"),
                workspace=os.getenv("BITBUCKET_WORKSPACE"),
            )

            logger.info("Successfully initialized JIRA and Bitbucket API clients")
            logger.debug(f"JIRA host: {os.getenv('ATLASSIAN_URL')}")
            logger.debug(f"Bitbucket workspace: {os.getenv('BITBUCKET_WORKSPACE')}")

            # Get repositories from loaded config
            repos = config.get(
                "repositories",
                [
                    "applift-lib",
                    "applift-app",
                    "dsp-customers-web",
                    "dsp-campaign-builder-web",
                    "dsp-audience-builder-web",
                ],
            )

            logger.info(f"Target repositories for monitoring: {', '.join(repos)}")
            logger.debug(f"Total repositories configured: {len(repos)}")

            # Process regular issues
            logger.info("Fetching all open JIRA issues for processing")
            open_issues = jira.get_all_open_issues()
            logger.info(f"Found {len(open_issues)} open issues to process")
            logger.debug(f"Issue keys: {[issue.key for issue in open_issues]}")

            issues_processed = 0
            issues_updated = 0
            worker_changes = []  # Track changes for watch channel alerts
            status_changes = []  # Track all status changes for status channel notifications

            for issue in open_issues:
                try:
                    logger.debug(
                        f"Processing issue {issue.key} - Current status: {issue.fields.status.name}"
                    )
                    # Capture the original status to check if it changed
                    original_status = issue.fields.status.name

                    # Process the issue
                    logger.debug(
                        f"Calling process_issue for {issue.key} with {len(repos)} repositories"
                    )
                    process_issue(jira, bitbucket, issue, repos)

                    # Check if status changed by refetching the issue
                    updated_issue = jira.client.issue(issue.key)
                    new_status = updated_issue.fields.status.name

                    if original_status != new_status:
                        logger.info(
                            f"Status updated for {issue.key}: {original_status} -> {new_status}"
                        )
                        logger.debug(
                            f"Issue {issue.key} assignee: {updated_issue.fields.assignee}"
                        )
                        issues_updated += 1

                        # Add to status changes for general notification
                        status_changes.append({
                            "ticket_id": issue.key,
                            "old_status": original_status,
                            "new_status": new_status,
                            "url": f"{jira.host}/browse/{issue.key}",
                            "type": "issue"
                        })

                        # Check if this ticket is being watched for watch channel alerts
                        watchers = self.db_manager.get_watchers_for_ticket(issue.key)
                        if watchers:
                            logger.debug(
                                f"Issue {issue.key} has {len(watchers)} watchers"
                            )
                            worker_changes.append(
                                {
                                    "ticket_id": issue.key,
                                    "change": f"Status: {original_status} -> {new_status}",
                                    "url": f"{jira.host}/browse/{issue.key}",
                                    "watchers": watchers,
                                }
                            )

                    issues_processed += 1
                    logger.debug(
                        f"Successfully processed issue {issue.key} ({issues_processed}/{len(open_issues)})"
                    )

                except Exception as e:
                    logger.error(f"Error processing issue {issue.key}: {str(e)}")
                    logger.debug(f"Issue processing error details: {e}", exc_info=True)

            # Process bugs
            logger.info("Fetching all open JIRA bugs for processing")
            open_bugs = jira.get_all_open_bugs()
            logger.info(f"Found {len(open_bugs)} open bugs to process")
            logger.debug(f"Bug keys: {[bug.key for bug in open_bugs]}")

            bugs_processed = 0
            bugs_updated = 0

            for bug in open_bugs:
                try:
                    logger.debug(
                        f"Processing bug {bug.key} - Current status: {bug.fields.status.name}"
                    )
                    # Capture the original status to check if it changed
                    original_status = bug.fields.status.name

                    # Process the bug
                    logger.debug(
                        f"Calling process_issue for bug {bug.key} with {len(repos)} repositories"
                    )
                    process_issue(jira, bitbucket, bug, repos)

                    # Check if status changed by refetching the bug
                    updated_bug = jira.client.issue(bug.key)
                    new_status = updated_bug.fields.status.name

                    if original_status != new_status:
                        logger.info(
                            f"Bug status updated for {bug.key}: {original_status} -> {new_status}"
                        )
                        logger.debug(
                            f"Bug {bug.key} assignee: {updated_bug.fields.assignee}"
                        )
                        bugs_updated += 1

                        # Add to status changes for general notification
                        status_changes.append({
                            "ticket_id": bug.key,
                            "old_status": original_status,
                            "new_status": new_status,
                            "url": f"{jira.host}/browse/{bug.key}",
                            "type": "bug"
                        })

                        # Check if this ticket is being watched for watch channel alerts
                        watchers = self.db_manager.get_watchers_for_ticket(bug.key)
                        if watchers:
                            logger.debug(f"Bug {bug.key} has {len(watchers)} watchers")
                            worker_changes.append(
                                {
                                    "ticket_id": bug.key,
                                    "change": f"Status: {original_status} -> {new_status}",
                                    "url": f"{jira.host}/browse/{bug.key}",
                                    "watchers": watchers,
                                }
                            )

                    bugs_processed += 1
                    logger.debug(
                        f"Successfully processed bug {bug.key} ({bugs_processed}/{len(open_bugs)})"
                    )

                except Exception as e:
                    logger.error(f"Error processing bug {bug.key}: {str(e)}")
                    logger.debug(f"Bug processing error details: {e}", exc_info=True)

            # Send worker change alerts to watch channel
            if worker_changes:
                logger.info(
                    f"Sending {len(worker_changes)} change alerts to watch channel"
                )
                await self.send_worker_change_alerts(worker_changes)
            else:
                logger.debug(
                    "No worker changes detected, skipping watch channel alerts"
                )

            # Send status change notifications to status channel
            if status_changes:
                logger.info(
                    f"Sending {len(status_changes)} status change notifications to status channel"
                )
                await self.send_status_change_notifications(status_changes)
            else:
                logger.debug(
                    "No status changes detected, skipping status channel notifications"
                )

            # Summary
            end_time = datetime.now()
            duration = end_time - start_time

            logger.info("JIRA Status Update Summary:")
            logger.info(
                f"   Issues: {issues_processed} processed, {issues_updated} updated"
            )
            logger.info(f"   Bugs: {bugs_processed} processed, {bugs_updated} updated")
            logger.info(f"   Duration: {duration.total_seconds():.2f} seconds")
            logger.info(f"   Start time: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"   End time: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(
                f"   Total tickets processed: {issues_processed + bugs_processed}"
            )
            logger.info(f"   Total tickets updated: {issues_updated + bugs_updated}")
            logger.info("JIRA status update completed successfully")

        except Exception as e:
            logger.error(f"Critical error in status update process: {str(e)}")
            logger.debug("Status update error details:", exc_info=True)
            raise

    async def backup_database_if_needed(self):
        """Backup database if it hasn't been backed up in the last 24 hours."""
        now = datetime.now()
        logger.debug(
            f"Checking if database backup is needed. Last backup: {self.last_backup}"
        )

        # Check if we need to backup (daily)
        if (
            self.last_backup is None or (now - self.last_backup).total_seconds() > 86400
        ):  # 24 hours
            try:
                backup_filename = (
                    f"jira_watcher_backup_{now.strftime('%Y%m%d_%H%M%S')}.db"
                )
                backup_path = os.path.join("backups", backup_filename)
                logger.info(f"Starting database backup to: {backup_path}")

                # Create backups directory if it doesn't exist
                os.makedirs("backups", exist_ok=True)
                logger.debug("Backups directory created/verified")

                # Perform backup
                if self.db_manager.backup_database(backup_path):
                    self.last_backup = now
                    logger.info(f"Database backed up successfully to {backup_path}")
                    logger.debug(
                        f"Backup file size: {os.path.getsize(backup_path)} bytes"
                    )

                    # Clean up old backups (keep only last 7 days)
                    await self.cleanup_old_backups()
                else:
                    logger.error("Database backup operation failed")

            except Exception as e:
                logger.error(f"Error during database backup: {str(e)}")
                logger.debug("Database backup error details:", exc_info=True)
        else:
            time_since_backup = (now - self.last_backup).total_seconds()
            logger.debug(
                f"Backup not needed. Last backup was {time_since_backup:.0f} seconds ago"
            )

    async def check_and_send_due_date_alerts(self):
        """Check for tasks due today or tomorrow and send alerts."""
        try:
            logger.info("Starting due date check for all configured users")

            # Get users from config
            users = config.get("users", [])
            if not users:
                logger.warning(
                    "No users configured in config.json for due date checking"
                )
                return

            # Extract JIRA IDs
            user_jira_ids = [user["jira_id"] for user in users if "jira_id" in user]
            if not user_jira_ids:
                logger.warning("No user JIRA IDs found in config.json")
                return

            logger.debug(f"Checking due dates for {len(user_jira_ids)} users")

            # Initialize JIRA client
            jira_client_for_alerts = JIRA(
                host=os.getenv("ATLASSIAN_URL"),
                email=os.getenv("ATLASSIAN_EMAIL"),
                token=os.getenv("JIRA_TOKEN"),
            )

            # Get due tasks for all users
            due_tasks_by_user = jira_client_for_alerts.get_all_users_tasks_due_soon(
                user_jira_ids
            )

            if due_tasks_by_user:
                total_tasks = sum(len(tasks) for tasks in due_tasks_by_user.values())
                logger.info(
                    f"Found {total_tasks} tasks due today or tomorrow for {len(due_tasks_by_user)} users"
                )

                # Send alerts
                await send_due_date_alerts(due_tasks_by_user, users)
                logger.info("Due date alerts sent successfully")
            else:
                logger.info("No tasks due today or tomorrow found for any user")

        except Exception as e:
            logger.error(f"Error checking due dates: {str(e)}")
            logger.debug("Due date check error details:", exc_info=True)

    async def send_worker_change_alerts(self, worker_changes):
        """Send alerts to watch channel for changes made by the worker."""
        try:
            watch_channel_id = int(os.getenv("WATCH_CHANNEL_ID"))
            watch_channel = self.discord_client.get_channel(watch_channel_id)

            if not watch_channel:
                logger.warning(
                    f"Could not find watch channel with ID {watch_channel_id}"
                )
                return

            for change_data in worker_changes:
                ticket_id = change_data["ticket_id"]
                change = change_data["change"]
                url = change_data["url"]
                watchers = change_data["watchers"]

                # Create user mentions (try to fetch Discord users)
                user_mentions = []
                valid_users = []

                for watcher in watchers:
                    try:
                        user = await self.discord_client.fetch_user(watcher["user_id"])
                        user_mentions.append(f"<@{user.id}>")
                        valid_users.append(user)
                    except discord.NotFound:
                        logger.warning(
                            f"Could not find Discord user {watcher['user_id']}"
                        )
                    except Exception as e:
                        logger.error(
                            f"Error fetching Discord user {watcher['user_id']}: {e}"
                        )

                if not user_mentions:
                    continue  # Skip if no valid users found

                # Create embed for channel
                embed = discord.Embed(
                    title=f"Automated Update: {ticket_id}",
                    description=f"[View Ticket]({url})",
                    color=0x28A745,  # Green color for automated updates
                    timestamp=datetime.now(timezone.utc),
                )

                embed.add_field(
                    name="Automated Change:", value=f"• {change}", inline=False
                )

                # Add watcher info
                watcher_list = ", ".join(
                    [f"{user.display_name}" for user in valid_users]
                )
                embed.add_field(
                    name=f"👥 Watching Users ({len(valid_users)}):",
                    value=watcher_list,
                    inline=False,
                )

                embed.add_field(
                    name="🔧 Update Source:",
                    value="Hourly Worker (based on Git activity)",
                    inline=False,
                )

                embed.set_footer(text="JIRA Automation System")

                # Send message with mentions and embed
                mentions_text = " ".join(user_mentions)
                message_content = f"⚡ **Automated Status Update!** {mentions_text}"

                try:
                    await watch_channel.send(content=message_content, embed=embed)
                    logger.info(
                        f"Sent worker change alert for {ticket_id} to {len(valid_users)} users"
                    )
                except discord.Forbidden:
                    logger.error(
                        f"No permission to send messages to watch channel {watch_channel_id}"
                    )
                except Exception as e:
                    logger.error(f"Error sending worker change alert: {e}")

        except ValueError:
            logger.error("WATCH_CHANNEL_ID is not a valid integer")
        except Exception as e:
            logger.error(f"Error in send_worker_change_alerts: {e}")

    async def send_status_change_notifications(self, status_changes):
        """Send status change notifications to the status change channel."""
        try:
            status_channel_id = int(os.getenv("STATUS_CHANGE_CHANNEL_ID"))
            status_channel = self.discord_client.get_channel(status_channel_id)

            if not status_channel:
                logger.warning(
                    f"Could not find status change channel with ID {status_channel_id}"
                )
                return

            if not status_changes:
                logger.debug("No status changes to notify about")
                return

            # Group changes by type (issues vs bugs)
            issues_changed = [change for change in status_changes if change.get("type") == "issue"]
            bugs_changed = [change for change in status_changes if change.get("type") == "bug"]

            # Create summary embed
            embed = discord.Embed(
                title="🔄 JIRA Status Update Summary",
                color=0x007ACC,  # Blue color for status updates
                timestamp=datetime.now(timezone.utc),
            )

            if issues_changed:
                issues_text = []
                for change in issues_changed[:10]:  # Limit to 10 to avoid message length issues
                    ticket_id = change["ticket_id"]
                    old_status = change["old_status"]
                    new_status = change["new_status"]
                    url = change["url"]
                    issues_text.append(f"• [{ticket_id}]({url}): {old_status} → {new_status}")
                
                if len(issues_changed) > 10:
                    issues_text.append(f"... and {len(issues_changed) - 10} more issues")
                
                embed.add_field(
                    name=f"📋 Issues Updated ({len(issues_changed)}):",
                    value="\n".join(issues_text),
                    inline=False,
                )

            if bugs_changed:
                bugs_text = []
                for change in bugs_changed[:10]:  # Limit to 10 to avoid message length issues
                    ticket_id = change["ticket_id"]
                    old_status = change["old_status"]
                    new_status = change["new_status"]
                    url = change["url"]
                    bugs_text.append(f"• [{ticket_id}]({url}): {old_status} → {new_status}")
                
                if len(bugs_changed) > 10:
                    bugs_text.append(f"... and {len(bugs_changed) - 10} more bugs")
                
                embed.add_field(
                    name=f"🐛 Bugs Updated ({len(bugs_changed)}):",
                    value="\n".join(bugs_text),
                    inline=False,
                )

            # Add summary stats
            total_changes = len(status_changes)
            embed.add_field(
                name="📊 Summary:",
                value=f"Total tickets updated: {total_changes}\nIssues: {len(issues_changed)} | Bugs: {len(bugs_changed)}",
                inline=False,
            )

            embed.add_field(
                name="🤖 Automation:",
                value="Updates triggered by Git activity detection",
                inline=False,
            )

            embed.set_footer(text="JIRA Status Updater Bot")

            try:
                await status_channel.send(embed=embed)
                logger.info(f"Sent status change notification for {total_changes} tickets to status channel")
            except discord.Forbidden:
                logger.error(f"No permission to send messages to status channel {status_channel_id}")
            except Exception as e:
                logger.error(f"Error sending status change notification: {e}")

        except ValueError:
            logger.error("STATUS_CHANGE_CHANNEL_ID is not a valid integer")
        except Exception as e:
            logger.error(f"Error in send_status_change_notifications: {e}")

    async def cleanup_old_backups(self):
        """Remove database backups older than 7 days."""
        try:
            backup_dir = "backups"
            if not os.path.exists(backup_dir):
                return

            cutoff_time = datetime.now().timestamp() - (7 * 24 * 3600)  # 7 days ago
            removed_count = 0

            for filename in os.listdir(backup_dir):
                if filename.startswith("jira_watcher_backup_") and filename.endswith(
                    ".db"
                ):
                    filepath = os.path.join(backup_dir, filename)
                    if os.path.getmtime(filepath) < cutoff_time:
                        os.remove(filepath)
                        removed_count += 1

            if removed_count > 0:
                logger.info(f"Cleaned up {removed_count} old backup files")
                logger.debug(
                    f"Backup cleanup removed files older than 7 days from {backup_dir}"
                )
            else:
                logger.debug("No old backup files found for cleanup")

        except Exception as e:
            logger.error(f"Error cleaning up old backups: {str(e)}")
            logger.debug("Backup cleanup error details:", exc_info=True)

    async def worker_loop(self):
        """Main worker loop that runs at scheduled times and intervals from config."""
        logger.info("Initializing JIRA Status Worker main loop")
        run_times = config.get("run_on", ["1000"])
        status_interval_minutes = config.get("status_updater_interval", 60)
        run_on_interval = config.get("run_status_updater_on_interval", True)

        logger.info("JIRA Status Worker started")
        logger.info(f"Scheduled run times: {', '.join(run_times)}")
        if run_on_interval:
            logger.info(f"Additional runs every {status_interval_minutes} minutes")
        else:
            logger.info("Interval-based updates disabled")
        logger.debug(
            f"Worker configuration - run_times: {run_times}, interval: {status_interval_minutes}, run_on_interval: {run_on_interval}"
        )

        last_scheduled_run = None
        last_interval_run = None
        startup_alerts_sent = False  # Track if startup alerts have been sent

        while True:
            try:
                await self.discord_client.wait_until_ready()
                now = datetime.now()

                # Send due date alerts at startup (only once)
                if not startup_alerts_sent:
                    logger.info("Sending due date alerts at startup")
                    await self.check_and_send_due_date_alerts()
                    startup_alerts_sent = True
                    # Initialize last_alert_sent to prevent immediate duplicate daily alert
                    self.last_alert_sent = now
                    logger.info("Startup due date alerts sent successfully")

                # Check if we should run based on scheduled times
                should_run_scheduled = False
                next_scheduled = get_next_scheduled_run(run_times)

                # Check if it's time for a scheduled run (within 1 minute tolerance)
                for time_str in run_times:
                    try:
                        scheduled_time = parse_time_string(time_str)
                        today_scheduled = datetime.combine(now.date(), scheduled_time)

                        # Check if we're within 1 minute of scheduled time and haven't run today
                        time_diff = abs((now - today_scheduled).total_seconds())
                        if time_diff <= 60 and (
                            last_scheduled_run is None
                            or last_scheduled_run.date() < now.date()
                            or abs(
                                (last_scheduled_run - today_scheduled).total_seconds()
                            )
                            > 300
                        ):
                            should_run_scheduled = True
                            last_scheduled_run = now
                            logger.info(
                                f"Running scheduled update at {now.strftime('%H:%M')}"
                            )
                            logger.debug(
                                f"Scheduled run triggered by time slot: {time_str}"
                            )
                            break
                    except ValueError:
                        continue

                # Check if we should run based on interval (only if enabled)
                should_run_interval = False
                if run_on_interval and (
                    last_interval_run is None
                    or (now - last_interval_run).total_seconds()
                    >= status_interval_minutes * 60
                ):
                    should_run_interval = True
                    last_interval_run = now
                    if not should_run_scheduled:
                        logger.info(
                            f"Running interval update ({status_interval_minutes} min interval)"
                        )
                        logger.debug(
                            f"Interval run triggered - last run was {(now - last_interval_run).total_seconds():.0f} seconds ago"
                        )

                # Run the update if needed
                if should_run_scheduled or should_run_interval:
                    logger.debug("Starting status update and backup sequence")
                    await self.run_status_update()
                    await self.backup_database_if_needed()

                    if self.discord_handler:
                        logger.debug("Sending logs to Discord")
                        await self.discord_handler.send_logs()

                # Check if we should send due date alerts (daily at configured time)
                alert_time_str = config.get("alert_users_at", "1000")
                try:
                    alert_time = parse_time_string(alert_time_str)
                    today_alert_time = datetime.combine(now.date(), alert_time)

                    # Check if we're within 1 minute of alert time and haven't sent daily alerts today
                    alert_time_diff = abs((now - today_alert_time).total_seconds())
                    should_send_daily_alerts = (
                        alert_time_diff <= 60 and
                        startup_alerts_sent and  # Only send daily alerts after startup alerts
                        (not hasattr(self, "last_alert_sent") or 
                         self.last_alert_sent is None or 
                         self.last_alert_sent.date() < now.date() or
                         # Allow daily alert if startup was today but it's now the configured alert time
                         (self.last_alert_sent.date() == now.date() and 
                          abs((self.last_alert_sent - today_alert_time).total_seconds()) > 300))
                    )

                    if should_send_daily_alerts:
                        logger.info(
                            f"Sending daily due date alerts at {now.strftime('%H:%M')}"
                        )
                        await self.check_and_send_due_date_alerts()
                        self.last_alert_sent = now
                        logger.debug(
                            f"Daily due date alerts sent, next alert will be tomorrow at {alert_time_str}"
                        )

                except ValueError as e:
                    logger.error(
                        f"Invalid alert time format '{alert_time_str}' in config: {e}"
                    )
                except Exception as e:
                    logger.error(f"Error checking/sending due date alerts: {e}")
                    logger.debug("Due date alert error details:", exc_info=True)

                # Calculate sleep time until next check (check every minute for scheduled times)
                sleep_time = 60  # Check every minute for precision

                logger.debug(
                    f"Next check in {sleep_time} seconds. Next scheduled: {next_scheduled.strftime('%Y-%m-%d %H:%M')}"
                )
                await asyncio.sleep(sleep_time)

            except Exception as e:
                logger.error(f"Error in worker loop: {str(e)}")
                logger.debug("Worker loop error details:", exc_info=True)

                # Send error logs to Discord
                if self.discord_handler:
                    logger.debug("Sending error logs to Discord")
                    await self.discord_handler.send_logs()

                # Wait 5 minutes before retrying
                logger.info("Error occurred, waiting 5 minutes before retry...")
                logger.debug("Worker entering error recovery sleep for 300 seconds")
                await asyncio.sleep(300)


# Initialize clients
intents = discord.Intents.default()
intents.message_content = True
client = discord.Client(intents=intents)

# Initialize JIRA client
jira_client = JIRA(
    host=os.getenv("ATLASSIAN_URL"),
    email=os.getenv("ATLASSIAN_EMAIL"),
    token=os.getenv("JIRA_TOKEN"),
)

# Initialize database manager
db_manager = DatabaseManager("jira_watcher.db")

# Initialize watcher with database
watcher = JIRAWatcher(jira_client, db_manager)

# Initialize Discord log handler
discord_handler = None

# Initialize worker
worker = None


# Background task for monitoring tickets
async def monitor_tickets():
    """Background task to check for ticket changes using config watch_interval."""
    await client.wait_until_ready()

    watch_interval_minutes = config.get("watch_interval", 5)
    watch_interval_seconds = watch_interval_minutes * 60

    logger.info(
        f"🔍 Starting ticket monitoring with {watch_interval_minutes} minute intervals"
    )

    while not client.is_closed():
        try:
            notifications = await watcher.check_for_changes(client)

            # Group notifications by ticket for channel alerts
            ticket_notifications = {}

            for notification in notifications:
                user = notification["user"]
                ticket_id = notification["ticket_id"]
                changes = notification["changes"]
                url = notification["url"]

                # Send DM to individual user
                embed = discord.Embed(
                    title=f"🔔 Changes detected in {ticket_id}",
                    description=f"[View Ticket]({url})",
                    color=0x0099FF,
                    timestamp=datetime.now(timezone.utc),
                )

                changes_text = "\n".join([f"• {change}" for change in changes])
                embed.add_field(name="Changes:", value=changes_text, inline=False)

                try:
                    await user.send(embed=embed)
                except discord.Forbidden:
                    bot_logger.warning(
                        f"Could not send DM to {user.name}#{user.discriminator}"
                    )

                # Group notifications for channel alert
                if ticket_id not in ticket_notifications:
                    ticket_notifications[ticket_id] = {
                        "changes": changes,
                        "url": url,
                        "users": [],
                    }
                ticket_notifications[ticket_id]["users"].append(user)

            # Send alerts to watch channel
            if ticket_notifications:
                await send_watch_channel_alerts(ticket_notifications)

        except Exception as e:
            bot_logger.error(f"Error in monitor_tickets: {e}")

        # Wait for configured interval before next check
        logger.debug(
            f"⏳ Waiting {watch_interval_minutes} minutes until next ticket check..."
        )
        await asyncio.sleep(watch_interval_seconds)


async def send_watch_channel_alerts(ticket_notifications):
    """Send alerts to the watch channel for ticket changes."""
    try:
        watch_channel_id = int(os.getenv("WATCH_CHANNEL_ID"))
        watch_channel = client.get_channel(watch_channel_id)

        if not watch_channel:
            bot_logger.warning(
                f"Could not find watch channel with ID {watch_channel_id}"
            )
            return

        for ticket_id, notification_data in ticket_notifications.items():
            changes = notification_data["changes"]
            url = notification_data["url"]
            users = notification_data["users"]

            # Create user mentions
            user_mentions = " ".join([f"<@{user.id}>" for user in users])

            # Create embed for channel
            embed = discord.Embed(
                title=f"🚨 Ticket Update Alert: {ticket_id}",
                description=f"[View Ticket]({url})",
                color=0xFF6B35,  # Orange color for alerts
                timestamp=datetime.now(timezone.utc),
            )

            changes_text = "\n".join([f"• {change}" for change in changes])
            embed.add_field(
                name="📋 Changes Detected:", value=changes_text, inline=False
            )

            # Add watcher info
            watcher_list = ", ".join([f"{user.display_name}" for user in users])
            embed.add_field(
                name=f"👥 Watching Users ({len(users)}):",
                value=watcher_list,
                inline=False,
            )

            embed.set_footer(text="JIRA Watcher System")

            # Send message with mentions and embed
            message_content = f"🔔 **Ticket Status Changed!** {user_mentions}"

            try:
                await watch_channel.send(content=message_content, embed=embed)
                bot_logger.info(
                    f"Sent watch channel alert for {ticket_id} to {len(users)} users"
                )
            except discord.Forbidden:
                bot_logger.error(
                    f"No permission to send messages to watch channel {watch_channel_id}"
                )
            except Exception as e:
                bot_logger.error(f"Error sending watch channel alert: {e}")

    except ValueError:
        bot_logger.error("WATCH_CHANNEL_ID is not a valid integer")
    except Exception as e:
        bot_logger.error(f"Error in send_watch_channel_alerts: {e}")


async def send_due_date_alerts(due_tasks_by_user, user_config):
    """Send alerts to the alerts channel for tasks due today or tomorrow."""
    try:
        alerts_channel_id = int(os.getenv("ALERTS_CHANNEL_ID"))
        alerts_channel = client.get_channel(alerts_channel_id)

        if not alerts_channel:
            bot_logger.warning(
                f"Could not find alerts channel with ID {alerts_channel_id}"
            )
            return

        # Create a mapping of jira_id to user name for better display
        user_names = {user["jira_id"]: user["name"] for user in user_config}

        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)

        for user_jira_id, tasks in due_tasks_by_user.items():
            user_name = user_names.get(user_jira_id, user_jira_id)

            # Separate tasks by due date
            today_tasks = []
            tomorrow_tasks = []

            for task in tasks:
                due_date_str = task.fields.duedate
                if due_date_str:
                    due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
                    if due_date == today:
                        today_tasks.append(task)
                    elif due_date == tomorrow:
                        tomorrow_tasks.append(task)

            if not today_tasks and not tomorrow_tasks:
                continue

            # Create embed for due date alerts
            embed = discord.Embed(
                title=f"📅 Due Date Alert for {user_name}",
                color=0xFF4444,  # Red color for urgent alerts
                timestamp=datetime.now(timezone.utc),
            )

            # Add today's tasks
            if today_tasks:
                today_text = []
                for task in today_tasks:
                    priority = (
                        getattr(task.fields.priority, "name", "None")
                        if task.fields.priority
                        else "None"
                    )
                    task_url = f"{os.getenv('ATLASSIAN_URL')}browse/{task.key}"
                    today_text.append(
                        f"• [{task.key}]({task_url}) - {task.fields.summary[:60]}{'...' if len(task.fields.summary) > 60 else ''} (Priority: {priority})"
                    )

                embed.add_field(
                    name=f"🚨 Due TODAY ({len(today_tasks)} task{'s' if len(today_tasks) != 1 else ''}):",
                    value="\n".join(today_text[:5])
                    + ("\n..." if len(today_text) > 5 else ""),
                    inline=False,
                )

            # Add tomorrow's tasks
            if tomorrow_tasks:
                tomorrow_text = []
                for task in tomorrow_tasks:
                    priority = (
                        getattr(task.fields.priority, "name", "None")
                        if task.fields.priority
                        else "None"
                    )
                    task_url = f"{os.getenv('ATLASSIAN_URL')}browse/{task.key}"
                    tomorrow_text.append(
                        f"• [{task.key}]({task_url}) - {task.fields.summary[:60]}{'...' if len(task.fields.summary) > 60 else ''} (Priority: {priority})"
                    )

                embed.add_field(
                    name=f"⚠️ Due TOMORROW ({len(tomorrow_tasks)} task{'s' if len(tomorrow_tasks) != 1 else ''}):",
                    value="\n".join(tomorrow_text[:5])
                    + ("\n..." if len(tomorrow_text) > 5 else ""),
                    inline=False,
                )

            embed.add_field(
                name="💡 Tip:",
                value="Check your task priorities and plan your day accordingly!",
                inline=False,
            )

            embed.set_footer(text="JIRA Due Date Reminder System")

            try:
                await alerts_channel.send(embed=embed)
                bot_logger.info(
                    f"Sent due date alert for {user_name} ({len(today_tasks)} today, {len(tomorrow_tasks)} tomorrow)"
                )
            except discord.Forbidden:
                bot_logger.error(
                    f"No permission to send messages to alerts channel {alerts_channel_id}"
                )
            except Exception as e:
                bot_logger.error(f"Error sending due date alert for {user_name}: {e}")

    except ValueError:
        bot_logger.error("ALERTS_CHANNEL_ID is not a valid integer")
    except Exception as e:
        bot_logger.error(f"Error in send_due_date_alerts: {e}")


@client.event
async def on_ready():
    global discord_handler, worker

    print(f"{client.user} has awakened!")

    # Setup Discord logging handler
    logs_channel_id = int(os.getenv("LOGS_CHANNEL_ID"))
    discord_handler = DiscordLogHandler(client, logs_channel_id)

    # Set up formatter
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    discord_handler.setFormatter(formatter)

    # Add handler to root logger
    root_logger = logging.getLogger()
    root_logger.addHandler(discord_handler)
    root_logger.setLevel(logging.INFO)

    # Initialize worker with Discord client
    worker = JIRAStatusWorker(client, discord_handler)

    # Start the monitoring and worker tasks
    client.loop.create_task(monitor_tickets())
    client.loop.create_task(worker.worker_loop())


@client.event
async def on_message(message):
    if message.author == client.user:
        return

    content = message.content.strip()

    if content.startswith("/hello"):
        await message.channel.send("Hello!")

    elif content.startswith("/ping"):
        latency_ms = round(client.latency * 1000, 2)
        await message.channel.send(f"Pong! 🏓 Latency: {latency_ms}ms")

    elif content.startswith("/watch"):
        parts = content.split()
        if len(parts) != 2:
            await message.channel.send(
                "❌ Usage: `/watch <ticket-id>`\nExample: `/watch ABC-123`"
            )
            return

        ticket_id = parts[1].upper()

        # Validate ticket format (basic check)
        if "-" not in ticket_id:
            await message.channel.send(
                "❌ Invalid ticket format. Use format like: ABC-123"
            )
            return

        # Try to add watcher
        success = watcher.add_watcher(ticket_id, message.author)

        if success:
            embed = discord.Embed(
                title="✅ Watching ticket",
                description=f"You are now watching **{ticket_id}** for changes.",
                color=0x00FF00,
            )
            embed.add_field(
                name="What you'll be notified about:",
                value="• Status changes\n• Summary changes\n• Description changes\n• Assignee changes",
                inline=False,
            )
            embed.add_field(
                name="How to stop watching:",
                value=f"`/unwatch {ticket_id}`",
                inline=False,
            )
            await message.channel.send(embed=embed)
        else:
            await message.channel.send(
                f"❌ Could not watch ticket **{ticket_id}**. Please check if the ticket exists and try again."
            )

    elif content.startswith("/unwatch"):
        parts = content.split()
        if len(parts) != 2:
            await message.channel.send(
                "❌ Usage: `/unwatch <ticket-id>`\nExample: `/unwatch ABC-123`"
            )
            return

        ticket_id = parts[1].upper()
        success = watcher.remove_watcher(ticket_id, message.author.id)

        if success:
            await message.channel.send(
                f"✅ You are no longer watching **{ticket_id}**."
            )
        else:
            await message.channel.send(f"❌ You were not watching **{ticket_id}**.")

    elif content.startswith("/list"):
        watched_tickets = watcher.get_watched_tickets_for_user(message.author.id)

        if not watched_tickets:
            await message.channel.send("📝 You are not watching any tickets.")
        else:
            embed = discord.Embed(
                title="📋 Your watched tickets",
                description=f"You are watching {len(watched_tickets)} ticket(s):",
                color=0x0099FF,
            )

            tickets_text = "\n".join(
                [
                    f"• [{ticket}]({jira_client.host}/browse/{ticket})"
                    for ticket in watched_tickets
                ]
            )
            embed.add_field(name="Tickets:", value=tickets_text, inline=False)
            await message.channel.send(embed=embed)

    elif content.startswith("/stats"):
        # Only allow this command in certain channels or for admins if you want
        stats = db_manager.get_database_stats()

        embed = discord.Embed(
            title="📊 Database Statistics",
            description="Current system statistics",
            color=0x9932CC,
        )

        embed.add_field(
            name="👥 Total Watchers", value=stats["total_watchers"], inline=True
        )
        embed.add_field(
            name="🆔 Unique Users", value=stats["unique_users"], inline=True
        )
        embed.add_field(
            name="🎫 Watched Tickets", value=stats["watched_tickets"], inline=True
        )
        embed.add_field(name="📸 Snapshots", value=stats["snapshots"], inline=True)

        await message.channel.send(embed=embed)

    elif content.startswith("/test-alert"):
        # Test command to verify watch channel functionality
        if not message.author.guild_permissions.administrator:
            await message.channel.send(
                "❌ This command is only available to administrators."
            )
            return

        try:
            watch_channel_id = int(os.getenv("WATCH_CHANNEL_ID"))
            watch_channel = client.get_channel(watch_channel_id)

            if not watch_channel:
                await message.channel.send(
                    f"❌ Could not find watch channel with ID {watch_channel_id}"
                )
                return

            # Create test embed
            embed = discord.Embed(
                title="🧪 Test Alert: SAMPLE-123",
                description="[View Ticket](https://example.atlassian.net/browse/SAMPLE-123)",
                color=0x9932CC,  # Purple for test
                timestamp=datetime.now(timezone.utc),
            )

            embed.add_field(
                name="📋 Test Change:",
                value="• Status: In Progress → Done",
                inline=False,
            )
            embed.add_field(
                name="👥 Test User:", value=message.author.display_name, inline=False
            )
            embed.set_footer(text="Test Alert - JIRA Watcher System")

            # Send test message
            test_content = f"🧪 **Test Alert!** <@{message.author.id}>"

            await watch_channel.send(content=test_content, embed=embed)
            await message.channel.send(f"✅ Test alert sent to {watch_channel.mention}")

        except ValueError:
            await message.channel.send("❌ WATCH_CHANNEL_ID is not a valid integer")
        except Exception as e:
            await message.channel.send(f"❌ Error sending test alert: {e}")

    elif content.startswith("/help"):
        embed = discord.Embed(
            title="🤖 JIRA Watcher Bot Commands",
            description="Monitor your JIRA tickets for changes!",
            color=0x0099FF,
        )

        commands = [
            ("`/ping`", "Check bot latency"),
            ("`/watch <ticket-id>`", "Start watching a JIRA ticket for changes"),
            ("`/unwatch <ticket-id>`", "Stop watching a JIRA ticket"),
            ("`/list`", "List all tickets you're currently watching"),
            ("`/stats`", "Show database statistics"),
            ("`/test-alert`", "Send a test alert to watch channel (Admin only)"),
            ("`/help`", "Show this help message"),
        ]

        for command, description in commands:
            embed.add_field(name=command, value=description, inline=False)

        embed.add_field(
            name="📢 Notifications",
            value="You'll receive a DM when watched tickets change (status, summary, description, or assignee).",
            inline=False,
        )

        await message.channel.send(embed=embed)


def main():
    """Main function to start both Discord bot and worker."""
    logger.info("Starting Auto JIRA Status Updater System")
    logger.info("Discord Bot + Hourly Worker Integration")
    logger.debug("Main function initialization started")

    # Check if .env file exists
    if not os.path.exists(".env"):
        logger.error(
            ".env file not found! Please create a .env file with your credentials."
        )
        logger.error("See README.md for required environment variables.")
        return

    # Check required environment variables
    required_vars = [
        "ATLASSIAN_URL",
        "ATLASSIAN_EMAIL",
        "JIRA_TOKEN",
        "BITBUCKET_TOKEN",
        "BITBUCKET_WORKSPACE",
        "DISCORD_BOT_TOKEN",
        "LOGS_CHANNEL_ID",
        "WATCH_CHANNEL_ID",
    ]

    missing_vars = [var for var in required_vars if not os.getenv(var)]
    if missing_vars:
        logger.error(
            f"Missing required environment variables: {', '.join(missing_vars)}"
        )
        return

    logger.info("Environment variables loaded successfully")
    logger.info("Starting Discord Bot with integrated worker")
    logger.info("Bot Commands: /ping, /watch, /unwatch, /list, /stats, /help")

    # Display configuration information
    run_times = config.get("run_on", ["1000"])
    watch_interval = config.get("watch_interval", 5)
    status_interval = config.get("status_updater_interval", 60)

    logger.info(f"Worker scheduled times: {', '.join(run_times)}")
    logger.info(f"Additional status updates every {status_interval} minutes")
    logger.info(f"Ticket monitoring every {watch_interval} minutes")
    logger.info("Database backups will be created daily")
    logger.debug(
        f"Configuration loaded - run_times: {run_times}, watch_interval: {watch_interval}, status_interval: {status_interval}"
    )

    try:
        logger.info("Starting Discord bot client")
        client.run(os.getenv("DISCORD_BOT_TOKEN"))
    except KeyboardInterrupt:
        logger.info("System stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        logger.debug("Main function error details:", exc_info=True)


if __name__ == "__main__":
    main()
