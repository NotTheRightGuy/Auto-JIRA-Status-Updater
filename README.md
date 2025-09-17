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

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License.
