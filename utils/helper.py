from typing import Optional, List
from logs.logger import logger
from utils.jira import JIRA
from utils.bitbucket import Bitbucket


def determine_new_status(
    current_status: str,
    branch_exists: bool,
    pr_exists: bool,
    pr_merged: bool,
    is_bug: bool = False,
) -> Optional[str]:
    """
    Determine the new status based on branch and PR state.

    Args:
        current_status: Current JIRA issue status
        branch_exists: Whether a branch exists for this issue
        pr_exists: Whether a PR exists for this issue
        pr_merged: Whether the PR is merged
        is_bug: Whether this is a bug issue type

    Returns:
        New status to set, or None if no change needed
    """
    if not branch_exists:
        # No branch exists, keep current status
        logger.debug(f"No branch found, keeping current status: {current_status}")
        return None

    if pr_exists and pr_merged:
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
        # Branch exists, PR exists but not merged -> In Review
        if current_status not in ["In Review", "Dev Testing", "Performing DevTesing"]:
            logger.info(f"Open PR found, changing status to 'In Review'")
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


def process_issue(jira: JIRA, bitbucket: Bitbucket, issue, repos: List[str]) -> None:
    """
    Process a single JIRA issue and update its status based on branch/PR state.

    Args:
        jira: JIRA client instance
        bitbucket: Bitbucket client instance
        issue: JIRA issue object
        repos: List of repository names to check
    """
    logger.info(f"Processing issue {issue.key}: {issue.fields.status.name}")

    # Check if this is a bug
    issue_type = issue.fields.issuetype.name.lower()
    is_bug = issue_type in ["bug", "implementation bug"]
    logger.debug(f"Issue type: {issue.fields.issuetype.name}, is_bug: {is_bug}")

    branch_found = False
    pr_found = False
    pr_merged = False

    for repo in repos:
        logger.debug(f"Checking repository: {repo}")

        # Check if branch exists
        branch_name = bitbucket.find_branch(repo, issue.key)
        if branch_name:
            branch_found = True
            logger.info(f"Branch found in repo '{repo}': {branch_name}")

            # Check for PRs
            prs = bitbucket.find_prs(repo, issue.key)
            if prs:
                pr_found = True
                for pr in prs:
                    logger.info(
                        f"PR found: {pr['links']['html']['href']}, Status: {pr['state']}"
                    )
                    if pr["state"] == "MERGED":
                        pr_merged = True
                        break

                # If we found a merged PR, no need to check more repositories
                if pr_merged:
                    break
            else:
                logger.debug(f"No PRs found for {issue.key} in {repo}")

        # If we found a merged PR, no need to check more repositories
        if pr_merged:
            break

    # Determine if status change is needed
    new_status = determine_new_status(
        issue.fields.status.name, branch_found, pr_found, pr_merged, is_bug
    )

    child_status_changed = False
    if new_status:
        if jira.change_status(issue, new_status):
            logger.info(f"Successfully changed status of {issue.key} to '{new_status}'")
            child_status_changed = True
        else:
            logger.error(f"Failed to change status of {issue.key} to '{new_status}'")
    else:
        logger.info(f"No status change needed for {issue.key}")

    # Update parent status if child status changed
    try:
        jira.update_parent_status_if_needed(issue, child_status_changed)
    except Exception as e:
        logger.error(f"Failed to update parent status for {issue.key}: {e}")
