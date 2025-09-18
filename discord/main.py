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
from services.jira import JIRAWatcher, JIRAWatcherBot

# Add the parent directory to the path to import our utils
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from services.jira import JIRA
from services.database import DatabaseManager, TicketSnapshot
from utils.helper import parse_reminder_date

# Set up logging
logger = logging.getLogger(__name__)


# Initialize clients
intents = discord.Intents.default()
intents.message_content = True

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
            logger.info("Starting ticket monitoring cycle")
            start_time = asyncio.get_event_loop().time()

            # Use asyncio.wait_for to timeout the entire monitoring cycle
            notifications = await asyncio.wait_for(
                watcher.check_for_changes(bot),
                timeout=120.0,  # 2 minute timeout for entire monitoring cycle
            )

            # Process notifications
            notification_count = 0
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
                    notification_count += 1
                except discord.Forbidden:
                    logger.warning(f"Could not send DM to {user.name} (ID: {user.id})")
                except Exception as e:
                    logger.error(f"Error sending notification to {user.name}: {e}")

            elapsed_time = asyncio.get_event_loop().time() - start_time
            logger.info(
                f"Monitoring cycle completed in {elapsed_time:.2f}s, sent {notification_count} notifications"
            )

        except asyncio.TimeoutError:
            logger.error("Monitoring cycle timed out after 2 minutes")
        except Exception as e:
            logger.error(f"Error in monitor_tickets: {e}")

        # Wait 5 minutes before next check, but allow for graceful shutdown
        try:
            await asyncio.sleep(300)  # 5 minutes
        except asyncio.CancelledError:
            logger.info("Monitoring task cancelled")
            break


# Background task for checking reminders
async def check_reminders():
    """Background task to check for due reminders every minute."""
    await bot.wait_until_ready()

    while not bot.is_closed():
        try:
            logger.debug("Checking for due reminders")
            due_reminders = db_manager.get_due_reminders()

            for reminder in due_reminders:
                try:
                    # Get the reminder channel
                    channel = bot.get_channel(reminder["channel_id"])
                    if not channel:
                        logger.warning(
                            f"Could not find channel {reminder['channel_id']} for reminder"
                        )
                        continue

                    # Create reminder embed
                    embed = discord.Embed(
                        title="⏰ Reminder",
                        description=reminder["message"],
                        color=0xFFD700,
                        timestamp=datetime.utcnow(),
                    )
                    embed.add_field(
                        name="For:", value=f"<@{reminder['user_id']}>", inline=True
                    )
                    embed.add_field(
                        name="Scheduled for:",
                        value=reminder["reminder_time"].strftime("%d/%m/%Y at %H:%M"),
                        inline=True,
                    )

                    # Send the reminder
                    await channel.send(embed=embed)

                    # Mark as sent
                    db_manager.mark_reminder_sent(reminder["id"])

                    logger.info(
                        f"Sent reminder {reminder['id']} to channel {reminder['channel_id']}"
                    )

                except Exception as e:
                    logger.error(f"Error sending reminder {reminder['id']}: {e}")

        except Exception as e:
            logger.error(f"Error in check_reminders: {e}")

        # Wait 1 minute before next check
        try:
            await asyncio.sleep(60)  # 1 minute
        except asyncio.CancelledError:
            logger.info("Reminder checking task cancelled")
            break


@bot.event
async def on_ready():
    logger.info(f"Discord bot {bot.user} has connected successfully")
    logger.info("Syncing slash commands")

    try:
        # Sync commands globally
        synced = await bot.tree.sync(guild=discord.Object(id=os.getenv("GUILD_ID")))
        logger.info(f"Synced {len(synced)} slash command(s) with Discord")

        # List the synced commands
        for command in synced:
            logger.debug(f"Synced command: /{command.name}: {command.description}")

    except Exception as e:
        logger.error(f"Failed to sync commands: {str(e)}")
        logger.debug("Command sync error details:", exc_info=True)

    # Start the monitoring task
    logger.info("Starting ticket monitoring background task")
    bot.loop.create_task(monitor_tickets())

    # Start the reminder checking task
    logger.info("Starting reminder checking background task")
    bot.loop.create_task(check_reminders())

    logger.info("Bot is ready and all systems operational!")


