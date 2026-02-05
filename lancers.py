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
from bs4 import BeautifulSoup

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

SLACK_BOT_TOKEN = "xoxp-9550131875088-9550131925200-10439629163507-5af893dec1ea669a630b237666ac5354"
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


def fetch_html(url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept-Language": "ja,en;q=0.9",
    }
    resp = requests.get(url, headers=headers, timeout=15)
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

        title_tag = card.select_one("a.p-search-job-media__title")
        title = _clean(title_tag.get_text()) if title_tag else ""
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
        time_status = _clean(time_box.select_one(".p-search-job-media__time-text").get_text()) if time_box else ""
        time_remaining = _clean(time_box.select_one(".p-search-job-media__time-remaining").get_text()) if time_box else ""

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


def _load_posted_ids() -> set[str]:
    if not POSTED_IDS_PATH.exists():
        return set()
    try:
        return set(json.loads(POSTED_IDS_PATH.read_text(encoding="utf-8")))
    except Exception:
        return set()


def _save_posted_ids(ids: set[str]) -> None:
    POSTED_IDS_PATH.write_text(json.dumps(sorted(ids), ensure_ascii=False, indent=2), encoding="utf-8")


def _get_worksheet():
    global _worksheet_cache
    if _worksheet_cache:
        return _worksheet_cache

    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as exc:
        print(f"Skipping Google Sheets logging (missing dependency): {exc}")
        _worksheet_cache = None
        return None

    if not GOOGLE_SERVICE_ACCOUNT_FILE.exists():
        print(f"Skipping Google Sheets logging (credentials not found at {GOOGLE_SERVICE_ACCOUNT_FILE}).")
        _worksheet_cache = None
        return None

    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_file(str(GOOGLE_SERVICE_ACCOUNT_FILE), scopes=scopes)
        client = gspread.authorize(creds)
        _worksheet_cache = client.open_by_key(GOOGLE_SHEET_ID).worksheet(GOOGLE_SHEET_TAB)
    except Exception as exc:
        print(f"Skipping Google Sheets logging (init failed): {exc}")
        print(traceback.format_exc())
        _worksheet_cache = None
    return _worksheet_cache


def append_job_to_sheet(job: Dict[str, Any], category: str) -> None:
    if not job.get("id"):
        return

    posted_ids = _load_posted_ids()
    if job["id"] in posted_ids:
        return

    worksheet = _get_worksheet()
    if not worksheet:
        return

    now = datetime.now()
    description = (job.get("description") or "").strip()
    url = job.get("url")
    if url:
        description = f"{description}\n{url}" if description else url

    title = job.get("title") or ""
    title = title[4:] if len(title) > 4 else ""

    row = [
        "=ROW()-1",
        now.strftime("%Y/%m/%d"),
        now.strftime("%H:%M:%S"),
        category.title() if category else "",
        title,
        job.get("budget") or "",
        description,
    ]

    try:
        worksheet.append_row(row, value_input_option="USER_ENTERED")
        posted_ids.add(job["id"])
        _save_posted_ids(posted_ids)
    except Exception as exc:
        print(f"Failed to append to Google Sheet: {exc}")


def get_job_data_dict(url: str):
    # Step 1: make sure we have the latest HTML
    html = fetch_html(url)
    HTML_PATH.write_text(html, encoding="utf-8")

    # Step 2: parse job cards from the HTML we just saved
    jobs = parse_jobs(html)
    save_jobs_to_json(jobs, JSON_PATH)

    # Step 3: filter for today's (NEW) jobs with minimum budget over 50,000円
    filtered_jobs = filter_new_high_budget(jobs, min_price=50_000)
    return filtered_jobs
        
def show_noti(job_json, index):
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

    append_job_to_sheet(job_json, category)

    data = {
        "embeds": [
            {
                "title": "Lancers New Task\n" + category,
                "description": job_json['title'] + job_json['url'] + "\nPayment: " + job_json['budget'],
                "color": 0x00ff00
            }
        ]
    }

    try:
        response = slack_client.chat_postMessage(
            channel=CHANNEL_ID,
            text = "Lancers New Task\n" + category + "\n" + job_json['title'] + job_json['url'] + "\nPayment: " + job_json['budget']
        )
    except SlackApiError as e:
        print(f"Error: {e.response['error']}")
    
    # response = requests.post(WEBHOOK_URL, json=data)

    # if response.status_code == 204:
    #     print("Message sent successfully")
    # else:
    #     print("Failed:", response.text)

if __name__ == "__main__":
    try:
        categories = ['system', 'web', 'design'] #system, web, design
        count = [0, 0, 0]
        pre_systems = [[],[],[]]
        new_systems = []
        i = 0
        duration = 0
        pre_duration = 0
        while True:
            try:
                duration += pre_duration
                start = time.time()
                # print(f"Count: {count[i%3]}")
                if categories[i%3] == 'system':
                    print()
                    print()
                    print(f"~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~    Count:{ (math.floor(i / 3)) + 1 }  Duration: {duration:.2f} S    ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~")
                    print()
                    print(f"================================= System   Duration: {pre_duration:.2f} S  ================================")
                    print()
                elif categories[i%3] == 'web':
                    print()
                    print(f"================================= Web   Duration: {pre_duration:.2f} S  ================================")
                    print()
                elif categories[i%3] == 'design':
                    print()
                    print(f"================================= Design   Duration: {pre_duration:.2f} S  ================================")
                    print()
                    
                if i % 3 == 0:
                    duration = 0
                # print("pre_systems", pre_systems)
                # systems = pre_systems[i%3]
                # pre_systems[i%3] = []
                job_list = get_job_data_dict(url=f"https://www.lancers.jp/work/search/{categories[i%3]}?open=1&ref=header_menu")
                
                for job in job_list:
                    if job:
                        pre_systems[i%3].append(job['id'])
                        if job['id'] not in pre_systems[i%3] and count[i%3] > 0:
                        # if job['id'] not in pre_systems[i%3]:
                            pre_systems[i%3].append(job['id'])
                            show_noti(job, categories[i%3])
                
                if len(pre_systems[i%3]) > 300:
                    pre_systems = pre_systems[-300:]
                
                end = time.time()
                pre_duration = end - start
                count[i%3] += 1
                i += 1
            except Exception as e:
                time.sleep(1)
                count = [0,0,0]
                i = 0
                print(f"Error: {e}")
                continue
                    
    except Exception as e:
        print(f"Error: {e}")
