# Fork notes

This repository is a personal fork of [bhrevol/dlsite-async](https://github.com/bhrevol/dlsite-async),
used by [DLsite_DB_Crawler](https://github.com/raikuwuTheDev/kmcdotinfo-dlsite-crawler).

## Policy: upstream -> fork only

Changes flow **one way**, from upstream into this fork.

- Do **not** open pull requests, issues, discussions or comments on `bhrevol/dlsite-async`.
- Do **not** push anything to the `upstream` remote.
- Fixes and features we need live in this fork only. They are never sent back.
- We still **receive** upstream updates, by merging `upstream/main` (see below).

Related: upstream's `CONTRIBUTING.md` has a strict "No LLM / No AI" policy for
issues, patches and comments. That is not our workflow, which is another reason
nothing goes back.

To make an accidental push impossible, disable the push URL of the `upstream` remote
(one-time, local):

```console
$ git remote set-url --push upstream no_push
```

## Remotes

| Remote     | URL                                              | Use                      |
| ---------- | ------------------------------------------------ | ------------------------ |
| `origin`   | `https://github.com/raikuwuTheDev/dlsite-async`  | this fork, push here     |
| `upstream` | `https://github.com/bhrevol/dlsite-async`        | fetch / merge only       |

## Taking updates from upstream

Always merge (do not rebase), so fork history stays intact and the merge commit
records where we synced.

```console
$ git fetch upstream
$ git log --oneline HEAD..upstream/main      # what is new?
$ git switch -c sync-upstream-<topic>
$ git merge upstream/main
```

Resolve conflicts keeping the fork-only changes listed below, then:

1. Run the tests (see "Verifying a sync").
2. Merge the sync branch into `main` and push to **`origin`** only.
3. Update the pin in `DLsite_DB_Crawler/requirements.txt`
   (`dlsite-async @ git+https://github.com/raikuwuTheDev/dlsite-async.git@<merge-sha>`),
   then reinstall it in that project's venvs (`dlsite-env`, `desktop-env`).
4. If upstream made a breaking change, adapt `DLsite_DB_Crawler` in its own commit.
   The last sync (aiohttp -> curl-cffi) is the model: `8a7ebe2` in that repo.

To keep future merges conflict-free, **do not edit upstream-owned docs** such as
`README.md` and `CONTRIBUTING.md`. Put fork-specific documentation in this file.

## Fork-only changes

Keep these when resolving conflicts. Verify with `git diff upstream/main HEAD`.

- `src/dlsite_async/api.py`
  - `BaseAPI.load_cookies_txt()`: import a Netscape `cookies.txt` into the session.
  - `BaseAPI.login(site_id=...)`: complete the OAuth2 SSO handoff to `www.dlsite.com`
    (maniax and aix floors); success is detected by the final URL host.
  - `DlsiteAPI.__init__` forwards `**kwargs` (e.g. `proxy`) and merges extra `cookies`.
  - `_fetch_work_html`: no per-request `raise_for_status` (not supported by curl-cffi);
    catches `CurlError` and falls through to the next URL.
- `src/dlsite_async/work.py`
  - `Work.from_json` accepts the list form of `rate_count_detail` returned by
    `product/info/ajax` as well as the dict form from `product.json`.
- Tests: `tests/test_login.py`, plus the `rate_count_detail` and
  `_fetch_work_html` fallback tests in `tests/test_api.py`.
- Debug scripts at the repo root: `test_aix.py`, `test_aix_cookies.py` (manual, not part of the suite).
- This file.

## Verifying a sync

Unit tests are mocked, so also do one live, read-only smoke fetch.

```console
$ python -m pip install -e ".[pil]" --group tests      # inside .venv
$ python -m pytest
$ python - <<'EOF'
import asyncio
from dlsite_async import DlsiteAPI

async def main():
    async with DlsiteAPI() as api:
        w = await api.get_work("VJ01002422")
        print(w.work_name, w.maker_name, w.genre, w.release_date, w.rate_average)

asyncio.run(main())
EOF
```

Then, from `DLsite_DB_Crawler`, run `desktop-env/bin/python -m pytest tests`.

## Last sync

- 2026-11-12, `ab33110`: merged upstream v1.0.0 (aiohttp -> curl-cffi) on branch `sync-upstream-curl-cffi`.
- 2026-11-14: unit tests (40 here, 34 in the crawler) and live fetches of `VJ01002422` and `RJ01668373` all pass.
