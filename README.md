# JIRA Status Updater

An automated tool that synchronizes JIRA issue statuses based on Git branch and Pull Request states in Bitbucket.

## Features

- Automatically updates JIRA issue statuses based on development progress
- Logs all activities with proper logging levels
- Supports multiple repositories
- Type-safe implementation with proper error handling

## Status Logic

The tool updates JIRA issues according to the following rules:

1. **No branch exists**: Keep current status
2. **Branch exists + PR merged**: Set status to "Dev Testing"
3. **Branch exists + PR open**: Set status to "In Review"
4. **Branch exists + No PR**: Set status to "In Progress"

## Setup

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Create a `.env` file with the following variables:
   ```
   ATLASSIAN_URL=https://your-domain.atlassian.net
   ATLASSIAN_EMAIL=your-email@domain.com
   JIRA_TOKEN=your-jira-token
   BITBUCKET_TOKEN=your-bitbucket-token
   BITBUCKET_WORKSPACE=your-workspace-name
   ```

3. Run the script:
   ```bash
   python main.py
   ```

## Configuration

### Repositories

Edit the `repos` list in `main.py` to specify which repositories to check:

```python
repos = [
    "dsp-customers-web",
    "applift-lib",
    "applift-app",
    # Add more repositories as needed
]
```

### Logging

Logs are written to both console and `jira_status_updater.log` file. Log levels can be adjusted in the logging configuration.

## Requirements

- Python 3.7+
- JIRA API access
- Bitbucket API access
- Valid authentication tokens

## File Structure

```
.
├── main.py                 # Main application logic
├── utils/
│   ├── jira.py            # JIRA API client
│   └── bitbucket.py       # Bitbucket API client
├── requirements.txt       # Python dependencies
├── .env                   # Environment variables (create this)
├── .gitignore            # Git ignore rules
└── README.md             # This file
```
