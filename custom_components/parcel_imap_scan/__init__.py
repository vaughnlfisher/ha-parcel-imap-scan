"""Parcel IMAP Scan: full-mailbox tracking-number backfill for Home Assistant.

Unlike the core `imap` integration, this component is designed for an
on-demand historical scan (not just a forward-looking "new mail" watch):
call the `parcel_imap_scan.scan_now` service and it searches the whole
configured window of the mailbox with plain stdlib `imaplib` (avoiding the
third-party `imapclient` package's Python 3.14 bug), extracts tracking
numbers, and adds any not already present to a to-do list.
"""
from __future__ import annotations

import email
import imaplib
import logging
import re
from datetime import datetime, timedelta
from email.header import decode_header
from email.message import Message

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import (
    CONF_DAYS_BACK,
    CONF_EMAIL,
    CONF_FOLDER,
    CONF_IMAP_PORT,
    CONF_IMAP_SERVER,
    CONF_PASSWORD,
    CONF_TODO_ENTITY,
    DEFAULT_DAYS_BACK,
    DEFAULT_FOLDER,
    DEFAULT_IMAP_PORT,
    DEFAULT_IMAP_SERVER,
    DEFAULT_TODO_ENTITY,
    DOMAIN,
    EVENT_SCAN_COMPLETE,
    SERVICE_SCAN_NOW,
)
from .extract import extract_tracking

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[str] = ["button"]

SCAN_SCHEMA = vol.Schema(
    {
        vol.Optional("days_back"): vol.Coerce(int),
        vol.Optional("entry_id"): cv.string,
    }
)


def _decode_header_value(value: str | None) -> str:
    if not value:
        return ""
    decoded = ""
    for text, enc in decode_header(value):
        if isinstance(text, bytes):
            decoded += text.decode(enc or "utf-8", errors="replace")
        else:
            decoded += text
    return decoded