@bot.tree.command(name="ping", description="Check bot latency")
async def ping(interaction: discord.Interaction):
    latency_ms = round(bot.latency * 1000, 2)
    await interaction.response.send_message(f"Pong! Latency: {latency_ms}ms")


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


@bot.tree.command(
    name="delete", description="Delete the last n messages from the channel"
)
async def delete_messages(interaction: discord.Interaction, n: int):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message(
            "You do not have permission to delete messages.", ephemeral=True
        )
        return

    if n < 1 or n > 100:
        await interaction.response.send_message(
            "Please provide a number between 1 and 100.", ephemeral=True
        )
        return

    deleted = await interaction.channel.purge(
        limit=n + 1
    )  # +1 to include the command message
    await interaction.response.send_message(
        f"Deleted {len(deleted)-1} message(s).", ephemeral=True
    )


@bot.tree.command(
    name="remind", description="Set a reminder for a specific date and time"
)
@app_commands.describe(
    date="Date (today/tomorrow/tmrw or dd/mm/yyyy format)",
    time="Time in HH:MM format (24-hour, optional - defaults to current time)",
    message="The reminder message",
)
async def remind_command(
    interaction: discord.Interaction, date: str, message: str, time: str = None
):
    logger.info(
        f"User {interaction.user.id} ({interaction.user.name}) setting reminder for {date} {time or 'current time'}: {message[:50]}..."
    )

    # Parse the reminder date and time
    reminder_datetime = parse_reminder_date(date, time)

    if not reminder_datetime:
        await interaction.response.send_message(
            "❌ Invalid date or time format. Use formats like:\n"
            "• Date: `today`, `tomorrow`, `tmrw`, or `dd/mm/yyyy`\n"
            "• Time: `HH:MM` (24-hour format, optional)",
            ephemeral=True,
        )
        return

    # Get reminder channel ID from environment
    reminder_channel_id = os.getenv("REMINDER_CHANNEL_ID")
    if not reminder_channel_id:
        logger.error("REMINDER_CHANNEL_ID not set in environment variables")
        await interaction.response.send_message(
            "❌ Reminder system is not configured properly. Please contact an administrator.",
            ephemeral=True,
        )
        return

    try:
        reminder_channel_id = int(reminder_channel_id)
    except ValueError:
        logger.error(f"Invalid REMINDER_CHANNEL_ID format: {reminder_channel_id}")
        await interaction.response.send_message(
            "❌ Reminder system is not configured properly. Please contact an administrator.",
            ephemeral=True,
        )
        return

    # Add reminder to database
    success = db_manager.add_reminder(
        user_id=interaction.user.id,
        username=f"{interaction.user.name}#{interaction.user.discriminator}",
        message=message,
        reminder_time=reminder_datetime,
        channel_id=reminder_channel_id,
    )

    if success:
        # Format the reminder time for display
        formatted_time = reminder_datetime.strftime("%d/%m/%Y at %H:%M")

        embed = discord.Embed(
            title="✅ Reminder Set",
            description=f"I'll remind you on **{formatted_time}**",
            color=0x00FF00,
        )
        embed.add_field(name="Message:", value=message, inline=False)
        embed.add_field(
            name="📍 Reminder Location:",
            value=f"The reminder will be sent to <#{reminder_channel_id}>",
            inline=False,
        )

        await interaction.response.send_message(embed=embed)
        logger.info(
            f"Successfully set reminder for user {interaction.user.id} at {reminder_datetime}"
        )
    else:
        logger.error(
            f"Failed to add reminder to database for user {interaction.user.id}"
        )
        await interaction.response.send_message(
            "❌ Failed to set reminder. Please try again later.", ephemeral=True
        )


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
        ("</delete:0>", "Delete the last n messages from the channel"),
        ("/remind", "Set a reminder for a specific date and time"),
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
