import logging
from typing import List, Optional, Dict, Any
import httpx

logger = logging.getLogger(__name__)


class Bitbucket:
    def __init__(self, email: str, token: str, workspace: str):
        self.email = email
        self.token = token
        self.host = "https://api.bitbucket.org/2.0"
        self.workspace = workspace
        logger.info(f"Initialized Bitbucket client for workspace: {workspace}")

    def check_connection(self) -> bool:
        """Check connection to Bitbucket API."""
        try:
            response = httpx.get(
                f"{self.host}/user",
                auth=(self.email, self.token),
            )
            response.raise_for_status()
            logger.info("Bitbucket connection successful")
            return True
        except httpx.HTTPError as e:
            logger.error(f"Bitbucket connection error: {e}")
            return False

    def find_branch(self, repo_name: str, ticket: str) -> Optional[str]:
        """Find a branch matching the ticket name in the specified repository."""
        url = f'{self.host}/repositories/{self.workspace}/{repo_name}/refs/branches?q=name~"{ticket}"'
        try:
            response = httpx.get(url, auth=(self.email, self.token))
            response.raise_for_status()
            data = response.json()

            if data.get("values"):
                branch_name = data["values"][0]["name"]
                logger.debug(
                    f"Found branch '{branch_name}' for ticket {ticket} in {repo_name}"
                )
                return branch_name
            else:
                logger.debug(f"No branch found for ticket {ticket} in {repo_name}")
                return None

        except httpx.HTTPError as e:
            logger.error(f"Error fetching branches from {repo_name}: {e}")
            return None

    def find_prs(self, repo_name: str, ticket: str) -> List[Dict[str, Any]]:
        """Find pull requests matching the ticket name in the specified repository."""
        url = f'{self.host}/repositories/{self.workspace}/{repo_name}/pullrequests?q=title~"{ticket}"'
        try:
            response = httpx.get(url, auth=(self.email, self.token))
            response.raise_for_status()
            data = response.json()

            prs = data.get("values", [])
            if prs:
                logger.debug(f"Found {len(prs)} PRs for ticket {ticket} in {repo_name}")
            else:
                logger.debug(f"No PRs found for ticket {ticket} in {repo_name}")

            return prs

        except httpx.HTTPError as e:
            logger.error(f"Error fetching pull requests from {repo_name}: {e}")
            return []