_TAG_RE = re.compile(r"<[^>]+>")
_HREF_RE = re.compile(r'href\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
_WS_RE = re.compile(r"[ \t]+")


def _html_to_text(html: str) -> str:
    """Crude HTML-to-text fallback: surface href URLs and strip tags.

    Many retail/shipping emails (Amazon, AliExpress, and others) are HTML-only
    or have a near-empty plain-text alternative, with the actual tracking
    number only present as link text or inside an href query string (e.g.
    "...tracking.../TBA123456789012" or "...?trackingNumber=1Z...."). Keeping
    href targets in the extracted text lets the existing regexes in
    extract.py still find those numbers.
    """
    if not html:
        return ""
    hrefs = " ".join(_HREF_RE.findall(html))
    # Drop script/style blocks entirely so their content never leaks into the haystack.
    html = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", html)
    text = _TAG_RE.sub(" ", html)
    text = text.replace("&nbsp;", " ").replace("&amp;", "&")
    text = _WS_RE.sub(" ", text)
    return f"{text}\n{hrefs}"


def _extract_body(msg: Message) -> str:
    if msg.is_multipart():
        plain_parts: list[str] = []
        html_parts: list[str] = []
        for part in msg.walk():
            if part.get_filename():
                continue
            content_type = part.get_content_type()
            if content_type not in ("text/plain", "text/html"):
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            decoded = payload.decode(
                part.get_content_charset() or "utf-8", errors="replace"
            )
            if content_type == "text/plain":
                plain_parts.append(decoded)
            else:
                html_parts.append(_html_to_text(decoded))
        # Always include both: a sparse plain-text alternative (common in
        # marketing-styled shipping emails) means the tracking number may
        # only be recoverable from the HTML part's link text/hrefs.
        return "\n".join(plain_parts + html_parts)
    payload = msg.get_payload(decode=True)
    if not payload:
        return ""
    decoded = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    if msg.get_content_type() == "text/html":
        return _html_to_text(decoded)
    return decoded


def _scan_mailbox(
    email_addr: str,
    password: str,
    server: str,
    port: int,
    folder: str,
    days_back: int,
) -> list[dict[str, str]]:
    """Blocking full-mailbox IMAP scan. Must run inside the executor."""
    results: list[dict[str, str]] = []
    conn = imaplib.IMAP4_SSL(server, port)
    try:
        conn.login(email_addr, password)
        conn.select(folder)
        since = (datetime.now() - timedelta(days=days_back)).strftime("%d-%b-%Y")
        status, data = conn.search(None, f'(SINCE "{since}")')
        if status != "OK" or not data or not data[0]:
            _LOGGER.warning("Parcel IMAP Scan: search returned no messages (status=%s)", status)
            return results
        uids = data[0].split()
        _LOGGER.info("Parcel IMAP Scan: scanning %d messages since %s", len(uids), since)
        for uid in uids:
            status, msg_data = conn.fetch(uid, "(RFC822)")
            if status != "OK" or not msg_data or msg_data[0] is None:
                continue
            raw = msg_data[0][1]
            if not isinstance(raw, (bytes, bytearray)):
                continue
            msg = email.message_from_bytes(raw)
            subject = _decode_header_value(msg.get("Subject"))
            sender = _decode_header_value(msg.get("From"))
            try:
                body = _extract_body(msg)
            except Exception:  # noqa: BLE001
                body = ""
            for carrier, number in extract_tracking(subject, sender, body):
                results.append(
                    {
                        "carrier": carrier,
                        "tracking_number": number,
                        "sender": sender,
                        "subject": subject,
                    }
                )
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass
    return results


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Parcel IMAP Scan from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = entry.data

    async def handle_scan_now(call: ServiceCall) -> None:
        entry_id = call.data.get("entry_id") or entry.entry_id
        conf = hass.data[DOMAIN].get(entry_id, entry.data)
        days_back = call.data.get("days_back", conf.get(CONF_DAYS_BACK, DEFAULT_DAYS_BACK))
        todo_entity = conf.get(CONF_TODO_ENTITY, DEFAULT_TODO_ENTITY)

        matches = await hass.async_add_executor_job(
            _scan_mailbox,
            conf[CONF_EMAIL],
            conf[CONF_PASSWORD],
            conf.get(CONF_IMAP_SERVER, DEFAULT_IMAP_SERVER),
            conf.get(CONF_IMAP_PORT, DEFAULT_IMAP_PORT),
            conf.get(CONF_FOLDER, DEFAULT_FOLDER),
            days_back,
        )

        existing_response = await hass.services.async_call(
            "todo",
            "get_items",
            {"status": "needs_action"},
            target={"entity_id": todo_entity},
            blocking=True,
            return_response=True,
        )
        existing_items = (existing_response or {}).get(todo_entity, {}).get("items", [])
        existing_summaries = " ".join(item.get("summary", "") for item in existing_items)

        added = 0
        for m in matches:
            if m["tracking_number"] in existing_summaries:
                continue
            await hass.services.async_call(
                "todo",
                "add_item",
                {
                    "item": f"{m['carrier']}: {m['tracking_number']}",
                    "description": (
                        f"From: {m['sender']} | Subject: {m['subject']} | "
                        "Backfilled by Parcel IMAP Scan"
                    ),
                },
                target={"entity_id": todo_entity},
                blocking=True,
            )
            existing_summaries += f" {m['tracking_number']}"
            added += 1

        _LOGGER.info(
            "Parcel IMAP Scan: found %d tracking number(s) across the scan, added %d new",
            len(matches),
            added,
        )
        hass.bus.async_fire(
            EVENT_SCAN_COMPLETE, {"found": len(matches), "added": added, "days_back": days_back}
        )

    if not hass.services.has_service(DOMAIN, SERVICE_SCAN_NOW):
        hass.services.async_register(DOMAIN, SERVICE_SCAN_NOW, handle_scan_now, schema=SCAN_SCHEMA)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if not hass.data[DOMAIN]:
            hass.services.async_remove(DOMAIN, SERVICE_SCAN_NOW)
    return unload_ok
