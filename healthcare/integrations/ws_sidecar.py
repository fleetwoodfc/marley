"""
DICOM UPS Event WebSocket Sidecar.

Async process that maintains a persistent WebSocket connection to dcm4chee-arc
and forwards UPS state-change events to the Frappe realtime layer
(frappe.publish_realtime / socket.io).

Usage (via Procfile or direct invocation):

    python -m healthcare.integrations.ws_sidecar

The process:
1. Reads UPS Integration Settings to get the dcm4chee-arc base URL + credentials.
2. Calls DICOMwebClient.subscribe_global() to obtain the WebSocket URL.
3. Connects via websockets and listens for DICOM+JSON event frames.
4. Parses each event and calls frappe.publish_realtime() via the Frappe HTTP API.
5. On disconnect, retries with exponential back-off (max 64 s).
6. Exits cleanly on SIGTERM / KeyboardInterrupt.

See research.md §4 for context.
"""

import asyncio
import json
import logging
import os
import signal
import sys

# Frappe's logger writes to ../logs/<module>.log relative to cwd.
# That path is only correct when cwd is <bench>/sites/ (how bench workers run).
# The sidecar runs from the bench root, so ../logs/ would point to the *parent*
# of the bench — a directory that typically doesn't exist.
# Setting FRAPPE_STREAM_LOGGING before any frappe import makes Frappe skip its
# file handlers and log to stderr only, letting our own logger handle output.
os.environ.setdefault("FRAPPE_STREAM_LOGGING", "1")

logger = logging.getLogger("ups_ws_sidecar")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [ups_ws_sidecar] %(levelname)s %(message)s",
)

# ---------------------------------------------------------------------------
# Guard: bail out immediately if sync is disabled
# ---------------------------------------------------------------------------


def _check_sync_enabled():
    """Return False and log if UPS sync is disabled, so the process exits."""
    try:
        import frappe  # noqa: PLC0415

        frappe.init(site=_get_site(), sites_path=_get_sites_path())
        frappe.connect()
        settings = frappe.get_single("UPS Integration Settings")
        enabled = bool(settings.enable_ups_sync)
        frappe.destroy()
        return enabled
    except Exception as exc:
        logger.error("Could not read UPS Integration Settings: %s", exc)
        return False


def _get_site():
    """Resolve the Frappe site name from env or bench default."""
    return os.environ.get("FRAPPE_SITE", "development.localhost")


def _get_sites_path():
    """
    Resolve the Frappe sites directory.

    frappe.init() defaults sites_path to ".", which expects site directories
    to live directly in the cwd.  A standard bench layout puts them under
    ``<bench>/sites/``, so we default to "sites" (relative to the bench root
    where honcho/Procfile runs) and allow override via FRAPPE_SITES_PATH.
    """
    return os.environ.get("FRAPPE_SITES_PATH", "sites")


# ---------------------------------------------------------------------------
# Realtime bridge: push event to Frappe via socket.io publish
# ---------------------------------------------------------------------------


def _publish_via_frappe(event_data: dict):
    """
    Call frappe.publish_realtime on the Frappe server.

    In production this can use frappe.publish_realtime() directly when the
    sidecar runs inside the Frappe worker process.  For an out-of-process
    sidecar we call the Frappe whitelisted helper via HTTP.

    For simplicity and reliability, this implementation calls the Frappe
    internal publish method via a short-lived frappe context.
    """
    try:
        import frappe  # noqa: PLC0415

        frappe.init(site=_get_site(), sites_path=_get_sites_path())
        frappe.connect()
        frappe.publish_realtime(
            "ups_state_change",
            event_data,
            room="ups_dashboard",
        )
        frappe.destroy()
    except Exception as exc:
        logger.error("Failed to publish realtime event: %s", exc)


# ---------------------------------------------------------------------------
# Event parser
# ---------------------------------------------------------------------------


