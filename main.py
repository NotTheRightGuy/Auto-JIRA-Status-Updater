import logging
import os
from typing import List
from dotenv import load_dotenv
from utils.jira import JIRA
from utils.bitbucket import Bitbucket
from logs.logger import logger
from utils.helper import process_issue

load_dotenv()


def main() -> None:
    """Main function to process all open JIRA issues."""
    logger.info("Starting JIRA status updater")

    # Initialize clients
    try:
        jira = JIRA(
            host=os.getenv("ATLASSIAN_URL"),
            email=os.getenv("ATLASSIAN_EMAIL"),
            token=os.getenv("JIRA_TOKEN"),
        )

        bitbucket = Bitbucket(
            email=os.getenv("ATLASSIAN_EMAIL"),
            token=os.getenv("BITBUCKET_TOKEN"),
            workspace=os.getenv("BITBUCKET_WORKSPACE"),
        )

        logger.info("Successfully initialized JIRA and Bitbucket clients")
    except Exception as e:
        logger.error(f"Failed to initialize clients: {e}")
        return

    repos = [
        "applift-lib",
        "applift-app",
        "dsp-customers-web",
        "dsp-campaign-builder-web",
        "dsp-audience-builder-web",
    ]

    logger.info(f"Checking repositories: {', '.join(repos)}")

    try:
        # Process regular issues
        open_issues = jira.get_all_open_issues()
        logger.info(f"Found {len(open_issues)} open issues to process")

        for issue in open_issues:
            process_issue(jira, bitbucket, issue, repos)
            logger.info("-" * 50)  # Separator between issues

        # Process bugs
        open_bugs = jira.get_all_open_bugs()
        logger.info(f"Found {len(open_bugs)} open bugs to process")

        for bug in open_bugs:
            process_issue(jira, bitbucket, bug, repos)
            logger.info("-" * 50)  # Separator between bugs

    except Exception as e:
        logger.error(f"Error processing issues and bugs: {e}")
        return


if __name__ == "__main__":
    main()
