import hashlib
import math
import re
import time
from html import unescape
from typing import Dict, List, Optional

import requests
try:
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
except Exception:  # pragma: no cover
    WebClient = None
    SlackApiError = Exception

SLACK_BOT_TOKEN = "xoxb-9550131875088-10908362495041-FHo7znrozyO9EFLivJ67zoAZ"
CHANNEL_ID = "C0AVA1SPX0E"
slack_client = WebClient(token=SLACK_BOT_TOKEN) if WebClient else None

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en;q=0.9",
}

CATEGORY_URLS = {
    11: "https://coconala.com/requests/categories/11",
    22: "https://coconala.com/requests/categories/22",
    28: "https://coconala.com/requests/categories/28",
}

CATEGORY_NAMES = {
    11: "IT相談・システム開発",
    22: "Web制作・HP作成・EC構築",
    28: "AI導入・生成AI活用相談",
}

BLOCKED_TITLE_WORDS = [
    "講師",
    "運営代行",
    "初心者",
    "バナー",
    "ロゴ",
]

BLOCKED_USER_WORDS = [
    "support_3",
]


def fetch_text_lines(url: str) -> List[str]:
    response = requests.get(url, headers=DEFAULT_HEADERS, timeout=20)
    response.raise_for_status()
    html = response.text

    # Keep only visible text to avoid fragile DOM selectors.
    html = re.sub(r"(?is)<script.*?>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style.*?>.*?</style>", " ", html)
    html = re.sub(r"(?is)<noscript.*?>.*?</noscript>", " ", html)
    html = re.sub(r"(?is)<!--.*?-->", " ", html)
    html = re.sub(r"(?is)<[^>]+>", "\n", html)
    text = unescape(html)

    lines = []
    for raw in text.splitlines():
        line = re.sub(r"\s+", " ", raw).strip()
        if line:
            lines.append(line)
    return lines


def _extract_budget_numeric(budget_text: str) -> Optional[int]:
    nums = re.findall(r"[0-9,]+", budget_text)
    if not nums:
        return None
    values = [int(v.replace(",", "")) for v in nums]
    return max(values) if values else None


def _job_id(url: str, title: str, user: str, posted_at: str) -> str:
    src = f"{url}|{title}|{user}|{posted_at}"
    return hashlib.sha1(src.encode("utf-8")).hexdigest()


def parse_jobs_from_lines(lines: List[str], category_url: str) -> List[Dict]:
    jobs: List[Dict] = []

    # Narrow to main listing area.
    start = 0
    end = len(lines)
    for i, line in enumerate(lines):
        if line == "件表示" and i >= 1 and "1 - 40" in lines[i - 1]:
            start = i + 1
            break
    listing = lines[start:end]

    starts: List[int] = []
    for i in range(0, len(listing) - 2):
        if listing[i + 2] != "ブックマーク":
            continue
        category = listing[i]
        title = listing[i + 1]
        if not category or not title:
            continue
        if category in {"投稿日時：", "予算", "応募者数", "募集期限", "ブックマーク"}:
            continue
        if category.endswith("："):
            continue
        if "順" in category or "仕事を探す" in title:
            continue
        if "投稿日時：" not in listing[i : min(i + 30, len(listing))]:
            continue
        starts.append(i)

    for idx, block_start in enumerate(starts):
        block_end = starts[idx + 1] if idx + 1 < len(starts) else len(listing)
        block = listing[block_start:block_end]
        if len(block) < 8:
            continue

        category = block[0]
        title = block[1]

        try:
            posted_label_idx = block.index("投稿日時：")
        except ValueError:
            continue

        if posted_label_idx < 1 or posted_label_idx + 1 >= len(block):
            continue

        user = block[posted_label_idx - 1]
        posted_at = block[posted_label_idx + 1].strip()
        description = " ".join(block[3 : posted_label_idx - 1]).strip()

        budget = "見積り希望"
        applicants = ""
        deadline = ""

        if "予算" in block:
            b_idx = block.index("予算")
            a_idx = block.index("応募者数") if "応募者数" in block else len(block)
            budget_tokens = block[b_idx + 1 : a_idx]
            if budget_tokens:
                budget = " ".join(budget_tokens).strip()

        if "応募者数" in block:
            a_idx = block.index("応募者数")
            d_idx = block.index("募集期限") if "募集期限" in block else len(block)
            applicants = " ".join(block[a_idx + 1 : d_idx]).strip()

        if "募集期限" in block:
            d_idx = block.index("募集期限")
            deadline = " ".join(block[d_idx + 1 :]).strip()

        jobs.append(
            {
                "id": _job_id(category_url, title, user, posted_at),
                "title": title,
                "category": category,
                "description": description,
                "user": user,
                "posted_at": posted_at,
                "budget": budget,
                "budget_numeric": _extract_budget_numeric(budget),
                "applicants": applicants,
                "deadline": deadline,
                "url": category_url,
            }
        )

    # De-duplicate inside a single fetch.
    unique: Dict[str, Dict] = {}
    for job in jobs:
        unique[job["id"]] = job
    return list(unique.values())


