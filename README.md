# Auto JIRA Status Updater

An automated system that synchronizes JIRA issue statuses based on Git branch and Pull Request states in Bitbucket, with Discord integration for monitoring and notifications.

## Features

### Core Functionality
- **Automated JIRA Updates**: Automatically updates JIRA issue statuses based on development progress
- **Multi-Repository Support**: Monitors multiple Bitbucket repositories simultaneously
- **Comprehensive Logging**: Detailed logging with proper error handling and activity tracking
- **Persistent Storage**: SQLite database for reliable data persistence across restarts

### Discord Bot Integration
- **Real-time Monitoring**: Watch JIRA tickets for changes (status, description, summary, assignee)
- **Interactive Commands**: Easy-to-use slash commands for ticket management
- **Direct Notifications**: Receive DMs when watched tickets change
- **Centralized Logging**: Hourly worker logs sent to designated Discord channel
- **Database Statistics**: View system usage and statistics

### Worker System
- **Hourly Automation**: Background worker runs status updates every hour
- **Discord Logging**: All worker activities logged to Discord for visibility
- **Error Recovery**: Automatic retry mechanism with graceful error handling
- **Database Backups**: Automatic daily database backups with cleanup of old backups

## Discord Bot Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/ping` | Check bot latency | `/ping` |
| `/watch <ticket-id>` | Start monitoring a JIRA ticket | `/watch ABC-123` |
| `/unwatch <ticket-id>` | Stop monitoring a JIRA ticket | `/unwatch ABC-123` |
| `/list` | Show all tickets you're watching | `/list` |
| `/help` | Display help information | `/help` |

## Status Update Logic

The system updates JIRA issues according to the following rules:

1. **No branch exists**: Keep current status
2. **Branch exists + PR merged**: Set status to "Dev Testing"
3. **Branch exists + PR open**: Set status to "In Review"
4. **Branch exists + No PR**: Set status to "In Progress"

## Setup

### Prerequisites
- Python 3.8+
- Discord bot token
- JIRA and Bitbucket API access

### Installation

1. Clone the repository and navigate to it:
   ```bash
   git clone <repository-url>
   cd auto-jira-status-updater
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Create a `.env` file with the following variables:
   ```env
   # JIRA & Bitbucket Configuration
   ATLASSIAN_URL=https://your-domain.atlassian.net/
   ATLASSIAN_EMAIL=your-email@domain.com
   JIRA_TOKEN=your-jira-api-token
   BITBUCKET_TOKEN=your-bitbucket-app-password
   BITBUCKET_WORKSPACE=your-bitbucket-workspace

   # Discord Bot Configuration
   DISCORD_APPLICATION_ID=your-discord-app-id
   DISCORD_PUBLIC_KEY=your-discord-public-key
   DISCORD_BOT_TOKEN=your-discord-bot-token

   # Discord Channel IDs
   LOGS_CHANNEL_ID=channel-id-for-worker-logs
   ALERTS_CHANNEL_ID=channel-id-for-alerts
   WATCH_CHANNEL_ID=channel-id-for-watch-notifications
   ```

### Discord Bot Setup

1. **Create Discord Application**:
   - Go to [Discord Developer Portal](https://discord.com/developers/applications)
   - Create a new application
   - Go to "Bot" section and create a bot
   - Copy the bot token to your `.env` file

2. **Invite Bot to Server**:
   - Go to "OAuth2" > "URL Generator"
   - Select scopes: `bot`
   - Select permissions: `Send Messages`, `Read Message History`, `Use Slash Commands`
   - Use the generated URL to invite the bot to your server

3. **Setup Channels**:
   - Create channels for logs, alerts, and notifications
   - Get channel IDs (Developer Mode > Right-click channel > Copy ID)
   - Add channel IDs to your `.env` file

## Usage

### Quick Start
Simply run the main script to start both the Discord bot and worker together:
```bash
python3 main.py
```

This unified command will:
- ✅ Start the Discord bot for interactive commands
- ✅ Launch the hourly worker for automatic status updates  
- ✅ Set up Discord logging integration
- ✅ Initialize the SQLite database
- ✅ Begin monitoring watched tickets every 5 minutes

### Using the Discord Bot

1. **Watch a Ticket**:
   ```
   /watch ABC-123
   ```
   You'll receive a DM whenever this ticket changes.

2. **Check Latency**:
   ```
   /ping
   ```

3. **View Watched Tickets**:
   ```
   /list
   ```

4. **Stop Watching**:
   ```
   /unwatch ABC-123
   ```

## Configuration

### Repositories

Edit the `repos` list in `config.json` to specify which repositories to monitor:

```python
repos = [
    "applift-lib",
    "applift-app", 
    "dsp-customers-web",
    "dsp-campaign-builder-web",
    "dsp-audience-builder-web"
    # Add more repositories as needed
]
```

### Monitoring Settings

- **Ticket Check Interval**: The Discord bot checks for ticket changes every 5 minutes
- **Worker Schedule**: The status updater runs automatically every hour
- **Notification Delivery**: Changes are sent via Discord DM to watching users

### Logging

- **Console Logs**: Real-time logging output for both bot and worker
- **File Logs**: Written to `jira_status_updater.log`
- **Discord Logs**: Worker logs sent to configured Discord channel every hour
- **Log Levels**: Configurable in the logging configuration

## Data Storage

The system uses SQLite for persistent data storage:

- **Database File**: `jira_watcher.db` (created automatically)
- **Watcher Data**: User preferences and ticket watching relationships
- **Ticket Snapshots**: Current state of monitored JIRA tickets for change detection
- **Automatic Backups**: Daily backups stored in `backups/` directory
- **Cleanup**: Automatic removal of backup files older than 7 days

### Database Schema

```sql
-- User watch preferences
watchers (
    id INTEGER PRIMARY KEY,
    ticket_id TEXT,
    user_id INTEGER,
    username TEXT,
    discriminator TEXT,
    created_at TIMESTAMP
)

