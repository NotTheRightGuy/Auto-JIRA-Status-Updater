from dotenv import load_dotenv

load_dotenv()
import discord
from discord.ext import commands
from discord import app_commands
import os
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Set
import sys

# Add the parent directory to the path to import our utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from utils.jira import JIRA
from utils.database import DatabaseManager, TicketSnapshot

# Set up logging
logger = logging.getLogger(__name__)


class JIRAWatcher:
    """Manages JIRA ticket watching and change detection using SQLite."""

    def __init__(self, jira_client: JIRA, db_manager: DatabaseManager):
        self.jira = jira_client
        self.db = db_manager

    def add_watcher(self, ticket_id: str, user: discord.User) -> bool:
        """Add a user to watch a specific ticket."""
        logger.debug(
            f"Attempting to add watcher for ticket {ticket_id} by user {user.id}"
        )
        # First, try to fetch the ticket to validate it exists
        try:
            issue = self.jira.client.issue(ticket_id)
            logger.debug(
                f"Successfully fetched JIRA issue {ticket_id}: {issue.fields.summary}"
            )
            snapshot = TicketSnapshot.from_jira_issue(issue)

            # Save the initial snapshot
            self.db.save_ticket_snapshot(snapshot)
            logger.debug(f"Saved initial snapshot for ticket {ticket_id}")

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
                logger.info(
                    f"Successfully added watcher for {ticket_id}: {user.name} (ID: {user.id})"
                )
                logger.debug(
                    f"Watcher details - username: {user.name}, discriminator: {user.discriminator if hasattr(user, 'discriminator') else '0000'}"
                )
            else:
                logger.warning(
                    f"Failed to add watcher for {ticket_id}: database operation failed"
                )

            return success

        except Exception as e:
            logger.error(f"Failed to add watcher for {ticket_id}: {str(e)}")
            logger.debug(
                f"Add watcher error details for user {user.id}:", exc_info=True
            )
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

        logger.debug(f"Checking {len(watched_tickets)} watched tickets for changes")

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
                        logger.info(f"Changes detected in {ticket_id}: {changes}")

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
                                logger.warning(
                                    f"Could not find Discord user {watcher['user_id']}"
                                )
                            except Exception as e:
                                logger.error(
                                    f"Error fetching Discord user {watcher['user_id']}: {e}"
                                )

                # Update snapshot regardless of changes
                self.db.save_ticket_snapshot(current_snapshot)

            except Exception as e:
                logger.error(f"Error checking ticket {ticket_id}: {e}")

                # If ticket doesn't exist anymore, clean up watchers
                if (
                    "does not exist" in str(e).lower()
                    or "issue does not exist" in str(e).lower()
                ):
                    logger.info(
                        f"Ticket {ticket_id} no longer exists, removing all watchers"
                    )
                    # Get all watchers for cleanup
                    watchers = self.db.get_watchers_for_ticket(ticket_id)
                    for watcher in watchers:
                        self.db.remove_watcher(ticket_id, watcher["user_id"])

        return notifications


# Initialize clients
intents = discord.Intents.default()
intents.message_content = True


class JIRAWatcherBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # Sync the command tree
        try:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} command(s)")
        except Exception as e:
            print(f"Failed to sync commands: {e}")


bot = JIRAWatcherBot()

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


# Background task for monitoring
async def monitor_tickets():
    """Background task to check for ticket changes every 5 minutes."""
    await bot.wait_until_ready()

    while not bot.is_closed():
        try:
            notifications = await watcher.check_for_changes(bot)

            for notification in notifications:
                user = notification["user"]
                ticket_id = notification["ticket_id"]
                changes = notification["changes"]
                url = notification["url"]

                embed = discord.Embed(
                    title=f"🔔 Changes detected in {ticket_id}",
                    description=f"[View Ticket]({url})",
                    color=0x0099FF,
                    timestamp=datetime.utcnow(),
                )

                changes_text = "\n".join([f"• {change}" for change in changes])
                embed.add_field(name="Changes:", value=changes_text, inline=False)

                try:
                    await user.send(embed=embed)
                except discord.Forbidden:
                    logging.warning(
                        f"Could not send DM to {user.name}#{user.discriminator}"
                    )

        except Exception as e:
            logging.error(f"Error in monitor_tickets: {e}")

        # Wait 5 minutes before next check
        await asyncio.sleep(300)


@bot.event
async def on_ready():
    logger.info(f"Discord bot {bot.user} has connected successfully")
    logger.info("Syncing slash commands")

    try:
        # Sync commands globally
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} slash command(s) globally")

        # List the synced commands
        for command in synced:
            logger.debug(f"Synced command: /{command.name}: {command.description}")

    except Exception as e:
        logger.error(f"Failed to sync commands: {str(e)}")
        logger.debug("Command sync error details:", exc_info=True)

    # Start the monitoring task
    logger.info("Starting ticket monitoring background task")
    bot.loop.create_task(monitor_tickets())
    logger.info("Bot is ready and all systems operational!")


