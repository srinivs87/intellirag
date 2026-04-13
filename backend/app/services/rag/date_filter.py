"""
Date Filter Service — extracts date references from natural language questions.
"""
import re
import datetime
from typing import Optional

MONTH_MAP = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
}


def extract_date_filter(question: str) -> Optional[str]:
    """
    Extract a date string from a question if a specific date is mentioned.
    Returns format: "YYYY-MM-DD month_name DD YYYY" or None.

    Supports:
    - "July 29" → resolves to current or previous year
    - "Jan 16 2026" → explicit year
    - "the meeting on March 5th" → extracts date
    """
    q = question.lower()

    for month_name, month_num in MONTH_MAP.items():
        if month_name not in q and month_name[:3] not in q:
            continue

        day_match = re.search(r'\b(\d{1,2})\b', q)
        year_match = re.search(r'\b(202\d)\b', q)

        if year_match:
            year = year_match.group(1)
        else:
            year = _resolve_year(month_num, day_match)

        if not day_match:
            continue

        day = day_match.group(1).zfill(2)
        date_str = f"{year}-{month_num}-{day}"
        # Return date + month name for richer semantic matching
        return f"{date_str} {month_name} {day} {year}"

    return None


def _resolve_year(month_num: str, day_match) -> str:
    """Determine year: use current year if date is in past, else previous year."""
    now = datetime.datetime.now()
    try:
        day_val = int(day_match.group(1)) if day_match else 1
        candidate = datetime.datetime(now.year, int(month_num), day_val)
        return str(now.year) if candidate <= now else str(now.year - 1)
    except Exception:
        return str(now.year)
