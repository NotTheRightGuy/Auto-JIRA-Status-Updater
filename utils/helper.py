from typing import Optional, List
from logs.logger import logger
from services.jira import JIRA
from services.bitbucket import Bitbucket
from datetime import datetime, timedelta, time, timezone


def determine_new_status(
    current_status: str,
    branch_exists: bool,
    pr_exists: bool,
    all_pr_merged: bool,
    is_bug: bool = False,
    is_story: bool = False,
) -> Optional[str]:
    """
    Determine the new status based on branch and PR state.

    Args:
        current_status: Current JIRA issue status
        branch_exists: Whether a branch exists for this issue
        pr_exists: Whether a PR exists for this issue
        pr_merged: Whether the PR is merged
        is_bug: Whether this is a bug issue type
        is_story: Whether this is a story issue type

    Returns:
        New status to set, or None if no change needed
    """
    if not branch_exists:
        # No branch exists, keep current status
        logger.debug(f"No branch found, keeping current status: {current_status}")
        return None

    if pr_exists and all_pr_merged:
        # Branch exists, PR exists and is merged
        if is_bug:
            # For bugs: merged PR -> Resolved
            if current_status != "Resolved":
                logger.info(f"PR merged for bug, changing status to 'Resolved'")
                return "Resolved"
        else:
            # For issues: merged PR -> Dev Testing
            if current_status != "Dev Testing":
                logger.info(f"PR merged for issue, changing status to 'Dev Testing'")
                return "Dev Testing"

    elif pr_exists:
        return "In Review"

    else:
        # Branch exists but no PR -> In Progress
        valid_statuses = ["In Progress", "In Review", "Dev Testing", "Done"]
        if is_bug:
            valid_statuses = [
                "In Progress",
                "In Review",
                "Performing DevTesing",
                "Resolved",
            ]

        if current_status not in valid_statuses:
            logger.info(f"Branch found but no PR, changing status to 'In Progress'")
            return "In Progress"

    logger.debug(f"No status change needed, keeping: {current_status}")
    return None


async def process_issue(
    jira: JIRA, bitbucket: Bitbucket, issue, repos: List[str]
) -> None:
    """
    Process a single JIRA issue and update its status based on branch/PR state.

    Args:
        jira: JIRA client instance
        bitbucket: Bitbucket client instance
        issue: JIRA issue object
        repos: List of repository names to check
    """
    logger.info(f"Processing issue {issue.key}: {issue.fields.status.name}")

    # Check if this is a bug or story
    issue_type = issue.fields.issuetype.name.lower()
    is_bug = issue_type in ["bug", "implementation bug"]
    is_story = issue_type in ["story"]
    logger.debug(
        f"Issue type: {issue.fields.issuetype.name}, is_bug: {is_bug}, is_story: {is_story}"
    )

    branch_found = False
    pr_found = False
    all_pr_merged = False

    for repo in repos:
        logger.debug(f"Checking repository: {repo}")

        # Check if branch exists
        branch_name = bitbucket.find_branch(repo, issue.key)
        if branch_name:
            branch_found = True
            logger.info(f"Branch found in repo '{repo}': {branch_name}")

            # Check for PRs
            prs = bitbucket.find_prs(repo, issue.key)
            n_prs = len(prs)
            total_pr_merged = 0

            if n_prs > 0:
                pr_found = True
                total_pr_merged = 0
                for pr in prs:
                    logger.info(
                        f"PR found: {pr['links']['html']['href']}, Status: {pr['state']}"
                    )
                    if pr["state"] == "MERGED":
                        total_pr_merged += 1
                if total_pr_merged == n_prs:
                    all_pr_merged = True
            else:
                logger.debug(f"No PRs found for {issue.key} in {repo}")

    # Determine if status change is needed
    new_status = determine_new_status(
        issue.fields.status.name,
        branch_found,
        pr_found,
        all_pr_merged,
        is_bug,
        is_story,
    )

    child_status_changed = False
    if new_status:
        # Use async version of change_status if available, otherwise fall back to sync
        if hasattr(jira, "change_status_async"):
            if await jira.change_status_async(issue, new_status):
                logger.info(
                    f"Successfully changed status of {issue.key} to '{new_status}'"
                )
                child_status_changed = True
            else:
                logger.error(
                    f"Failed to change status of {issue.key} to '{new_status}'"
                )
        else:
            if jira.change_status(issue, new_status):
                logger.info(
                    f"Successfully changed status of {issue.key} to '{new_status}'"
                )
                child_status_changed = True
            else:
                logger.error(
                    f"Failed to change status of {issue.key} to '{new_status}'"
                )
    else:
        logger.info(f"No status change needed for {issue.key}")

    # TODO  This logic is wrong, take a look at it again
    # Update parent status if child status changed
    try:
        # Use async version if available, otherwise fall back to sync
        if hasattr(jira, "update_parent_status_if_needed_async"):
            await jira.update_parent_status_if_needed_async(issue, child_status_changed)
        else:
            jira.update_parent_status_if_needed(issue, child_status_changed)
    except Exception as e:
        logger.error(f"Failed to update parent status for {issue.key}: {e}")


