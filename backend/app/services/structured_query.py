"""
Structured Query Handler — handles ranking and comparison queries on tabular data.

When a query asks "which client had highest/lowest X", vector search alone
cannot answer correctly because it can't sort numeric columns.

This handler:
1. Detects ranking/comparison query intent
2. Fetches ALL chunks from the relevant sheet
3. Parses the structured data
4. Returns the answer with actual sorted data
"""
import re
import logging
from typing import List, Dict, Any, Optional, Tuple

from app.core.vector_store import get_qdrant
from qdrant_client.models import Filter, FieldCondition, MatchText

log = logging.getLogger("intellirag.structured_query")

# Query patterns that indicate ranking/comparison intent
RANKING_PATTERNS = [
    r'\b(highest|lowest|most|least|best|worst|top|bottom|largest|smallest)\b',
    r'\bwhich (client|customer|product|region|segment|division)\b',
    r'\bwhat (client|customer|product|region|segment|division)\b',
    r'\brank(ed|ing)?\b',
    r'\bcompare\b',
    r'\bmaximum|minimum\b',
]

RANKING_RE = re.compile('|'.join(RANKING_PATTERNS), re.IGNORECASE)

# Column name patterns for common metrics
METRIC_PATTERNS = {
    'growth': ['yoy growth', 'growth', 'yoy growth %'],
    'revenue': ['annual ($k)', 'annual', 'revenue', 'total revenue'],
    'profit': ['profit', 'net income', 'ebitda'],
    'margin': ['margin', 'gross margin'],
    'headcount': ['headcount', 'employees'],
    'nps': ['nps', 'net promoter'],
    'clients': ['active clients', 'clients'],
}


def is_ranking_query(question: str) -> bool:
    """Detect if a query is asking for ranked/comparative data."""
    return bool(RANKING_RE.search(question))


def extract_metric_from_query(question: str) -> str:
    """Identify which metric the user is asking about."""
    q = question.lower()
    for metric, patterns in METRIC_PATTERNS.items():
        if any(p in q for p in patterns):
            return metric
    return 'revenue'  # Default to revenue


def extract_direction(question: str) -> str:
    """Determine if asking for highest or lowest."""
    q = question.lower()
    if any(w in q for w in ['highest', 'most', 'best', 'largest', 'maximum', 'top', 'biggest']):
        return 'highest'
    if any(w in q for w in ['lowest', 'least', 'worst', 'smallest', 'minimum', 'bottom']):
        return 'lowest'
    return 'highest'  # Default


def parse_numeric(value: str) -> Optional[float]:
    """Parse a string value to float, handling %, $, K, M suffixes."""
    if not value or value in ('None', '', 'N/A', 'Active', 'New Q1'):
        return None
    try:
        # Remove common formatting
        clean = str(value).strip()
        clean = clean.replace('$', '').replace(',', '').replace(' ', '')
        clean = clean.replace('(', '-').replace(')', '')

        multiplier = 1.0
        if clean.endswith('M'):
            multiplier = 1_000_000
            clean = clean[:-1]
        elif clean.endswith('K'):
            multiplier = 1_000
            clean = clean[:-1]
        elif clean.endswith('%'):
            clean = clean[:-1]

        return float(clean) * multiplier
    except (ValueError, AttributeError):
        return None


async def handle_ranking_query(
    question: str,
    collection_name: str,
    filename_hint: Optional[str] = None,
) -> Optional[List[Dict]]:
    """
    Handle a ranking query by fetching all rows from the relevant sheet
    and sorting by the requested metric.

    Returns list of chunk dicts ordered by the metric, or None if not applicable.
    """
    metric = extract_metric_from_query(question)
    direction = extract_direction(question)
    q = question.lower()

    # Determine which sheet to search
    sheet_hint = None
    if any(w in q for w in ['client', 'customer']):
        sheet_hint = 'Client Analytics'
    elif any(w in q for w in ['product', 'product a', 'product b', 'product c']):
        sheet_hint = 'Product Analytics'
    elif any(w in q for w in ['department', 'headcount', 'employee', 'hr']):
        sheet_hint = 'Headcount'
    elif any(w in q for w in ['quarter', 'quarterly', 'q1', 'q2', 'q3', 'q4']):
        sheet_hint = 'Quarterly Deep Dive'

    if not sheet_hint:
        return None

    log.info(f"[StructuredQuery] Ranking query: metric={metric}, direction={direction}, sheet={sheet_hint}")

    client = get_qdrant()

    # Fetch all chunks from the relevant sheet
    try:
        kw_filter = Filter(must=[
            FieldCondition(key="text", match=MatchText(text=f"Sheet: {sheet_hint}"))
        ])
        if filename_hint:
            kw_filter.must.append(
                FieldCondition(key="filename", match=MatchText(text=filename_hint))
            )

        results = await client.scroll(
            collection_name=collection_name,
            scroll_filter=kw_filter,
            limit=200,
            with_payload=True,
        )
        points = results[0]

    except Exception as e:
        log.warning(f"[StructuredQuery] Scroll failed: {e}")
        return None

    if not points:
        return None

    # Parse each row chunk and extract the metric value
    scored_rows = []
    for point in points:
        text = point.payload.get('text', '')
        if not text or f"Sheet: {sheet_hint}" not in text:
            continue

        # Extract row identifier (first line after "Entry:")
        entry_match = re.search(r'Entry: (.+?)(?:\n|$)', text)
        if not entry_match:
            continue
        entry_name = entry_match.group(1).strip()

        # Skip header/total rows
        if entry_name in ('TOTAL', 'TOTAL / AVERAGE', 'Average', ''):
            continue

        # Find metric value in the text
        metric_value = None
        for pattern in METRIC_PATTERNS.get(metric, [metric]):
            # Look for "MetricName: value" pattern
            value_match = re.search(
                rf'{re.escape(pattern)}[:\s]+([+-]?[\d.,]+%?)',
                text,
                re.IGNORECASE
            )
            if value_match:
                metric_value = parse_numeric(value_match.group(1))
                if metric_value is not None:
                    break

        if metric_value is not None:
            scored_rows.append({
                'name': entry_name,
                'metric_value': metric_value,
                'metric': metric,
                'text': text,
                'filename': point.payload.get('filename', ''),
                'document_id': point.payload.get('document_id', ''),
                'chunk_index': point.payload.get('chunk_index', 0),
                'score': abs(metric_value),  # Use metric value as score
            })

    if not scored_rows:
        return None

    # Sort by metric value
    scored_rows.sort(
        key=lambda x: x['metric_value'],
        reverse=(direction == 'highest')
    )

    log.info(f"[StructuredQuery] Found {len(scored_rows)} rows, "
             f"top: {scored_rows[0]['name']} = {scored_rows[0]['metric_value']}")

    return scored_rows
