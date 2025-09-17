#!/usr/bin/env python3
"""
Test script for the new due date checking functionality.
This script will test the JIRA API methods without sending Discord alerts.
"""

import os
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
from utils.jira import JIRA

load_dotenv()


def load_config():
    """Load configuration from config.json."""
    try:
        with open("config.json", "r") as config_file:
            return json.load(config_file)
    except FileNotFoundError:
        print("Error: config.json file not found")
        return None
    except json.JSONDecodeError as e:
        print(f"Error parsing config.json: {e}")
        return None


def test_due_date_functionality():
    """Test the new due date checking functionality."""
    print("=" * 60)
    print("Testing JIRA Due Date Checking Functionality")
    print("=" * 60)

    # Load config
    config = load_config()
    if not config:
        return False

    print(f"Loaded config for {len(config.get('users', []))} users")

    # Check environment variables
    required_vars = ["ATLASSIAN_URL", "ATLASSIAN_EMAIL", "JIRA_TOKEN"]
    missing_vars = [var for var in required_vars if not os.getenv(var)]

    if missing_vars:
        print(f"Error: Missing environment variables: {missing_vars}")
        return False

    print("Environment variables loaded successfully")

    try:
        # Initialize JIRA client
        print("\nInitializing JIRA client...")
        jira_client = JIRA(
            host=os.getenv("ATLASSIAN_URL"),
            email=os.getenv("ATLASSIAN_EMAIL"),
            token=os.getenv("JIRA_TOKEN"),
        )

        # Test connection
        if not jira_client.check_connection():
            print("Error: Failed to connect to JIRA")
            return False

        print("JIRA connection successful!")

        # Get users from config
        users = config.get("users", [])
        if not users:
            print("Warning: No users configured in config.json")
            return False

        # Extract JIRA IDs
        user_jira_ids = [user["jira_id"] for user in users if "jira_id" in user]
        if not user_jira_ids:
            print("Warning: No user JIRA IDs found in config.json")
            return False

        print(f"\nChecking due dates for {len(user_jira_ids)} users:")
        for user in users:
            print(f"  - {user.get('name', 'Unknown')} ({user.get('jira_id', 'No ID')})")

        # Test the new methods
        print(f"\nTesting due date checking...")

        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)
        print(f"Today: {today}")
        print(f"Tomorrow: {tomorrow}")

        # Get due tasks for all users
        due_tasks_by_user = jira_client.get_all_users_tasks_due_soon(user_jira_ids)

        if due_tasks_by_user:
            total_tasks = sum(len(tasks) for tasks in due_tasks_by_user.values())
            print(f"\n✅ Found {total_tasks} tasks due today or tomorrow:")

            # Create a mapping of jira_id to user name for better display
            user_names = {user["jira_id"]: user["name"] for user in users}

            for user_jira_id, tasks in due_tasks_by_user.items():
                user_name = user_names.get(user_jira_id, user_jira_id)
                print(
                    f"\n  📋 {user_name} ({len(tasks)} task{'s' if len(tasks) != 1 else ''}):"
                )

                for task in tasks:
                    due_date_str = task.fields.duedate
                    priority = (
                        getattr(task.fields.priority, "name", "None")
                        if task.fields.priority
                        else "None"
                    )
                    status = task.fields.status.name

                    if due_date_str:
                        due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date()
                        urgency = "🚨 TODAY" if due_date == today else "⚠️ TOMORROW"
                    else:
                        urgency = "❓ No due date"

                    print(
                        f"    • {task.key}: {task.fields.summary[:50]}{'...' if len(task.fields.summary) > 50 else ''}"
                    )
                    print(
                        f"      Status: {status} | Priority: {priority} | Due: {urgency}"
                    )
        else:
            print("\n✅ No tasks due today or tomorrow found for any user")

        print(f"\n" + "=" * 60)
        print("Test completed successfully!")
        print("=" * 60)
        return True

    except Exception as e:
        print(f"\nError during testing: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = test_due_date_functionality()
    if success:
        print("\n🎉 All tests passed! The due date functionality is ready to use.")
    else:
        print("\n❌ Tests failed. Please check the errors above.")
