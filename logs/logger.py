import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("jira_status_updater.log"), logging.StreamHandler()],
)

logger = logging.getLogger(__name__)
