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
