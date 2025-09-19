import logging
from typing import List, Optional
from jira import JIRA as jira_client
from datetime import datetime, timedelta
from .database import DatabaseManager
import discord
from discord.ext import commands
from services.database import TicketSnapshot, DatabaseManager
from typing import Dict
import asyncio
import concurrent.futures

logger = logging.getLogger(__name__)


class JIRA:
    def __init__(self, host: str, email: str, token: str):
        self.host = host
        self.email = email
        self.token = token
        self.client = jira_client(server=self.host, basic_auth=(self.email, self.token))
        logger.info(f"Initialized JIRA client for {host}")
        self.transitions = {}
        # Thread pool for async operations
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)

    async def get_issue_async(self, issue_key: str, timeout: float = 10.0):
        """Async wrapper for JIRA issue fetching with timeout."""
        loop = asyncio.get_event_loop()
        try:
            # Run the blocking JIRA call in a thread pool with timeout
            issue = await asyncio.wait_for(
                loop.run_in_executor(self.executor, self.client.issue, issue_key),
                timeout=timeout,
            )
            return issue
        except asyncio.TimeoutError:
            logger.error(f"Timeout fetching issue {issue_key} after {timeout}s")
            raise
        except Exception as e:
            logger.error(f"Error fetching issue {issue_key}: {e}")
            raise

    def check_connection(self) -> bool:
        """Check connection to JIRA instance."""
        try:
            self.client.myself()
            logger.info("JIRA connection successful")
            return True
        except Exception as e:
            logger.error(f"Connection to JIRA failed: {e}")
            return False

    def get_parent_issue(self, issue):
        """Get the parent issue of a subtask or task."""
        try:
            parent_key = issue.fields.parent.key
            parent_issue = self.client.issue(parent_key)
            logger.info(f"Found parent issue {parent_key} for {issue.key}")
            return parent_issue

        except Exception as e:
            logger.error(f"Failed to get parent issue for {issue.key}: {e}")
            return None

    def update_parent_status_if_needed(
        self, child_issue, child_status_changed: bool
    ) -> bool:
        """Update parent issue status to 'In Progress' if child status changed and parent is not already in progress."""
        if not child_status_changed:
            logger.debug(
                f"Child issue {child_issue.key} status didn't change, skipping parent update"
            )
            return False

        parent_issue = self.get_parent_issue(child_issue)
        if not parent_issue:
            logger.debug(f"No parent issue found for {child_issue.key}")
            return False

        current_parent_status = parent_issue.fields.status.name
        logger.info(
            f"Parent issue {parent_issue.key} current status: {current_parent_status}"
        )

        # Check if parent is already in progress or beyond
        if current_parent_status.lower() in [
            "in progress",
            "dev testing",
            "resolved",
            "done",
        ]:
            logger.info(
                f"Parent issue {parent_issue.key} is already at '{current_parent_status}', no update needed"
            )
            return False

        # Update parent to 'In Progress'
        logger.info(f"Updating parent issue {parent_issue.key} to 'In Progress'")
        return self.change_status(parent_issue, "In Progress")

    async def update_parent_status_if_needed_async(
        self, child_issue, child_status_changed: bool
    ) -> bool:
        """Async version of update_parent_status_if_needed using thread pool."""
        loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    self.executor,
                    self.update_parent_status_if_needed,
                    child_issue,
                    child_status_changed,
                ),
                timeout=15.0,  # 15 second timeout for parent updates
            )
            return result
        except asyncio.TimeoutError:
            logger.error(f"Timeout updating parent status for {child_issue.key}")
            return False
        except Exception as e:
            logger.error(
                f"Error in async parent status update for {child_issue.key}: {e}"
            )
            return False

    def get_issue(self, ticket):
        """Get a specific ticket"""
        return self.client.issue(ticket)

    def get_all_open_issues(self) -> List:
        """Get all open issues assigned to the current user."""
        jql = """
assignee = currentUser()
AND status NOT IN (Closed, Done, Rejected, Resolved, "Deployed to production")
AND type IN (Sub-task, Subtask)
ORDER BY created DESC
        """
        try:
            open_issues = self.client.search_issues(jql)
            logger.info(f"Retrieved {len(open_issues)} open issues")
            return open_issues
        except Exception as e:
            logger.error(f"Failed to retrieve open issues: {e}")
            return []

    def get_all_open_bugs(self) -> List:
        """Get all open bugs assigned to the current user."""
        jql = """
assignee = currentUser()
AND status NOT IN (Closed, Done, Rejected, Resolved, "Deployed to production")
AND type IN (Bug, "Implementation bug")
ORDER BY created DESC
        """
        try:
            open_bugs = self.client.search_issues(jql)
            logger.info(f"Retrieved {len(open_bugs)} open bugs")
            return open_bugs
        except Exception as e:
            logger.error(f"Failed to retrieve open bugs: {e}")
            return []

    def get_user_tasks_due_soon(self, user_jira_id: str) -> List:
        """Get all open tasks assigned to a specific user that are due today or tomorrow."""
        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)

        # Format dates for JQL (YYYY-MM-DD)
        today_str = today.strftime("%Y-%m-%d")
        tomorrow_str = tomorrow.strftime("%Y-%m-%d")

        jql = f"""
assignee = {user_jira_id}
AND status NOT IN (Closed, Done, Rejected, Resolved, "Deployed to production")
AND "end date[date]" >= {today_str}
AND "end date[date]" <= {tomorrow_str}
ORDER BY "end date[date]" ASC, priority DESC
        """
        try:
            due_tasks = self.client.search_issues(jql, expand="changelog")
            logger.info(
                f"Retrieved {len(due_tasks)} tasks due today or tomorrow for user {user_jira_id}"
            )
            return due_tasks
        except Exception as e:
            logger.error(f"Failed to retrieve due tasks for user {user_jira_id}: {e}")
            return []

    def get_task_end_date(self, task) -> Optional[str]:
        """Get the end date from a JIRA task's custom field."""
        try:
            # The "End date" field corresponds to customfield_11145
            return task.raw["fields"].get("customfield_11145")
        except Exception as e:
            logger.error(f"Error accessing end date for task {task.key}: {e}")
            return None

    def get_all_users_tasks_due_soon(self, user_jira_ids: List[str]) -> dict:
        """Get all open tasks due today or tomorrow for multiple users."""
        all_due_tasks = {}

        for user_id in user_jira_ids:
            logger.debug(f"Checking due tasks for user: {user_id}")
            user_tasks = self.get_user_tasks_due_soon(user_id)

            # Validate that user_tasks is indeed a list
            if not isinstance(user_tasks, list):
                logger.error(
                    f"get_user_tasks_due_soon returned invalid type {type(user_tasks)} for user {user_id}: {user_tasks}"
                )
                user_tasks = []  # Fallback to empty list

            if user_tasks:
                all_due_tasks[user_id] = user_tasks
                logger.info(f"Found {len(user_tasks)} due tasks for user {user_id}")
            else:
                logger.debug(f"No due tasks found for user {user_id}")

        logger.debug(f"Returning due tasks dictionary with {len(all_due_tasks)} users")
        return all_due_tasks

    async def change_status_async(self, issue, new_status: str) -> bool:
        """Async version of change_status using thread pool."""
        loop = asyncio.get_event_loop()
        try:
            result = await asyncio.wait_for(
                loop.run_in_executor(
                    self.executor, self.change_status, issue, new_status
                ),
                timeout=15.0,  # 15 second timeout for status changes
            )
            return result
        except asyncio.TimeoutError:
            logger.error(f"Timeout changing status for {issue.key} to {new_status}")
            return False
        except Exception as e:
            logger.error(f"Error in async status change for {issue.key}: {e}")
            return False

    def change_status(self, issue, new_status: str) -> bool:
        """Change the status of an issue or bug."""

        # Determine issue type
        issue_type = issue.fields.issuetype.name.lower()
        is_bug = issue_type in ["bug", "implementation bug"]
        is_story = issue_type in ["story"]

        if is_bug:
            # Define the transition workflow for bugs
            transition_workflow = [
                {
                    "from_status": "Open",
                    "transition": "Move to Back Log",
                    "to_status": "Backlog",
                },
                {
                    "from_status": "Backlog",
                    "transition": "Start Development",
                    "to_status": "In Progress",
                },
                {
                    "from_status": "In Progress",
                    "transition": "Move for code review",
                    "to_status": "In Review",
                },
                {
                    "from_status": "In Review",
                    "transition": "Code review submission",
                    "to_status": "Performing DevTesing",
                },
                {
                    "from_status": "Performing DevTesing",
                    "transition": "Moved for QA",
                    "to_status": "Resolved",
                },
            ]
        elif is_story:
            # Define the transition workflow for stories
            transition_workflow = [
                {
                    "from_status": "Handshake Done",
                    "transition": "Start progress",
                    "to_status": "In Progress",
                },
                {
                    "from_status": "In Progress",
                    "transition": "Developer level testing",
                    "to_status": "Dev Testing",
                },
                {
                    "from_status": "Dev Testing",
                    "transition": "Resolve Issue",
                    "to_status": "Resolved",
                },
            ]
        else:
            # Define the transition workflow for regular issues
            transition_workflow = [
                {
                    "from_status": "Open",
                    "transition": "Select for Development",
                    "to_status": "Handshake Done",
                },
                {
                    "from_status": "Handshake Done",
                    "transition": "Start Progress",
                    "to_status": "In Progress",
                },
                {
                    "from_status": "In Progress",
                    "transition": "Move for code review",
                    "to_status": "In Review",
                },
                {
                    "from_status": "In Review",
                    "transition": "Developer Testing",
                    "to_status": "Dev Testing",
                },
                {
                    "from_status": "Dev Testing",
                    "transition": "Move to Done",
                    "to_status": "Done",
                },
                {
                    "from_status": "Dev Testing",
                    "transition": "Developer level testing - Reopen",
                    "to_status": "In Progress",
                },
                {
                    "from_status": "In Progress",
                    "transition": "Move for code review",
                    "to_status": "In Review",
                },
            ]

        try:
            current_status = issue.fields.status.name
            logger.info(f"Current status of {issue.key}: {current_status}")

            # Get available transitions
            transitions = self.client.transitions(issue)
            available_transitions = {t["name"].lower(): t["id"] for t in transitions}
            available_names = [t["name"] for t in transitions]

            logger.info(f"Available transitions: {available_names}")

            # Find the path from current status to target status
            path = self._find_transition_path(
                current_status, new_status, transition_workflow
            )

            if not path:
                logger.error(f"No path found from {current_status} to {new_status}")
                return False

            # Execute each transition in the path
            for step in path:
                transition_name = step["transition"]

                # Check if this transition is available
                if transition_name.lower() not in available_transitions:
                    logger.error(f"Transition '{transition_name}' not available")
                    logger.info(f"Available transitions: {available_names}")
                    return False

                # Perform the transition
                transition_id = available_transitions[transition_name.lower()]
                self.client.transition_issue(issue, transition_id)
                logger.info(
                    f"Issue {issue.key} transitioned using '{transition_name}' to '{step['to_status']}'"
                )

                # Refresh issue and get new available transitions for next step
                if step != path[-1]:  # Don't refresh on the last step
                    issue = self.client.issue(issue.key)
                    transitions = self.client.transitions(issue)
                    available_transitions = {
                        t["name"].lower(): t["id"] for t in transitions
                    }
                    available_names = [t["name"] for t in transitions]

            logger.info(f"Issue {issue.key} successfully transitioned to {new_status}")
            return True

        except Exception as e:
            logger.error(f"Failed to transition issue {issue.key} to {new_status}: {e}")
            return False

    def _find_transition_path(
        self, current_status: str, target_status: str, workflow: List[dict]
    ) -> List[dict]:
        """Find the sequence of transitions needed to go from current status to target status."""
        # If already at target status, no transitions needed
        if current_status.lower() == target_status.lower():
            logger.info(f"Already at target status: {target_status}")
            return []

        path = []
        current = current_status

        # Follow the workflow until we reach the target or can't proceed
        for _ in range(len(workflow)):  # Prevent infinite loops
            # Find the next transition from current status
            next_step = None
            for step in workflow:
                if step["from_status"].lower() == current.lower():
                    next_step = step
                    break

            if not next_step:
                logger.warning(f"No transition found from status: {current}")
                break

            path.append(next_step)
            current = next_step["to_status"]

            # Check if we've reached the target
            if current.lower() == target_status.lower():
                logger.info(
                    f"Found path to {target_status}: {[s['transition'] for s in path]}"
                )
                return path

        logger.warning(
            f"Could not find complete path from {current_status} to {target_status}"
        )
        return []


