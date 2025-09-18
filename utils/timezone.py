import pytz
from datetime import datetime

# Define IST timezone
IST = pytz.timezone("Asia/Kolkata")


def get_ist_now():
    """Get current datetime in IST timezone."""
    return datetime.now(IST)


def convert_to_ist(dt):
    """Convert datetime to IST timezone."""
    if dt.tzinfo is None:
        # If datetime is naive, assume it's UTC
        dt = pytz.UTC.localize(dt)
    return dt.astimezone(IST)


def format_ist_datetime(dt, format_string="%Y-%m-%d %H:%M:%S %Z"):
    """Format datetime in IST timezone."""
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    ist_dt = dt.astimezone(IST)
    return ist_dt.strftime(format_string)
