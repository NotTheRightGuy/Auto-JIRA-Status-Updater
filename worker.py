import logging
import os
import asyncio
import discord
from datetime import datetime
from dotenv import load_dotenv
from utils.jira import JIRA
from utils.bitbucket import Bitbucket
from logs.logger import logger
from utils.helper import process_issue
from utils.database import DatabaseManager

import json

load_dotenv()


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


class JIRAStatusWorker:
    """Worker that runs JIRA status updates and logs to Discord."""

    def __init__(self):
        self.discord_client = None
        self.discord_handler = None
        self.is_running = False
        self.db_manager = DatabaseManager("jira_watcher.db")
        self.last_backup = None

    async def setup_discord(self):
        """Setup Discord client for logging."""
        intents = discord.Intents.default()
        self.discord_client = discord.Client(intents=intents)

        @self.discord_client.event
        async def on_ready():
            logger.info(f"Worker Discord client ready: {self.discord_client.user}")

            # Setup Discord logging handler
            logs_channel_id = int(os.getenv("LOGS_CHANNEL_ID"))
            self.discord_handler = DiscordLogHandler(
                self.discord_client, logs_channel_id
            )
            logger.debug(
                f"Discord logging handler configured for channel {logs_channel_id}"
            )

            # Set up formatter
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            self.discord_handler.setFormatter(formatter)

            # Add handler to root logger
            root_logger = logging.getLogger()
            root_logger.addHandler(self.discord_handler)
            logger.debug("Discord handler added to root logger")
            root_logger.setLevel(logging.INFO)

            # Start the worker loop
            self.discord_client.loop.create_task(self.worker_loop())

        # Start Discord client in background
        await self.discord_client.login(os.getenv("DISCORD_BOT_TOKEN"))
        await self.discord_client.connect()

    async def run_status_update(self):
        """Run the JIRA status update process."""
        start_time = datetime.now()
        logger.info("Starting JIRA status update process")
        logger.info(f"Update initiated at: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")

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

            # Read repositories from config.json
            logger.debug("Loading repository configuration from config.json")

            try:
                with open("config.json", "r") as config_file:
                    config = json.load(config_file)
                    repos = config.get("repositories", [])
                    if not repos:
                        logger.warning(
                            "No repositories found in config.json, using default list"
                        )
                        repos = [
                            "applift-lib",
                            "applift-app",
                            "dsp-customers-web",
                            "dsp-campaign-builder-web",
                            "dsp-audience-builder-web",
                        ]
                    else:
                        logger.debug(
                            f"Loaded {len(repos)} repositories from config: {repos}"
                        )
            except FileNotFoundError:
                logger.error("config.json file not found, using default repositories")
                repos = [
                    "applift-lib",
                    "applift-app",
                    "dsp-customers-web",
                    "dsp-campaign-builder-web",
                    "dsp-audience-builder-web",
                ]
            except json.JSONDecodeError as e:
                logger.error(
                    f"Error parsing config.json: {str(e)}, using default repositories"
                )
                repos = [
                    "applift-lib",
                    "applift-app",
                    "dsp-customers-web",
                    "dsp-campaign-builder-web",
                    "dsp-audience-builder-web",
                ]

            logger.info(f"Target repositories for monitoring: {', '.join(repos)}")

            # Process regular issues
            logger.info("Fetching all open JIRA issues for processing")
            open_issues = jira.get_all_open_issues()
            logger.info(f"Found {len(open_issues)} open issues to process")

            issues_processed = 0
            issues_updated = 0

            for issue in open_issues:
                try:
                    # Capture the original status to check if it changed
                    original_status = issue.fields.status.name

                    # Process the issue
                    process_issue(jira, bitbucket, issue, repos)

                    # Check if status changed by refetching the issue
                    updated_issue = jira.client.issue(issue.key)
                    new_status = updated_issue.fields.status.name

                    if original_status != new_status:
                        logger.info(
                            f"Status updated for {issue.key}: {original_status} -> {new_status}"
                        )
                        issues_updated += 1

                    issues_processed += 1

                except Exception as e:
                    logger.error(f"Error processing issue {issue.key}: {str(e)}")

            # Process bugs
            open_bugs = jira.get_all_open_bugs()
            logger.info(f"Found {len(open_bugs)} open bugs to process")

            bugs_processed = 0
            bugs_updated = 0

            for bug in open_bugs:
                try:
                    # Capture the original status to check if it changed
                    original_status = bug.fields.status.name

                    # Process the bug
                    process_issue(jira, bitbucket, bug, repos)

                    # Check if status changed by refetching the bug
                    updated_bug = jira.client.issue(bug.key)
                    new_status = updated_bug.fields.status.name

                    if original_status != new_status:
                        logger.info(
                            f"Bug status updated for {bug.key}: {original_status} -> {new_status}"
                        )
                        bugs_updated += 1

                    bugs_processed += 1

                except Exception as e:
                    logger.error(f"Error processing bug {bug.key}: {str(e)}")

            # Summary
            end_time = datetime.now()
            duration = end_time - start_time

            logger.info("JIRA Status Update Summary:")
            logger.info(
                f"   Issues: {issues_processed} processed, {issues_updated} updated"
            )
            logger.info(f"   Bugs: {bugs_processed} processed, {bugs_updated} updated")
            logger.info(f"   Duration: {duration.total_seconds():.2f} seconds")
            logger.info("JIRA status update completed successfully")

        except Exception as e:
            logger.error(f"Critical error in status update process: {str(e)}")
            raise

    async def worker_loop(self):
        """Main worker loop that runs based on configuration."""
        logger.info("JIRA Status Worker started")

        # Load configuration to check if interval updates are enabled
        try:
            with open("config.json", "r") as config_file:
                config = json.load(config_file)
                run_on_interval = config.get("run_status_updater_on_interval", True)
                interval_minutes = config.get("status_updater_interval", 60)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Could not load config.json: {e}, using defaults")
            run_on_interval = True
            interval_minutes = 60

        if run_on_interval:
            logger.info(f"Worker will run every {interval_minutes} minutes")
        else:
            logger.info("Interval-based updates are disabled - worker will not run")
            return

        while True:
            try:
                # Wait until we're ready
                await self.discord_client.wait_until_ready()

                # Run the status update
                await self.run_status_update()

                # Backup database daily (check if it's been more than 24 hours)
                await self.backup_database_if_needed()

                # Send logs to Discord
                if self.discord_handler:
                    await self.discord_handler.send_logs()

                # Wait for the configured interval
                sleep_seconds = interval_minutes * 60
                logger.info(f"Waiting {interval_minutes} minutes until next run...")
                await asyncio.sleep(sleep_seconds)

            except Exception as e:
                logger.error(f"Error in worker loop: {str(e)}")

                # Send error logs to Discord
                if self.discord_handler:
                    await self.discord_handler.send_logs()

                # Wait 5 minutes before retrying
                logger.info("Error occurred, waiting 5 minutes before retry...")
                await asyncio.sleep(300)

    async def backup_database_if_needed(self):
        """Backup database if it hasn't been backed up in the last 24 hours."""
        now = datetime.now()

        # Check if we need to backup (daily)
        if (
            self.last_backup is None or (now - self.last_backup).total_seconds() > 86400
        ):  # 24 hours
            try:
                backup_filename = (
                    f"jira_watcher_backup_{now.strftime('%Y%m%d_%H%M%S')}.db"
                )
                backup_path = os.path.join("backups", backup_filename)

                # Create backups directory if it doesn't exist
                os.makedirs("backups", exist_ok=True)

                # Perform backup
                if self.db_manager.backup_database(backup_path):
                    self.last_backup = now
                    logger.info(f"Database backed up successfully to {backup_path}")

                    # Clean up old backups (keep only last 7 days)
                    await self.cleanup_old_backups()
                else:
                    logger.error("Database backup failed")

            except Exception as e:
                logger.error(f"Error during database backup: {str(e)}")

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

        except Exception as e:
            logger.error(f"Error cleaning up old backups: {str(e)}")


async def main():
    """Main function to start the worker."""
    worker = JIRAStatusWorker()

    try:
        await worker.setup_discord()
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
    finally:
        if worker.discord_client:
            await worker.discord_client.close()


if __name__ == "__main__":
    asyncio.run(main())