-- JIRA ticket snapshots for change detection
ticket_snapshots (
    ticket_id TEXT PRIMARY KEY,
    status TEXT,
    summary TEXT,
    description TEXT,
    assignee TEXT,
    last_updated TEXT,
    snapshot_created_at TIMESTAMP,
    snapshot_updated_at TIMESTAMP
)
```

## Architecture

### Components

1. **Unified Main Application** (`main.py`):
   - **Single Entry Point**: Runs both Discord bot and worker in one process
   - **Discord Bot**: Handles user interactions and commands
   - **Background Worker**: Runs JIRA status updates every hour
   - **Ticket Monitoring**: Checks for changes every 5 minutes
   - **Logging Integration**: Sends worker logs to Discord channels

2. **JIRA Client** (`utils/jira.py`):
   - Interfaces with JIRA API
   - Handles issue status transitions
   - Manages parent-child issue relationships

3. **Bitbucket Client** (`utils/bitbucket.py`):
   - Monitors repository branches and PRs
   - Provides development progress data

4. **Database Manager** (`utils/database.py`):
   - SQLite database operations
   - Handles watchers and ticket snapshots
   - Automatic backups and cleanup

### Data Flow

1. **Unified System Startup**:
   - Single `python3 main.py` command starts everything
   - Discord bot initializes and connects
   - Worker background task starts automatically
   - Database initializes with proper schema

2. **Ticket Watching**:
   - User runs `/watch` command via Discord
   - Bot validates ticket exists in JIRA
   - Ticket and user data stored in SQLite database
   - Background monitoring task tracks changes every 5 minutes
   - Users receive DMs when changes occur

3. **Automated Status Updates**:
   - Worker runs every hour automatically
   - Checks all user's open tickets and compares with Bitbucket
   - Updates JIRA statuses based on development progress
   - Logs all activities and sends to Discord logs channel
   - Database backups created daily with automatic cleanup

### Manual Testing
1. **Start the system**:
   ```bash
   python3 main.py
   ```

2. **Test commands** in Discord:
   - `/ping` - Check bot responsiveness
   - `/watch TEST-123` - Start watching a ticket
   - `/list` - View watched tickets
   - `/stats` - View database statistics
   - `/unwatch TEST-123` - Stop watching

3. **Verify functionality**:
   - Worker logs appear in Discord channel every hour
   - Ticket changes trigger notifications via DM
   - Database persists data between restarts

## Troubleshooting

### Common Issues

1. **Bot Not Responding**:
   - Check bot token in `.env`
   - Verify bot has proper permissions in Discord server
   - Check console for error messages

2. **JIRA Connection Failed**:
   - Verify ATLASSIAN_URL format includes trailing slash
   - Check JIRA_TOKEN is valid API token, not password
   - Ensure email has JIRA access

3. **Discord Logging Not Working**:
   - Verify LOGS_CHANNEL_ID is correct
   - Check bot has permission to send messages in log channel
   - Ensure channel exists and bot is in the server

4. **Ticket Monitoring Issues**:
   - Verify ticket ID format (e.g., ABC-123)
   - Check if ticket exists and is accessible
   - Ensure JIRA client has read permissions

### Getting API Tokens

#### JIRA API Token:
1. Go to [Atlassian Account Settings](https://id.atlassian.com/manage-profile/security/api-tokens)
2. Create a new API token
3. Copy the token to your `.env` file

#### Bitbucket App Password:
1. Go to Bitbucket Settings > App passwords
2. Create new app password with repository read permissions
3. Copy the password to your `.env` file

## File Structure

```
.
├── discord/
│   └── main.py            # Legacy Discord bot (deprecated)
├── utils/
│   ├── jira.py           # JIRA API client
│   ├── bitbucket.py      # Bitbucket API client
│   ├── database.py       # SQLite database manager
│   ├── helper.py         # Helper functions
│   └── ratelimit.py      # Rate limiting utilities
├── logs/
│   └── logger.py         # Logging configuration
├── backups/              # Database backups (auto-created)
├── main.py               # **MAIN ENTRY POINT** - Unified bot + worker
├── worker.py             # Legacy worker (deprecated)
├── jira_watcher.db       # SQLite database (auto-created)
├── requirements.txt      # Python dependencies
├── .env                  # Environment variables (create this)
├── .gitignore           # Git ignore rules
└── README.md            # Documentation
```

# User Management & Separation of Concerns

## Overview
The JIRA automation system uses a clear separation between **automation actions** and **monitoring/alerting** to ensure security and proper scope of operations.

## 🔐 Authentication & User Separation

### Current User (Authentication)
- **Used for**: Status updates and automation actions
- **Authentication**: Uses `ATLASSIAN_EMAIL` and `JIRA_TOKEN` from `.env`
- **Scope**: Only processes tickets assigned to the authenticated user
- **Functions**: `get_all_open_issues()`, `get_all_open_bugs()`, `change_status()`
- **JQL**: `assignee = currentUser()`

### Config Users (Monitoring)
- **Used for**: Due date alerts and monitoring
- **Configuration**: Defined in `config.json` with specific JIRA IDs
- **Scope**: Can query tickets for any configured user
- **Functions**: `get_user_tasks_due_soon()`, `get_all_users_tasks_due_soon()`
- **JQL**: `assignee = "specific_jira_id"`

## 📋 Current Implementation

### Status Updates (currentUser() only)
```python
def get_all_open_issues(self) -> List:
    """Get all open issues assigned to the current user."""
    jql = """
assignee = currentUser()
AND status NOT IN (Closed, Done, Rejected, Resolved, "Deployed to production")
AND type IN (Sub-task, Subtask)
ORDER BY created DESC
    """
