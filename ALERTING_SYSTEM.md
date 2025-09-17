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
