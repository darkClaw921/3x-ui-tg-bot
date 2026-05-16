"""Standalone smoke test for the 3x-ui REST client.

Runs end-to-end against a real (or staging) 3x-ui panel:

1. ``XuiClient.login()``
2. ``list_inbounds()`` — prints inbound count.
3. ``get_inbound(XUI_INBOUND_ID)`` — prints port, protocol, current clients.
4. ``add_client(...)`` — provisions a throw-away client with 10-minute expiry.
5. ``get_client_traffics(email)`` — verifies the client is visible.
6. ``del_client(...)`` — cleans up (unless ``--keep`` was passed).

Usage::

    # All .env vars must be set (XUI_BASE_URL/USERNAME/PASSWORD/INBOUND_ID/...)
    python -m scripts.xui_smoke            # run + cleanup
    python -m scripts.xui_smoke --keep     # keep the test client
    python scripts/xui_smoke.py            # equivalent

The script is not invoked from the bot. It exists so operators can sanity-check
that a panel/version combination is compatible after deploying.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from typing import Any

from loguru import logger

from app.config import settings
from app.logger import setup_logging
from app.xui.client import XuiClient, XuiError
from app.xui.clients import (
    add_client,
    del_client,
    get_client_traffics,
    make_client_email,
    make_client_uuid,
)
from app.xui.inbounds import get_inbound, list_inbounds


def _short(obj: Any, limit: int = 400) -> str:
    """Compact json.dumps for log lines, truncated to ``limit`` chars."""
    text = json.dumps(obj, ensure_ascii=False, default=str)
    return text if len(text) <= limit else text[:limit] + "…"


async def run(keep: bool) -> int:
    """Execute the smoke sequence. Returns process exit code."""
    setup_logging("INFO")

    test_uuid = make_client_uuid()
    test_email = make_client_email(tg_id=999_000_001)
    # 10 minutes from now, expressed in milliseconds (3x-ui requirement).
    expiry_ts_ms = int((time.time() + 600) * 1000)

    logger.info("xui-smoke: target panel {}", settings.XUI_BASE_URL)
    logger.info("xui-smoke: test client email={} uuid={}", test_email, test_uuid)

    client = XuiClient()
    try:
        # --- 1) login ---------------------------------------------------
        try:
            await client.login()
        except XuiError as exc:
            logger.error("step=login failed: {}", exc)
            return 2

        # --- 2) list inbounds -------------------------------------------
        try:
            inbounds = await list_inbounds(client)
        except XuiError as exc:
            logger.error("step=list_inbounds failed: {}", exc)
            return 3
        logger.info("step=list_inbounds count={}", len(inbounds))
        for ib in inbounds:
            logger.info(
                "  inbound id={} port={} protocol={} remark={}",
                ib.get("id"),
                ib.get("port"),
                ib.get("protocol"),
                ib.get("remark"),
            )

        # --- 3) get target inbound --------------------------------------
        try:
            inbound = await get_inbound(client, settings.XUI_INBOUND_ID)
        except XuiError as exc:
            logger.error("step=get_inbound({}) failed: {}", settings.XUI_INBOUND_ID, exc)
            return 4
        existing_clients = (
            (inbound.get("settings") or {}).get("clients") if isinstance(inbound, dict) else None
        )
        logger.info(
            "step=get_inbound id={} port={} clients_before={}",
            inbound.get("id"),
            inbound.get("port"),
            len(existing_clients or []),
        )

        # --- 4) add_client ----------------------------------------------
        try:
            created = await add_client(
                client,
                inbound_id=settings.XUI_INBOUND_ID,
                client_uuid=test_uuid,
                email=test_email,
                expiry_ts_ms=expiry_ts_ms,
                total_gb=0,
                tg_id=str(999_000_001),
            )
        except XuiError as exc:
            logger.error("step=add_client failed: {}", exc)
            return 5
        logger.info("step=add_client OK -> {}", _short(created))

        # --- 5) get_client_traffics -------------------------------------
        try:
            traffics = await get_client_traffics(client, test_email)
        except XuiError as exc:
            logger.error("step=get_client_traffics failed: {}", exc)
            # Continue to cleanup so we don't leak the test client.
            traffics = {}
        logger.info("step=get_client_traffics -> {}", _short(traffics))

        # --- 6) del_client (unless --keep) ------------------------------
        if keep:
            logger.warning("--keep: leaving test client in place (uuid={})", test_uuid)
        else:
            try:
                await del_client(client, settings.XUI_INBOUND_ID, test_uuid)
            except XuiError as exc:
                logger.error("step=del_client failed: {}", exc)
                return 6
            logger.info("step=del_client OK")

        logger.success("xui-smoke: all steps passed")
        return 0
    finally:
        await client.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="3x-ui REST client smoke test")
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Do not delete the test client at the end (useful for manual inspection).",
    )
    args = parser.parse_args()
    return asyncio.run(run(keep=args.keep))


if __name__ == "__main__":
    sys.exit(main())
