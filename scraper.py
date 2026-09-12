#!/usr/bin/env python3
"""
Croglobal RSS scraper
Dohvaća naslove, linkove i točno vrijeme objave s liste hrvatskih portala
(RSS feedovi) i sprema ih u data/latest.json.

Pokreće se periodički preko GitHub Actions (vidi .github/workflows/scrape.yml).
"""

import json
import time
from datetime import datetime, timezone
from pathlib import Path

import feedparser

# --- Konfiguracija izvora ---
# Dodaj/ukloni feedove ovdje. "source" je čitljivo ime portala za tablicu u /objava.
FEEDS = [
    {"source": "Index.hr", "url": "https://www.index.hr/rss/vijesti"},
    {"source": "Index.hr Sport", "url": "https://www.index.hr/rss/sport"},
    {"source": "HRT Vijesti", "url": "https://vijesti.hrt.hr/rss"},
    {"source": "N1 Hrvatska", "url": "https://hr.n1info.com/feed/"},
    {"source": "Tportal", "url": "https://www.tportal.hr/rss"},
    {"source": "Google News HR", "url": "https://news.google.com/rss?hl=hr&gl=HR&ceid=HR:hr"},
]

OUTPUT_PATH = Path(__file__).parent / "data" / "latest.json"
MAX_ITEMS_PER_FEED = 30
RETENTION_HOURS = 48  # koliko dugo čuvati stavke u JSON-u prije brisanja starih


def parse_feed(feed_conf):
    """Dohvati jedan RSS feed i vrati listu stavki s normaliziranim poljima."""
    items = []
    try:
        parsed = feedparser.parse(feed_conf["url"])
        for entry in parsed.entries[:MAX_ITEMS_PER_FEED]:
            published = None
            # feedparser daje 'published_parsed' kao time.struct_time (UTC-normalizirano)
            if getattr(entry, "published_parsed", None):
                published = datetime.fromtimestamp(
                    time.mktime(entry.published_parsed), tz=timezone.utc
                ).isoformat()
            elif getattr(entry, "updated_parsed", None):
                published = datetime.fromtimestamp(
                    time.mktime(entry.updated_parsed), tz=timezone.utc
                ).isoformat()

            items.append(
                {
                    "source": feed_conf["source"],
                    "title": entry.get("title", "").strip(),
                    "link": entry.get("link", "").strip(),
                    "published_utc": published,
                }
            )
    except Exception as e:
        # Ne rušimo cijeli run zbog jednog feeda koji ne radi
        items.append(
            {
                "source": feed_conf["source"],
                "error": str(e),
                "title": None,
                "link": None,
                "published_utc": None,
            }
        )
    return items


def load_existing():
    if OUTPUT_PATH.exists():
        try:
            return json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
        except Exception:
            return {"items": []}
    return {"items": []}


def prune_old(items):
    """Makni stavke starije od RETENTION_HOURS da JSON ne raste beskonačno."""
    cutoff = time.time() - RETENTION_HOURS * 3600
    kept = []
    for it in items:
        if not it.get("published_utc"):
            kept.append(it)  # zadrži stavke bez datuma (rijetko, npr. greška feeda)
            continue
        try:
            ts = datetime.fromisoformat(it["published_utc"]).timestamp()
            if ts >= cutoff:
                kept.append(it)
        except Exception:
            kept.append(it)
    return kept


def main():
    existing = load_existing()
    existing_links = {it["link"] for it in existing["items"] if it.get("link")}

    new_items = []
    for feed_conf in FEEDS:
        new_items.extend(parse_feed(feed_conf))

    # Dedup po linku, zadrži postojeće + dodaj samo nove
    merged = list(existing["items"])
    added = 0
    for it in new_items:
        if it.get("link") and it["link"] not in existing_links:
            merged.append(it)
            existing_links.add(it["link"])
            added += 1

    merged = prune_old(merged)
    # Sortiraj najnovije prvo
    merged.sort(key=lambda x: x.get("published_utc") or "", reverse=True)

    output = {
        "last_run_utc": datetime.now(timezone.utc).isoformat(),
        "items_total": len(merged),
        "items_added_this_run": added,
        "items": merged,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Gotovo. Ukupno stavki: {len(merged)}, novih ovaj run: {added}")


if __name__ == "__main__":
    main()
