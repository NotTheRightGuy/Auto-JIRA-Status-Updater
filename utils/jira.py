import logging
from typing import List, Optional
from jira import JIRA as jira_client

logger = logging.getLogger(__name__)


class JIRA:
    def __init__(self, host: str, email: str, token: str):
        self.host = host
        self.email = email
        self.token = token
        self.client = jira_client(server=self.host, basic_auth=(self.email, self.token))
        logger.info(f"Initialized JIRA client for {host}")
        self.transitions = {}

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
            # Check if this issue has a parent
            if hasattr(issue.fields, "parent") and issue.fields.parent:
                parent_key = issue.fields.parent.key
                parent_issue = self.client.issue(parent_key)
                logger.info(f"Found parent issue {parent_key} for {issue.key}")
                return parent_issue
            else:
                logger.debug(f"No parent issue found for {issue.key}")
                return None
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
                    "transition": "Start Progress",
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