def _parse_ups_event(raw_frame: str) -> dict | None:
    """
    Parse a raw DICOM+JSON WebSocket event frame from dcm4chee-arc.

    Returns a dict suitable for frappe.publish_realtime, or None if the
    frame cannot be parsed.

    Expected frame structure (DICOM+JSON wrapped in UPS event):
        [{ "00001000": { "vr": "UI", "Value": ["<ups_uid>"] },
           "00741000": { "vr": "CS", "Value": ["IN PROGRESS"] }, ... }]
    """
    try:
        datasets = json.loads(raw_frame)
        if not datasets:
            return None
        ds = datasets[0] if isinstance(datasets, list) else datasets
        ups_uid = (ds.get("00001000") or {}).get("Value", [None])[0]
        ups_state = (ds.get("00741000") or {}).get("Value", [None])[0]
        event_type = (ds.get("00000100") or {}).get("Value", [None])[0]  # CommandField
        if not ups_uid:
            return None
        return {
            "ups_instance_uid": ups_uid,
            "new_state": ups_state,
            "event_type": event_type,
            "raw": ds,
        }
    except (json.JSONDecodeError, AttributeError, TypeError) as exc:
        logger.warning("Could not parse UPS event frame: %s", exc)
        return None


# ---------------------------------------------------------------------------
# WebSocket connection loop
# ---------------------------------------------------------------------------


async def _run_sidecar():
    """Main coroutine: subscribe and process events with reconnect logic."""
    try:
        import websockets  # noqa: PLC0415
    except ImportError:
        logger.error(
            "websockets package is not installed. "
            "Install with: pip install websockets"
        )
        return

    backoff = 1  # seconds (shared for both subscription and WebSocket retries)
    max_backoff = 64
    ws_url = None

    while ws_url is None:
        try:
            import frappe  # noqa: PLC0415

            frappe.init(site=_get_site(), sites_path=_get_sites_path())
            frappe.connect()
            try:
                from healthcare.integrations.dicomweb_client import DICOMwebClient  # noqa: PLC0415

                ws_url = DICOMwebClient().subscribe_global()
            finally:
                frappe.destroy()

            if not ws_url:
                logger.error(
                    "subscribe_global() returned no WebSocket URL. "
                    "Check dcm4chee-arc configuration. Retrying in %ds…", backoff
                )
                ws_url = None
                raise ValueError("No WebSocket URL returned")

            logger.info("Subscribed to dcm4chee-arc global worklist. WS URL: %s", ws_url)
        except asyncio.CancelledError:
            return
        except Exception as exc:
            logger.error("Failed to subscribe to dcm4chee-arc: %s. Retrying in %ds…", exc, backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)

    backoff = 1  # reset after successful subscription

    while True:
        try:
            async with websockets.connect(ws_url) as ws:
                logger.info("WebSocket connected")
                backoff = 1  # reset on successful connect
                async for message in ws:
                    event = _parse_ups_event(message)
                    if event:
                        logger.debug(
                            "UPS event: uid=%s state=%s",
                            event.get("ups_instance_uid"),
                            event.get("new_state"),
                        )
                        _publish_via_frappe(event)

        except (
            websockets.exceptions.ConnectionClosed,
            websockets.exceptions.WebSocketException,
            ConnectionRefusedError,
            OSError,
        ) as exc:
            logger.warning(
                "WebSocket disconnected (%s). Retrying in %ds…", exc, backoff
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, max_backoff)

        except asyncio.CancelledError:
            logger.info("Sidecar shutting down.")
            break


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    # Poll until sync is enabled (or a shutdown signal is received).
    # Staying alive prevents honcho from killing all other bench processes.
    _shutdown_requested = [False]

    def _early_shutdown(signum, frame):
        logger.info("Received signal %s — shutting down ws_sidecar.", signum)
        _shutdown_requested[0] = True

    signal.signal(signal.SIGTERM, _early_shutdown)
    signal.signal(signal.SIGINT, _early_shutdown)

    while not _check_sync_enabled():
        if _shutdown_requested[0]:
            logger.info("ws_sidecar stopped before sync was enabled.")
            return
        logger.info(
            "UPS sync is disabled in UPS Integration Settings. "
            "Checking again in 60 s…"
        )
        import time  # noqa: PLC0415
        time.sleep(60)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    main_task = loop.create_task(_run_sidecar())

    def _shutdown(signum, frame):
        logger.info("Received signal %s — shutting down ws_sidecar.", signum)
        main_task.cancel()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    try:
        loop.run_until_complete(main_task)
    except (asyncio.CancelledError, SystemExit):
        pass
    finally:
        loop.close()
        logger.info("ws_sidecar stopped.")


if __name__ == "__main__":
    main()