def job_filter(job: Dict) -> Optional[Dict]:
    title = (job.get("title") or "").lower()
    user = (job.get("user") or "").lower()
    if any(word.lower() in title for word in BLOCKED_TITLE_WORDS):
        return None
    if any(word.lower() in user for word in BLOCKED_USER_WORDS):
        return None

    budget_value = job.get("budget_numeric")
    # If budget is disclosed, use the same style threshold as other scripts.
    if isinstance(budget_value, int) and budget_value < 50000:
        return None
    return job


def show_noti(job: Dict, category_id: int) -> None:
    category_name = CATEGORY_NAMES.get(category_id, str(category_id))
    text = (
        "Coconala New Task\n"
        f"{category_name}\n"
        f"{job['title']}\n"
        f"Budget: {job['budget']}\n"
        f"Posted: {job['posted_at']}\n"
        f"Client: {job['user']}\n"
        f"Link: {job['url']}"
    )
    if not slack_client:
        print(text)
        return

    try:
        slack_client.chat_postMessage(channel=CHANNEL_ID, text=text)
    except SlackApiError as e:
        if hasattr(e, "response") and isinstance(e.response, dict):
            print(f"Slack error: {e.response.get('error', e)}")
        else:
            print(f"Slack error: {e}")


if __name__ == "__main__":
    categories = [11, 22, 28]
    count = [0, 0, 0]
    seen_ids = [[], [], []]
    i = 0
    duration = 0.0
    pre_duration = 0.0

    while True:
        try:
            category_id = categories[i % len(categories)]
            url = CATEGORY_URLS[category_id]

            duration += pre_duration
            if category_id == categories[0]:
                print()
                print()
                print(
                    f"~~~~~~~~~~~~~~~~ Count:{(math.floor(i / len(categories)) + 1)} "
                    f"Duration: {duration:.2f}s ~~~~~~~~~~~~~~~~"
                )
                print()
                duration = 0.0
            print(
                f"===== {CATEGORY_NAMES.get(category_id, category_id)} "
                f"Duration: {pre_duration:.2f}s ====="
            )

            start = time.time()
            lines = fetch_text_lines(url)
            parsed_jobs = parse_jobs_from_lines(lines, url)
            filtered_jobs = [job_filter(job) for job in parsed_jobs]

            idx = i % len(categories)
            for job in filtered_jobs:
                if not job:
                    continue

                job_id = job["id"]
                if count[idx] == 0:
                    seen_ids[idx].append(job_id)
                    print(job["title"])
                    print(job["posted_at"])
                    continue

                if job_id not in seen_ids[idx]:
                    seen_ids[idx].append(job_id)
                    show_noti(job, category_id)

            if len(seen_ids[idx]) > 300:
                seen_ids[idx] = seen_ids[idx][-300:]

            end = time.time()
            pre_duration = end - start
            count[idx] += 1
            i += 1
            time.sleep(1)
        except Exception as e:
            print(f"Error: {e}")
            time.sleep(1)
            count = [0 for _ in categories]
            seen_ids = [[] for _ in categories]
            i = 0