```

### Due Date Monitoring (all config users)
```python
def get_user_tasks_due_soon(self, user_jira_id: str) -> List:
    """Get all open tasks assigned to a specific user that are due today or tomorrow."""
    jql = f"""
assignee = "{user_jira_id}"
AND status NOT IN (Closed, Done, Rejected, Resolved, "Deployed to production")
AND duedate >= "{today_str}"
AND duedate <= "{tomorrow_str}"
ORDER BY duedate ASC, priority DESC
    """
```

## 🎯 Operational Flow

### Status Update Process
1. Authenticate as current user (`ATLASSIAN_EMAIL`)
2. Query only tickets assigned to current user
3. Process and update status based on Git activity
4. Send status change notifications

### Due Date Alert Process
1. Read all users from `config.json`
2. For each user, query their assigned tickets
3. Check due dates (today/tomorrow)
4. Send personalized alerts with user names

## ⚙️ Configuration

### .env (Authentication)
```bash
ATLASSIAN_EMAIL="janmejay.c@iqm.com"  # Used for currentUser() authentication
JIRA_TOKEN="..."                      # Authentication token
```

### config.json (Monitoring Users)
```json
{
    "users": [
        {
            "name": "Devarsh Gandhi",
            "jira_id": "712020:8157fbf9-6c46-4378-95b4-6691dd2ba5a6"
        },
        {
            "name": "Janmejay Chatterjee", 
            "jira_id": "712020:025d4fbf-7c7c-44d4-a9e0-98e741d936fa"
        },
        {
            "name": "Nitish Jaiswal",
            "jira_id": "712020:59149839-1dba-4692-b8b6-245b981d3f41"
        }
        // ... other users
    ]
}
```

## 🛡️ Security & Permissions

### Why This Separation?
1. **Limited Automation Scope**: Only the authenticated user's tickets can be modified
2. **Broad Monitoring Capability**: Can monitor due dates for all team members
3. **Permission Control**: Status changes require proper authentication
4. **Team Visibility**: Everyone gets due date alerts regardless of who runs the bot

### Required Permissions
- **Authenticated User**: Must have permission to view and edit their own tickets
- **Config Users**: Must be visible to the authenticated user (same project/team)
- **JIRA Token**: Must have appropriate project access for both automation and monitoring

## 📊 Current Users in Config

| Name | JIRA ID | Purpose |
|------|---------|---------|
| Devarsh Gandhi | 712020:8157fbf9-6c46-4378-95b4-6691dd2ba5a6 | Due date monitoring |
| Janmejay Chatterjee | 712020:025d4fbf-7c7c-44d4-a9e0-98e741d936fa | Due date monitoring |
| Nitish Jaiswal | 712020:59149839-1dba-4692-b8b6-245b981d3f41 | Due date monitoring |
| Vivek Modiya | 63e0f954790148a180969e47 | Due date monitoring |
| Varun Patel | 712020:588b9921-c245-4d18-8274-49b7b78f4ae4 | Due date monitoring |
| Divya Panchori | 712020:1c499e28-a210-4727-b648-088d871b59a1 | Due date monitoring |
| Desh Deepak Singh | 61ca8d3468926d0068f0891a | Due date monitoring |
| Aravind | 61b6ddfc91c049006f9ee6ac | Due date monitoring |

## 🔍 Verification

### Check Status Update Scope
```bash
# This query shows what tickets can be automatically updated
assignee = currentUser()
AND status NOT IN (Closed, Done, Rejected, Resolved, "Deployed to production")
```

### Check Due Date Monitoring Scope  
```bash
# This query shows what tickets are monitored for due dates (per user)
assignee = "712020:8157fbf9-6c46-4378-95b4-6691dd2ba5a6"
AND status NOT IN (Closed, Done, Rejected, Resolved, "Deployed to production")
AND duedate >= "2025-09-17"
AND duedate <= "2025-09-18"
```

## 🚀 Benefits of This Approach

1. **Security**: Automation can only modify tickets of the authenticated user
2. **Team Coverage**: Due date alerts cover all team members
3. **Flexibility**: Easy to add/remove users from monitoring without affecting automation
4. **Audit Trail**: Clear separation between automated changes and monitoring
5. **Scalability**: Can monitor any number of users without additional authentication setup

This design ensures that automation stays within proper bounds while providing comprehensive team visibility through alerts and monitoring.


# Due Date Alert Feature

## Overview
This feature automatically checks for JIRA tasks that are due today or tomorrow for configured users and sends alerts to the Discord alerts channel.

## Configuration

### Config.json Settings
- `"alert_users_at": "1000"` - Time (HHMM format) when to send daily due date alerts (default: 10:00 AM)
- `"users"` array must contain user objects with:
  - `"name"`: Display name for the user
  - `"jira_id"`: The user's JIRA account ID (format: "712020:xxxx-xxxx-xxxx-xxxx")

### Environment Variables
- `ALERTS_CHANNEL_ID` - Discord channel ID where due date alerts will be sent

## How It Works

1. **Startup Alert**: When the bot starts up, it immediately checks for due tasks and sends alerts
2. **Daily Schedule**: At the configured time (`alert_users_at`), the system checks for due tasks again
3. **User Query**: For each user in the config, it queries JIRA for:
   - All open tasks assigned to that user
   - Tasks with due dates of today or tomorrow
   - Excludes closed, done, rejected, resolved, and deployed tasks
4. **Alert Generation**: If due tasks are found, formatted alerts are sent to the Discord alerts channel
5. **Smart Timing**: Sends startup alerts immediately, then daily alerts at the configured time

## Alert Format

The Discord alerts include:
- **User name** and task counts
- **Tasks due TODAY** (red urgent indicator)
- **Tasks due TOMORROW** (yellow warning indicator)
- **Task details**: Key, summary (truncated), priority, and clickable links
- **Helpful tips** for task management

## JIRA Query Details

The system uses this JQL query for each user:
```jql
assignee = "USER_JIRA_ID"
AND status NOT IN (Closed, Done, Rejected, Resolved, "Deployed to production")
AND duedate >= "YYYY-MM-DD"  -- today
AND duedate <= "YYYY-MM-DD"  -- tomorrow
ORDER BY duedate ASC, priority DESC
```

## Files Modified

### `/utils/jira.py`
- Added `get_user_tasks_due_soon(user_jira_id)` - Get due tasks for a specific user
- Added `get_all_users_tasks_due_soon(user_jira_ids)` - Get due tasks for multiple users

### `/main.py`
- Added `send_due_date_alerts(due_tasks_by_user, user_config)` - Send formatted Discord alerts
- Added `check_and_send_due_date_alerts()` to JIRAStatusWorker class
- Integrated due date checking into the main worker loop

## Testing

Use the included `test_due_dates.py` script to test the functionality:
```bash
python test_due_dates.py
```

This will:
- Test JIRA connection
- Query for due tasks
- Display results without sending Discord alerts
- Verify the configuration is correct

## Logs

The feature logs its activities:
- Daily due date check initiation
- Number of users and tasks found
- Success/failure of alert sending
- Error details for troubleshooting

## Example Alert

```
📅 Due Date Alert for John Doe

