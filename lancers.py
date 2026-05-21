import json
import math
import os
import re
import time
import datetime
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
from datetime import datetime, timedelta

import requests
from bs4 import BeautifulSoup, NavigableString

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

import sheets

SLACK_BOT_TOKEN = "xoxb-9550131875088-10670319023685-BG4gEZit6Kwqy5ltu4XkaOV5"
CHANNEL_ID = "C0ADGTM2F5X"

slack_client = WebClient(token=SLACK_BOT_TOKEN)

WEBHOOK_URL = "https://discord.com/api/webhooks/1451104878800670913/xOdH4MvJfd4RoN-Htk8Wm-YqsCBFZeE3AOH0E-kn7hvK0etHYp7kzO-KO9DIzNvZC6pW"

LISTING_URL = "https://www.lancers.jp/work/search/system?open=1&ref=header_menu"
BASE_URL = "https://www.lancers.jp"
HTML_PATH = Path("lancers_work_search.html")
JSON_PATH = Path("lancers_jobs.json")
FILTERED_PATH = Path("lancers_jobs_today_over_50000.json")
POSTED_IDS_PATH = Path("posted_job_ids.json")

GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID", "1MkuU8j1-RV6gNdSczbq22X37CZ1iux3ct3iftp5F2vo")
GOOGLE_SHEET_TAB = os.getenv("GOOGLE_SHEET_TAB", "Lancers_List")
GOOGLE_SERVICE_ACCOUNT_FILE = Path(os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json"))

_worksheet_cache: Optional[Any] = None


DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "ja,en;q=0.9",
    "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}

DEFAULT_COOKIES_PATH = Path(os.getenv("LANCERS_COOKIES", "lancers_cookies.json"))


def _apply_selenium_cookies_to_session(session: requests.Session, cookies: List[Dict[str, Any]]) -> None:
    from requests.cookies import create_cookie

    default_domain = urlparse(BASE_URL).hostname or "www.lancers.jp"
    for cookie in cookies:
        name = cookie.get("name")
        if not name:
            continue

        domain = cookie.get("domain") or default_domain
        value = cookie.get("value") or ""
        path = cookie.get("path") or "/"
        secure = bool(cookie.get("secure"))
        expires = cookie.get("expiry")

        rest: Dict[str, Any] = {}
        if "httpOnly" in cookie:
            rest["HttpOnly"] = cookie.get("httpOnly")

        session.cookies.set_cookie(
            create_cookie(
                name=name,
                value=value,
                domain=domain,
                path=path,
                secure=secure,
                expires=expires,
                rest=rest,
            )
        )


def build_authenticated_session(*, cookies_path: Optional[Path] = None) -> requests.Session:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)

    if cookies_path and cookies_path.exists():
        try:
            from login import load_cookies

            cookies = load_cookies(cookies_path)
            _apply_selenium_cookies_to_session(session, cookies)
        except Exception as exc:
            print(f"Warning: failed to load cookies from {cookies_path}: {exc}")

    return session


def fetch_html(url: str, *, session: Optional[requests.Session] = None) -> str:
    # Append a cache-busting timestamp so CDN/proxy layers cannot return a
    # stale copy of the listing — that's what makes brand-new posts appear
    # minutes late. The query param is ignored by the application but
    # forces the edge cache to treat each request as unique.
    sep = "&" if "?" in url else "?"
    full_url = f"{url}{sep}_={int(time.time() * 1000)}"
    if session is None:
        resp = requests.get(full_url, headers=DEFAULT_HEADERS, timeout=15)
    else:
        resp = session.get(full_url, headers=DEFAULT_HEADERS, timeout=15)
    resp.raise_for_status()
    resp.encoding = resp.apparent_encoding
    return resp.text


def _clean(text: Optional[str]) -> str:
    if not text:
        return ""
    return " ".join(text.split())


def _parse_budget(raw: str) -> Tuple[Optional[int], Optional[int]]:
    """Extract budget min/max integers from strings like '100,000 円 ~ 200,000 円 / 固定'."""
    nums = re.findall(r"[0-9,]+", raw)
    ints = [int(n.replace(",", "")) for n in nums]
    if not ints:
        return None, None
    if len(ints) == 1:
        return ints[0], None
    return ints[0], ints[1]