def validate_discord_content(content: str, max_length: int = 2000) -> str:
    """Validate and truncate Discord content to fit within limits.

    Args:
        content: The content to validate
        max_length: Maximum allowed length (default 2000 for messages)

    Returns:
        Truncated content if necessary
    """
    if len(content) <= max_length:
        return content

    # Truncate with a clear indication
    truncation_msg = "... [TRUNCATED DUE TO LENGTH]"
    available_space = max_length - len(truncation_msg)

    if available_space > 0:
        return content[:available_space] + truncation_msg
    else:
        # If truncation message itself is too long, just cut off
        return content[:max_length]


def validate_discord_embed_field(value: str, max_length: int = 1024) -> str:
    """Validate and truncate Discord embed field value to fit within limits.

    Args:
        value: The field value to validate
        max_length: Maximum allowed length (default 1024 for embed fields)

    Returns:
        Truncated value if necessary
    """
    if len(value) <= max_length:
        return value

    truncation_msg = "... (truncated)"
    available_space = max_length - len(truncation_msg)

    if available_space > 0:
        return value[:available_space] + truncation_msg
    else:
        return value[:max_length]


def parse_time_string(time_str: str) -> time:
    """Parse time string in format HHMM to time object.

    Args:
        time_str: Time in format like '1000' for 10:00 AM or '1310' for 1:10 PM

    Returns:
        datetime.time object
    """
    if isinstance(time_str, int):
        time_str = str(time_str).strip()
    elif not isinstance(time_str, str):
        raise ValueError(f"Time must be a string or integer, got {type(time_str)}")

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


def parse_reminder_date(
    date_string: str, time_string: Optional[str] = None
) -> Optional[datetime]:
    """
    Parse a date string for reminders supporting multiple formats.

    Args:
        date_string: Date in formats like "today", "tomorrow", "tmrw", "dd/mm/yyyy"
        time_string: Optional time in format "HH:MM" (24-hour format)

    Returns:
        datetime object or None if parsing fails
    """
    try:
        now = datetime.now()
        target_date = None

        date_string = date_string.lower().strip()

        # Handle relative dates
        if date_string in ["today"]:
            target_date = now.date()
        elif date_string in ["tomorrow", "tmrw"]:
            target_date = (now + timedelta(days=1)).date()
        else:
            # Try to parse DD/MM/YYYY format
            try:
                target_date = datetime.strptime(date_string, "%d/%m/%Y").date()
            except ValueError:
                # Try DD/MM/YY format
                try:
                    target_date = datetime.strptime(date_string, "%d/%m/%y").date()
                except ValueError:
                    logger.warning(f"Could not parse date string: {date_string}")
                    return None

        # Parse time if provided
        if time_string:
            try:
                time_obj = datetime.strptime(time_string.strip(), "%H:%M").time()
                result = datetime.combine(target_date, time_obj)
            except ValueError:
                logger.warning(f"Could not parse time string: {time_string}")
                # Default to current time if time parsing fails
                result = datetime.combine(target_date, now.time())
        else:
            # Default to current time if no time specified
            result = datetime.combine(target_date, now.time())

        # Ensure the reminder is in the future
        if result <= now:
            logger.warning(f"Reminder time {result} is in the past")
            return None

        return result

    except Exception as e:
        logger.error(f"Error parsing reminder date: {e}")
        return None