@bot.tree.command(name="ping", description="Check bot latency")
async def ping(interaction: discord.Interaction):
    latency_ms = round(bot.latency * 1000, 2)
    await interaction.response.send_message(f"Pong! 🏓 Latency: {latency_ms}ms")


@bot.tree.command(name="watch", description="Start watching a JIRA ticket for changes")
@app_commands.describe(ticket_id="The JIRA ticket ID to watch (e.g., ABC-123)")
async def watch_ticket(interaction: discord.Interaction, ticket_id: str):
    ticket_id = ticket_id.upper()
    logger.info(
        f"User {interaction.user.id} ({interaction.user.name}) attempting to watch ticket {ticket_id}"
    )

    # Validate ticket format (basic check)
    if "-" not in ticket_id:
        logger.warning(
            f"Invalid ticket format provided by user {interaction.user.id}: {ticket_id}"
        )
        await interaction.response.send_message(
            "Invalid ticket format. Use format like: ABC-123", ephemeral=True
        )
        return

    # Try to add watcher
    success = watcher.add_watcher(ticket_id, interaction.user)

    if success:
        logger.info(
            f"Successfully added watcher for {ticket_id} by user {interaction.user.id}"
        )
        embed = discord.Embed(
            title="Watching ticket",
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
        await interaction.response.send_message(embed=embed)
    else:
        logger.warning(
            f"Failed to add watcher for {ticket_id} by user {interaction.user.id}"
        )
        await interaction.response.send_message(
            f"Could not watch ticket **{ticket_id}**. Please check if the ticket exists and try again.",
            ephemeral=True,
        )


@bot.tree.command(name="unwatch", description="Stop watching a JIRA ticket")
@app_commands.describe(ticket_id="The JIRA ticket ID to stop watching")
async def unwatch_ticket(interaction: discord.Interaction, ticket_id: str):
    ticket_id = ticket_id.upper()
    logger.info(
        f"User {interaction.user.id} ({interaction.user.name}) attempting to unwatch ticket {ticket_id}"
    )
    success = watcher.remove_watcher(ticket_id, interaction.user.id)

    if success:
        logger.info(
            f"Successfully removed watcher for {ticket_id} by user {interaction.user.id}"
        )
        await interaction.response.send_message(
            f"You are no longer watching **{ticket_id}**."
        )
    else:
        logger.info(f"User {interaction.user.id} was not watching {ticket_id}")
        await interaction.response.send_message(
            f"You were not watching **{ticket_id}**.", ephemeral=True
        )


@bot.tree.command(name="list", description="List all tickets you're currently watching")
async def list_tickets(interaction: discord.Interaction):
    logger.info(
        f"User {interaction.user.id} ({interaction.user.name}) requested list of watched tickets"
    )
    watched_tickets = watcher.get_watched_tickets_for_user(interaction.user.id)

    if not watched_tickets:
        logger.debug(f"User {interaction.user.id} is not watching any tickets")
        await interaction.response.send_message(
            "You are not watching any tickets.", ephemeral=True
        )
    else:
        logger.debug(
            f"User {interaction.user.id} is watching {len(watched_tickets)} tickets: {watched_tickets}"
        )
        embed = discord.Embed(
            title="Your watched tickets",
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
        await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="stats", description="Show database statistics")
async def show_stats(interaction: discord.Interaction):
    stats = db_manager.get_database_stats()

    embed = discord.Embed(
        title="📊 Database Statistics",
        description="Current system statistics",
        color=0x9932CC,
    )

    embed.add_field(
        name="👥 Total Watchers", value=stats["total_watchers"], inline=True
    )
    embed.add_field(name="🆔 Unique Users", value=stats["unique_users"], inline=True)
    embed.add_field(
        name="🎫 Watched Tickets", value=stats["watched_tickets"], inline=True
    )
    embed.add_field(name="📸 Snapshots", value=stats["snapshots"], inline=True)

    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="help", description="Show help information about bot commands")
async def help_command(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤖 JIRA Watcher Bot Commands",
        description="Monitor your JIRA tickets for changes!",
        color=0x0099FF,
    )

    commands_info = [
        ("</ping:0>", "Check bot latency"),
        ("</watch:0>", "Start watching a JIRA ticket for changes"),
        ("</unwatch:0>", "Stop watching a JIRA ticket"),
        ("</list:0>", "List all tickets you're currently watching"),
        ("</stats:0>", "Show database statistics"),
        ("</help:0>", "Show this help message"),
    ]

    for command, description in commands_info:
        embed.add_field(name=command, value=description, inline=False)

    embed.add_field(
        name="📢 Notifications",
        value="You'll receive a DM when watched tickets change (status, summary, description, or assignee).",
        inline=False,
    )

    await interaction.response.send_message(embed=embed, ephemeral=True)


bot.run(os.getenv("DISCORD_BOT_TOKEN"))
