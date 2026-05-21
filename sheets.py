"""Shared Google Sheets logging for the Crowdworks and Lancers job watchers.

Both watchers append one row per newly-detected job into a single spreadsheet
(separate tabs). Auth is lazy and any failure disables logging gracefully so a
broken/expired service account never stops the Slack notifications.
"""

import datetime
import re
from pathlib import Path

ROW_HEIGHT_PX = 50

SPREADSHEET_ID = "1-PL8BvUVVczQ86XJY_e3wm8BMHs3fU4AzBeoI6Yryvk"
SERVICE_ACCOUNT_FILE = Path("service_account.json")

# gid of each tab inside the spreadsheet (from the sheet URLs).
CROWDWORKS_GID = 0
LANCERS_GID = 1773383551

_spreadsheet = None
_worksheets: dict = {}
_disabled = False


def _get_spreadsheet():
    global _spreadsheet, _disabled
    if _disabled:
        return None
    if _spreadsheet is not None:
        return _spreadsheet

    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as exc:
        print(f"Google Sheets logging disabled (missing dependency: {exc}). "
              f"Run: pip install gspread google-auth")
        _disabled = True
        return None

    if not SERVICE_ACCOUNT_FILE.exists():
        print(f"Google Sheets logging disabled (no credentials at {SERVICE_ACCOUNT_FILE}).")
        _disabled = True
        return None

    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets"]
        creds = Credentials.from_service_account_file(str(SERVICE_ACCOUNT_FILE), scopes=scopes)
        _spreadsheet = gspread.authorize(creds).open_by_key(SPREADSHEET_ID)
    except Exception as exc:
        print(f"Google Sheets logging disabled (auth/open failed): {exc}")
        _disabled = True
        return None
    return _spreadsheet


def _get_worksheet(gid: int):
    if gid in _worksheets:
        return _worksheets[gid]
    spreadsheet = _get_spreadsheet()
    worksheet = None
    if spreadsheet is not None:
        try:
            worksheet = spreadsheet.get_worksheet_by_id(gid)
        except Exception as exc:
            print(f"Google Sheets: worksheet gid={gid} unavailable: {exc}")
    _worksheets[gid] = worksheet
    return worksheet


def _hyperlink(url: str, text: str) -> str:
    text = (text or "").replace('"', '""')
    url = (url or "").replace('"', '""')
    if not url:
        return text
    return f'=HYPERLINK("{url}","{text}")'


def _set_row_height(worksheet, append_result) -> None:
    """Set the just-appended row's height to ROW_HEIGHT_PX. Best-effort."""
    try:
        updated_range = append_result["updates"]["updatedRange"]  # e.g. "Lancers!A7:E7"
        start_cell = updated_range.split("!")[-1].split(":")[0]    # "A7"
        match = re.search(r"(\d+)", start_cell)
        if not match:
            return
        row_index = int(match.group(1))  # 1-based
        worksheet.spreadsheet.batch_update({
            "requests": [{
                "updateDimensionProperties": {
                    "range": {
                        "sheetId": worksheet.id,
                        "dimension": "ROWS",
                        "startIndex": row_index - 1,
                        "endIndex": row_index,
                    },
                    "properties": {"pixelSize": ROW_HEIGHT_PX},
                    "fields": "pixelSize",
                }
            }]
        })
    except Exception as exc:
        print(f"Google Sheets: could not set row height: {exc}")


def append_job_row(gid: int, category: str, title: str, detail_url: str,
                    estimate: str, content: str) -> bool:
    """Append one job: [datetime, category, title-link, estimate, content, url].

    Only ever appends a new row — existing rows are never modified or deleted.
    Returns True if the row was written, False if logging is unavailable.
    Never raises — Sheets logging must not break the notification path.
    """
    worksheet = _get_worksheet(gid)
    if worksheet is None:
        return False

    # Leading apostrophe forces Sheets to keep the timestamp as literal text
    # (otherwise USER_ENTERED parses it to a date serial and reformats it).
    row = [
        "'" + datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"),
        category or "",
        _hyperlink(detail_url, title),
        estimate or "",
        content or "",
        detail_url or "",
    ]
    try:
        result = worksheet.append_row(row, value_input_option="USER_ENTERED")
        _set_row_height(worksheet, result)
        return True
    except Exception as exc:
        print(f"Google Sheets append failed (gid={gid}): {exc}")
        return False