def _parse_job_id(onclick: str, url: Optional[str]) -> Optional[str]:
    if onclick:
        m = re.search(r"goToLjpWorkDetail\((\d+)\)", onclick)
        if m:
            return m.group(1)
    if url:
        # fallback: parse last numeric segment in the URL path
        path = urlparse(url).path
        m = re.search(r"(\d+)", path.split("/")[-1])
        if m:
            return m.group(1)
    return None


def parse_jobs(html: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    jobs: List[Dict[str, Any]] = []

    for card in soup.select("div.p-search-job-media.c-media.c-media--item"):
        onclick = card.get("onclick", "")

        # Project cards have goToLjpWorkDetail(N); 求人 / onsite job cards have
        # goToLjpJobDetail(N) with a tiny ID in a different namespace. Mixing
        # them in causes ID collisions in pre_systems and wrong-type
        # notifications, so skip anything that is not a project card.
        if "goToLjpWorkDetail" not in onclick:
            continue

        title_tag = card.select_one("a.p-search-job-media__title")
        # The tags <ul> (NEW, 急募, etc.) is nested inside the title <a>, so
        # get_text() would prepend "NEW" to every title. Read only the direct
        # text nodes of the <a> to get the real title on its own.
        title = ""
        if title_tag:
            title = _clean("".join(
                c for c in title_tag.contents if isinstance(c, NavigableString)
            ))
        url = urljoin(BASE_URL, title_tag["href"]) if title_tag and title_tag.get("href") else None
        job_id = _parse_job_id(onclick, url)

        tags = [_clean(li.get_text()) for li in card.select("ul.p-search-job-media__tags li")]
        categories = [_clean(li.get_text()) for li in card.select("ul.p-search-job__divisions li")]

        job_type_tag = card.select_one(".c-badge__text")
        job_type = _clean(job_type_tag.get_text()) if job_type_tag else ""

        price_tag = card.select_one(".p-search-job-media__price")
        budget_raw = _clean(price_tag.get_text(" ", strip=True)) if price_tag else ""
        budget_min, budget_max = _parse_budget(budget_raw) if budget_raw else (None, None)

        desc_tag = card.select_one(".c-media__description")
        description = _clean(desc_tag.get_text(" ", strip=True)) if desc_tag else ""

        time_box = card.select_one(".p-search-job-media__time")
        time_text_tag = time_box.select_one(".p-search-job-media__time-text") if time_box else None
        time_remaining_tag = time_box.select_one(".p-search-job-media__time-remaining") if time_box else None
        time_status = _clean(time_text_tag.get_text()) if time_text_tag else ""
        time_remaining = _clean(time_remaining_tag.get_text()) if time_remaining_tag else ""

        numbers = [n.get_text(strip=True) for n in card.select(".p-search-job-media__propose-number")]
        proposals = {
            "selected": int(numbers[0]) if len(numbers) > 0 and numbers[0].isdigit() else numbers[0] if numbers else "",
            "target": int(numbers[1]) if len(numbers) > 1 and numbers[1].isdigit() else numbers[1] if len(numbers) > 1 else "",
        }

        client_tag = card.select_one(".p-search-job-media__avatar-note a")
        client = _clean(client_tag.get_text()) if client_tag else ""

        jobs.append(
            {
                "id": job_id,
                "title": title,
                "url": url,
                "tags": tags,
                "categories": categories,
                "job_type": job_type,
                "budget": budget_raw,
                "budget_min": budget_min,
                "budget_max": budget_max,
                "description": description,
                "time_status": time_status,
                "time_remaining": time_remaining,
                "proposals": proposals,
                "client": client,
            }
        )

    return jobs


def save_jobs_to_json(jobs: List[Dict[str, Any]], path: Path) -> None:
    path.write_text(json.dumps(jobs, ensure_ascii=False, indent=2), encoding="utf-8")


def filter_new_high_budget(jobs: List[Dict[str, Any]], min_price: int) -> List[Dict[str, Any]]:
    """Filter jobs that are tagged NEW (proxy for today) and meet the minimum budget, excluding certain clients."""
    blocked_clients = ["タグ株式会社", "Taka", "support_3"]
    blocked_titles = ["運営代行"]
    filtered = []
    for job in jobs:
        budget_min = job.get("budget_min")
        tags = job.get("tags") or []
        is_new = any("NEW" in t.upper() for t in tags)
        if not is_new:
            continue
        if job.get("job_type") == "コンペ" or job.get("job_type") == "求人":
            continue
        if budget_min is None or budget_min <= min_price:
            continue
        client = (job.get("client") or "").strip()
        if any(blocked.lower() in client.lower() for blocked in blocked_clients):
            continue
        title = (job.get("title") or "").strip()
        if any(blocked_title.lower() in title.lower() for blocked_title in blocked_titles):
            continue
        filtered.append(job)
    return filtered


def _load_posted_ids() -> Dict[str, List[str]]:
    if not POSTED_IDS_PATH.exists():
        return {}
    try:
        data = json.loads(POSTED_IDS_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return {k: list(v) for k, v in data.items() if isinstance(v, list)}
        return {}
    except Exception:
        return {}


def _save_posted_ids(by_category: Dict[str, List[str]]) -> None:
    POSTED_IDS_PATH.write_text(json.dumps(by_category, ensure_ascii=False, indent=2), encoding="utf-8")


def get_job_data_dict(url: str, *, session: Optional[requests.Session] = None):
    # Step 1: make sure we have the latest HTML
    html = fetch_html(url, session=session)
    HTML_PATH.write_text(html, encoding="utf-8")

    # Step 2: parse job cards from the HTML we just saved
    jobs = parse_jobs(html)
    save_jobs_to_json(jobs, JSON_PATH)

    # Step 3: filter for today's (NEW) jobs with minimum budget over 20,000円
    filtered_jobs = filter_new_high_budget(jobs, min_price=20000)
    return jobs, filtered_jobs
        
def fetch_full_description(url: Optional[str], *, session: Optional[requests.Session] = None) -> str:
    """Fetch the complete job description from a Lancers work detail page.

    The search listing only carries a truncated preview; the full text lives in
    the 依頼概要 row (dd.c-definition-list__description) of the detail page.
    """
    if not url:
        return ""
    try:
        html = fetch_html(url, session=session)
        soup = BeautifulSoup(html, "html.parser")
        best = ""
        for dd in soup.select("dd.c-definition-list__description"):
            text = dd.get_text("\n", strip=True)
            if len(text) > len(best):
                best = text
        # collapse runs of blank lines that get_text can introduce
        return re.sub(r"\n{3,}", "\n\n", best).strip()
    except Exception as exc:
        print(f"Failed to fetch full description from {url}: {exc}")
        return ""


def _format_estimate(job_json) -> str:
    """Build an estimate string like 'fixed(100,000円〜200,000円)' for the sheet."""
    budget_raw = job_json.get("budget") or ""
    lo = job_json.get("budget_min")
    hi = job_json.get("budget_max")
    ptype = "hourly" if ("時間" in budget_raw or "時給" in budget_raw) else "fixed"
    if isinstance(lo, int) and isinstance(hi, int) and lo != hi:
        return f"{ptype}({lo:,}円〜{hi:,}円)"
    amount = lo if isinstance(lo, int) else (hi if isinstance(hi, int) else None)
    if amount is not None:
        return f"{ptype}({amount:,}円)"
    return budget_raw or "undefined"


def build_copy_block(title, content):
    """Build a Slack code block; Slack's built-in copy button on code blocks
    copies this exact text (Title / separator / Content) to the clipboard."""
    title = (title or "").replace("```", "'''")
    content = (content or "").replace("```", "'''")
    return (
        "```\n"
        f"Title:{title}\n"
        + "-" * 19 + "\n"
        f" Content:{content}\n"
        "```"
    )


def show_noti(job_json, index, session=None):
    print(f"Title: {job_json['title']}")
    print(f"https://www.lancers.jp/work/detail/{job_json['id']}")
    print(f"Payment: {job_json['budget']}")

    if (index == "system"):
        category = "System"
    elif (index == "web"):
        category = "Web"
    elif (index == "design"):
        category = "Design"
    else:
        category = index.title() if isinstance(index, str) else ""

    detail_url = job_json.get("url") or f"https://www.lancers.jp/work/detail/{job_json['id']}"

    # The listing only has a truncated preview; fetch the full detail text
    # first so it can feed both the Slack copy-block and the sheet.
    content = fetch_full_description(detail_url, session=session) or (job_json.get("description") or "")

    # Code block at the end of the message. Slack shows a one-click copy
    # button on code blocks, so pressing it copies exactly this text.
    copy_block = build_copy_block(job_json["title"], content)

    try:
        response = slack_client.chat_postMessage(
            channel=CHANNEL_ID,
            text = "Lancers New Task\n" + category + "\n" + job_json['title'] + "\n" + detail_url + "\nPayment: " + job_json['budget']
        )
    except SlackApiError as e:
        print(f"Error: {e.response['error']}")

    try:
        sheets.append_job_row(
            gid=sheets.LANCERS_GID,
            category=category,
            title=job_json.get("title") or "",
            detail_url=detail_url,
            estimate=_format_estimate(job_json),
            content=content,
        )
    except Exception as exc:
        print(f"Sheet logging error: {exc}")

if __name__ == "__main__":
    try:
        session = build_authenticated_session(cookies_path=DEFAULT_COOKIES_PATH if DEFAULT_COOKIES_PATH.exists() else None)
        if DEFAULT_COOKIES_PATH.exists():
            print(f"Using Lancers cookies: {DEFAULT_COOKIES_PATH}")
        else:
            print(f"No cookies found at {DEFAULT_COOKIES_PATH}; fetching as guest. Run: python login.py")

        categories = ['system', 'web'] #system, web, design
        count = [0] * len(categories)
        persisted = _load_posted_ids()
        pre_systems = [list(persisted.get(c, [])) for c in categories]
        i = 0
        duration = 0
        pre_duration = 0
        while True:
            try:
                duration += pre_duration
                start = time.time()
                idx = i % len(categories)
                if categories[idx] == 'system':
                    print()
                    print()
                    print(f"~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~    Count:{ (math.floor(i / len(categories))) + 1 }  Duration: {duration:.2f} S    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
                    print()
                    print(f"================================= System   Duration: {pre_duration:.2f} S  ================================")
                    print()
                elif categories[idx] == 'web':
                    print()
                    print(f"================================= Web   Duration: {pre_duration:.2f} S  ================================")
                    print()

                if idx == 0:
                    duration = 0

                # sort=started → 新着順 (newest first). The default sort=client
                # reorders by recommendation, which both hides fresh posts and
                # surfaces older ones as if they were new.
                all_jobs, job_list = get_job_data_dict(
                    url=f"https://www.lancers.jp/work/search/{categories[idx]}?open=1&sort=started&ref=header_menu",
                    session=session,
                )

                # Snapshot what we'd seen before this scan; notifications use this
                # so a job that changes filter-membership later (e.g. budget edited
                # upward hours after posting) is not mistaken for a brand-new post.
                seen_before = set(pre_systems[idx])

                # Track every NEW-tagged job we observe, not just ones that pass
                # the filter. This is the key fix: filter membership can flip
                # later, but the job itself isn't actually new at that point.
                for job in (all_jobs or []):
                    if not job:
                        continue
                    job_id = job.get("id")
                    if not job_id:
                        continue
                    tags = job.get("tags") or []
                    if not any("NEW" in t.upper() for t in tags):
                        continue
                    if job_id not in seen_before:
                        pre_systems[idx].append(job_id)

                # Notify on filtered jobs we hadn't seen prior to this scan,
                # and only after the first warm-up cycle for this category.
                if count[idx] > 0:
                    for job in (job_list or []):
                        if not job:
                            continue
                        job_id = job.get("id")
                        if not job_id:
                            continue
                        if job_id not in seen_before:
                            show_noti(job, categories[idx], session=session)

                if len(pre_systems[idx]) > 1000:
                    pre_systems[idx] = pre_systems[idx][-1000:]

                try:
                    _save_posted_ids({categories[k]: pre_systems[k] for k in range(len(categories))})
                except Exception as save_exc:
                    print(f"Warning: failed to persist posted ids: {save_exc}")

                end = time.time()
                pre_duration = end - start
                count[idx] += 1
                i += 1
            except Exception as e:
                print(f"Error: {e}")
                traceback.print_exc()
                time.sleep(5)
                count = [0] * len(categories)
                i = 0
                continue
                    
    except Exception as e:
        print(f"Error: {e}")