class JIRAWatcher:
    """Manages JIRA ticket watching and change detection using SQLite."""

    def __init__(self, jira_client: JIRA, db_manager: DatabaseManager):
        self.jira = jira_client
        self.db = db_manager

    async def add_watcher_async(self, ticket_id: str, user: discord.User) -> bool:
        """Add a user to watch a specific ticket (async version)."""
        logger.debug(
            f"Attempting to add watcher for ticket {ticket_id} by user {user.id}"
        )
        # First, try to fetch the ticket to validate it exists
        try:
            issue = await self.jira.get_issue_async(ticket_id, timeout=10.0)
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

        except asyncio.TimeoutError:
            logger.error(f"Timeout adding watcher for {ticket_id}")
            return False
        except Exception as e:
            logger.error(f"Failed to add watcher for {ticket_id}: {str(e)}")
            logger.debug(
                f"Add watcher error details for user {user.id}:", exc_info=True
            )
            return False

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

        # Process tickets in smaller batches to prevent blocking
        batch_size = 5
        for i in range(0, len(watched_tickets), batch_size):
            batch = watched_tickets[i : i + batch_size]

            # Process batch with timeout
            batch_tasks = []
            for ticket_id in batch:
                task = asyncio.create_task(
                    self._check_single_ticket(ticket_id, bot_client)
                )
                batch_tasks.append(task)

            # Wait for batch completion with overall timeout
            try:
                batch_results = await asyncio.wait_for(
                    asyncio.gather(*batch_tasks, return_exceptions=True),
                    timeout=30.0,  # 30 second timeout for entire batch
                )

                # Collect successful results
                for result in batch_results:
                    if isinstance(result, list):
                        notifications.extend(result)
                    elif isinstance(result, Exception):
                        logger.error(f"Error in batch processing: {result}")

            except asyncio.TimeoutError:
                logger.error(f"Batch processing timed out for tickets: {batch}")
                # Cancel remaining tasks
                for task in batch_tasks:
                    if not task.done():
                        task.cancel()

            # Small delay between batches to prevent overwhelming JIRA
            if i + batch_size < len(watched_tickets):
                await asyncio.sleep(1)

        return notifications

    async def _check_single_ticket(
        self, ticket_id: str, bot_client: discord.Client
    ) -> List[Dict]:
        """Check a single ticket for changes."""
        notifications = []
        try:
            # Fetch current state from JIRA with timeout
            issue = await self.jira.get_issue_async(ticket_id, timeout=8.0)
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

        except asyncio.TimeoutError:
            logger.error(f"Timeout checking ticket {ticket_id}")
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


class JIRAWatcherBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="/", intents=discord.Intents.all())

    async def setup_hook(self):
        # Sync the command tree
        try:
            synced = await self.tree.sync()
            print(f"Synced {len(synced)} command(s)")
        except Exception as e:
            print(f"Failed to sync commands: {e}")
