import logging
import os
from datetime import datetime

# Create logs directory if it doesn't exist
os.makedirs("logs", exist_ok=True)


# Custom formatter for detailed logging
class DetailedFormatter(logging.Formatter):
    """Custom formatter that provides detailed formatting with colors and context."""

    def format(self, record):
        # Add timestamp with milliseconds
        timestamp = datetime.fromtimestamp(record.created).strftime(
            "%Y-%m-%d %H:%M:%S.%f"
        )[:-3]

        # Create detailed format
        log_format = (
            f"[{timestamp}] "
            f"[{record.levelname:8}] "
            f"[{record.name}:{record.lineno}] "
            f"[PID:{os.getpid()}] "
            f"{record.getMessage()}"
        )

        # Add exception info if present
        if record.exc_info:
            log_format += f"\nException: {self.formatException(record.exc_info)}"

        return log_format


# Configure logging to write only to file with detailed format
logging.basicConfig(
    level=logging.DEBUG,  # Set to DEBUG for maximum detail
    handlers=[
        logging.FileHandler("all.log", mode="a", encoding="utf-8"),
    ],
    format="%(message)s",  # We'll use our custom formatter
)

# Set up our custom formatter
logger = logging.getLogger(__name__)
for handler in logging.root.handlers:
    handler.setFormatter(DetailedFormatter())

# Add separation line for new session
session_start = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
with open("log.txt", "a", encoding="utf-8") as f:
    f.write(f"\n{'='*80}\n")
    f.write(f"New session started at {session_start}\n")
    f.write(f"Process ID: {os.getpid()}\n")
    f.write(f"{'='*80}\n\n")
