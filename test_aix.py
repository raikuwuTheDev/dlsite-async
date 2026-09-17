"""Test script: fetch RJ01668373 (aix floor) while on JP VPN.

Run locally on the machine that has the Japan VPN active:

    python test_aix.py

Password is entered via a hidden prompt (getpass) so it never ends up
in shell history or in this file.
"""

import asyncio
import dataclasses
import getpass
import json
from datetime import datetime
from pathlib import Path

from dlsite_async import DlsiteAPI

PRODUCT_ID = "RJ01668373"
HTML_DUMP_PATH = Path(__file__).with_name("aix_work_loggedin.html")


def _default(o: object) -> str:
    if isinstance(o, datetime):
        return o.isoformat()
    return str(o)


async def main() -> None:
    login_id = input("DLsite login ID: ").strip()
    password = getpass.getpass("DLsite password: ")

    async with DlsiteAPI() as api:
        await api.login(login_id, password, site_id="aix")
        print("Logged in.")

        # Debug only: list cookie names/domains (never values) so we can
        # compare against what a real browser session holds after login,
        # without ever printing/logging the actual secret cookie values.
        print("Cookie jar after login (name @ domain):")
        for cookie in api.session.cookie_jar:
            print(f"  {cookie.key} @ {cookie['domain']}")

        # Fetch the raw product-page HTML too, so we can check whether the
        # outline table / #right panel is actually populated once truly
        # logged in (this is what we need to confirm before deciding the
        # scraper fix direction).
        work = await api.product_info(PRODUCT_ID)
        html = await api._fetch_work_html(work)  # noqa: SLF001 (debug only)
        if html:
            HTML_DUMP_PATH.write_text(html, encoding="utf-8")
            print(f"Saved raw work-page HTML to {HTML_DUMP_PATH} ({len(html)} bytes)")
        else:
            print("No HTML returned for the work page (both work/ and announce/ URLs failed).")

        result = await api.get_work(PRODUCT_ID)

    print(json.dumps(dataclasses.asdict(result), ensure_ascii=False, indent=2, default=_default))


if __name__ == "__main__":
    asyncio.run(main())