🚨 Due TODAY (2 tasks):
• PROJ-123 - Fix critical login bug... (Priority: High)
• PROJ-124 - Update user documentation... (Priority: Medium)

⚠️ Due TOMORROW (1 task):
• PROJ-125 - Code review for new feature... (Priority: Low)

💡 Tip:
Check your task priorities and plan your day accordingly!
```
# Complete Alerting System Summary

## Overview
The JIRA automation system includes comprehensive alerting functionality with **clear separation between automation and monitoring**:

- **Automation**: Only modifies tickets assigned to the authenticated user (`currentUser()`)
- **Monitoring**: Checks due dates and sends alerts for all users configured in `config.json`

## 🔐 User Management Approach

### Status Updates (currentUser() only)
- **Scope**: Only processes tickets assigned to the authenticated user
- **Authentication**: Uses `ATLASSIAN_EMAIL` and `JIRA_TOKEN` from `.env`
- **Purpose**: Automatic status changes based on Git activity
- **Security**: Limited to user's own tickets only

### Due Date Alerts (all config users)
- **Scope**: Monitors due dates for all users in `config.json`
- **Configuration**: Uses specific JIRA IDs from config
- **Purpose**: Team-wide due date notifications
- **Coverage**: All 8 team members currently configured

## 🚨 Alert Types

### 1. Due Date Alerts
- **Purpose**: Notify users about tasks due today or tomorrow
- **Channel**: `ALERTS_CHANNEL_ID` (Discord)
- **Frequency**: 
  - **Startup**: Immediately when bot starts
  - **Daily**: At configured time (`alert_users_at` in config.json)
- **Configuration**: 
  - `"alert_users_at": "1000"` (10:00 AM daily)
  - Users must be configured in `config.json` with JIRA IDs

### 2. Status Change Notifications  
- **Purpose**: Notify about all JIRA ticket status updates made by the automation
- **Channel**: `STATUS_CHANGE_CHANNEL_ID` (Discord)
- **Frequency**: After each status update run
- **Content**: Shows old status → new status for all updated tickets

### 3. Watched Ticket Alerts
- **Purpose**: Notify specific users about changes to tickets they're watching
- **Channel**: `WATCH_CHANNEL_ID` (Discord)  
- **Frequency**: When watched tickets change status
- **Content**: Personal notifications with user mentions

### 4. System Logs
- **Purpose**: Detailed system logging and error reporting
- **Channel**: `LOGS_CHANNEL_ID` (Discord)
- **Frequency**: Continuous logging
- **Content**: System status, errors, and operational details

## 📅 Timing & Schedule

### Due Date Alerts
```
Startup: Immediately on bot start
Daily: At 10:00 AM (configurable via alert_users_at)
```

### Status Updates & Notifications
```
Scheduled runs: 09:00, 12:00, 15:00, 18:00 (configurable via run_on)
Interval runs: Every 60 minutes (configurable via status_updater_interval)
```

### Ticket Monitoring
```
Watch checks: Every 5 minutes (configurable via watch_interval)
```

## 🔧 Configuration

### config.json Settings
```json
{
    "users": [
        {
            "name": "User Name",
            "jira_id": "712020:xxxx-xxxx-xxxx-xxxx"
        }
    ],
    "run_on": ["0900", "1200", "1500", "1800"],
    "alert_users_at": "1000",
    "watch_interval": 5,
    "status_updater_interval": 60,
    "run_status_updater_on_interval": true
}
```

### .env Settings
```bash
# Discord Channel IDs
ALERTS_CHANNEL_ID="1417762995081318450"      # Due date alerts
STATUS_CHANGE_CHANNEL_ID="1417861837126373417" # Status changes  
WATCH_CHANNEL_ID="1417762949900275764"        # Watched tickets
LOGS_CHANNEL_ID="1417762921836187681"         # System logs
```

## 🎯 Alert Flow

### Startup Sequence
1. Bot starts and connects to Discord
2. **Immediate due date check and alerts sent**
3. Worker loop begins
4. Ticket monitoring starts

### Daily Operations
1. Status updates run at scheduled times (09:00, 12:00, 15:00, 18:00)
2. Status change notifications sent after each update
3. Due date alerts sent daily at 10:00 AM
4. Watched ticket alerts sent when changes detected
5. System logs sent continuously

### Alert Smart Logic
- **Due dates**: Startup + daily at configured time
- **Status changes**: Only when actual status updates occur
- **Watched tickets**: Only for tickets with active watchers
- **Logs**: Continuous with buffering and error handling

## 📱 Discord Message Formats

### Due Date Alert
```
📅 Due Date Alert for John Doe

