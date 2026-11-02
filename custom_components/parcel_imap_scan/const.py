"""Constants for the Parcel IMAP Scan integration."""

DOMAIN = "parcel_imap_scan"

CONF_EMAIL = "email"
CONF_PASSWORD = "password"
CONF_IMAP_SERVER = "imap_server"
CONF_IMAP_PORT = "imap_port"
CONF_FOLDER = "folder"
CONF_DAYS_BACK = "days_back"
CONF_TODO_ENTITY = "todo_entity"

DEFAULT_IMAP_SERVER = "imap.gmail.com"
DEFAULT_IMAP_PORT = 993
DEFAULT_FOLDER = "INBOX"
DEFAULT_DAYS_BACK = 90
DEFAULT_TODO_ENTITY = "todo.parcels"

SERVICE_SCAN_NOW = "scan_now"
EVENT_SCAN_COMPLETE = f"{DOMAIN}_scan_complete"
