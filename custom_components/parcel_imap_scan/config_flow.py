"""Config flow for Parcel IMAP Scan."""
from __future__ import annotations

import imaplib
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

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
)

_LOGGER = logging.getLogger(__name__)

DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_EMAIL): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Optional(CONF_IMAP_SERVER, default=DEFAULT_IMAP_SERVER): str,
        vol.Optional(CONF_IMAP_PORT, default=DEFAULT_IMAP_PORT): int,
        vol.Optional(CONF_FOLDER, default=DEFAULT_FOLDER): str,
        vol.Optional(CONF_DAYS_BACK, default=DEFAULT_DAYS_BACK): int,
        vol.Optional(CONF_TODO_ENTITY, default=DEFAULT_TODO_ENTITY): str,
    }
)


def _test_connection(email_addr: str, password: str, server: str, port: int) -> None:
    """Blocking IMAP login test; run inside executor."""
    conn = imaplib.IMAP4_SSL(server, port)
    try:
        conn.login(email_addr, password)
    finally:
        try:
            conn.logout()
        except Exception:  # noqa: BLE001
            pass


class ParcelImapScanConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Parcel IMAP Scan."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await self.hass.async_add_executor_job(
                    _test_connection,
                    user_input[CONF_EMAIL],
                    user_input[CONF_PASSWORD],
                    user_input[CONF_IMAP_SERVER],
                    user_input[CONF_IMAP_PORT],
                )
            except imaplib.IMAP4.error:
                errors["base"] = "invalid_auth"
            except (OSError, HomeAssistantError):
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error testing IMAP connection")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(user_input[CONF_EMAIL])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=user_input[CONF_EMAIL], data=user_input
                )

        return self.async_show_form(
            step_id="user", data_schema=DATA_SCHEMA, errors=errors
        )