🚨 Due TODAY (2 tasks):
• [PROJ-123](link) - Fix critical bug... (Priority: High)

⚠️ Due TOMORROW (1 task):  
• [PROJ-124](link) - Code review... (Priority: Medium)

💡 Tip: Check your task priorities and plan your day accordingly!
```

### Status Change Notification
```
🔄 JIRA Status Update Summary

📋 Issues Updated (3):
• [PROJ-123](link): Open → In Progress
• [PROJ-124](link): In Progress → Dev Testing  

🐛 Bugs Updated (1):
• [BUG-456](link): Backlog → In Progress

📊 Summary: Total tickets updated: 4 | Issues: 3 | Bugs: 1
🤖 Automation: Updates triggered by Git activity detection
```

### Watched Ticket Alert  
```
⚡ Automated Status Update! @user1 @user2

Automated Update: PROJ-123
[View Ticket](link)

Automated Change: • Status: Open → In Progress
👥 Watching Users (2): user1, user2  
🔧 Update Source: Hourly Worker (based on Git activity)
```

## 🛠️ Technical Implementation

### Files Modified
- `main.py`: Core alerting logic and Discord integration
- `utils/jira.py`: Due date querying methods
- `config.json`: User and timing configuration
- `.env`: Discord channel configuration

### Key Functions Added
- `send_due_date_alerts()`: Due date Discord notifications
- `send_status_change_notifications()`: Status change Discord notifications  
- `check_and_send_due_date_alerts()`: Due date checking orchestration
- `get_user_tasks_due_soon()`: JIRA API for user due dates
- `get_all_users_tasks_due_soon()`: Multi-user due date queries

### Startup vs Daily Alert Logic
- `startup_alerts_sent` flag prevents duplicate startup alerts
- Daily alerts use time-based checking with 1-minute tolerance  
- Smart logic prevents conflicts between startup and daily alerts

## 🔍 Monitoring & Troubleshooting

### Log Messages to Watch For
- "Sending due date alerts at startup"  
- "Sending daily due date alerts at HH:MM"
- "Sent status change notification for X tickets"
- Discord permission errors
- JIRA connection issues

### Common Issues
- Missing Discord channel permissions
- Invalid JIRA user IDs in config
- Network connectivity problems
- Discord rate limiting

### Testing
- Use `test_due_dates.py` for due date functionality
- Use `test_status_notifications.py` for status change format
- Monitor Discord channels for actual message delivery
- Check system logs for error details

This comprehensive alerting system ensures users stay informed about their JIRA tasks through multiple notification channels with appropriate timing and context.



## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License.
