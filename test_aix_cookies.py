"""Test script: fetch RJ01668373 (aix floor) using cookies exported from a
real, already-logged-in browser session.

The aix floor's login code-exchange is blocked for plain HTTP clients
(appears to be Cloudflare TLS/JA3 fingerprinting on www.dlsite.com's OAuth
callback -- see debug session notes), so this bypasses login() entirely:

1. Log into DLsite in a real browser, with the JP VPN active.
2. Visit the aix product page once in that browser so the session is fully
   established.
3. Export cookies for dlsite.com (a browser extension such as "Get
   cookies.txt LOCALLY" produces a Netscape-format file) to a file.
4. Run:

    ./.venv/bin/python test_aix_cookies.py /path/to/cookies.txt
"""

import asyncio
import dataclasses
import json
import sys
from datetime import datetime
from pathlib import Path

from dlsite_async import DlsiteAPI

PRODUCT_ID = "RJ01668373"


def _default(o: object) -> str:
    if isinstance(o, datetime):
        return o.isoformat()
    return str(o)


async def main(cookies_path: Path) -> None:
    async with DlsiteAPI() as api:
        api.load_cookies_txt(cookies_path)
        result = await api.get_work(PRODUCT_ID)
    print(json.dumps(dataclasses.asdict(result), ensure_ascii=False, indent=2, default=_default))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: ./.venv/bin/python test_aix_cookies.py <cookies.txt>")
        sys.exit(1)
    asyncio.run(main(Path(sys.argv[1])))
