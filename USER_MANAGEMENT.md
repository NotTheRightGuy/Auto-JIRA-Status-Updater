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
