#!/usr/bin/env python3
"""
iWatch4u — Pipeline principal (100 % automatisé) :
  1. Scraper les sources de vidéos virales        (scraper.py)
  2. Générer titres/descriptions/tags via Groq AI (groq_processor.py)
  3. Planifier la publication : 4 vidéos par heure (data/videos.json)

Le frontend lit videos.json et ne révèle que les vidéos dont
`publish_at` <= maintenant. Aucune vidéo n'est téléchargée : seuls
les liens d'embed officiels sont conservés.

Usage :
    python main.py                     # cycle complet
    python main.py --max-items 8       # limite le nombre d'ajouts
    python main.py --dry-run           # n'écrit pas videos.json
"""

import argparse
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from groq_processor import generate_metadata
from scraper import scrape_all

# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent
DATA_FILE = BASE_DIR / "data" / "videos.json"
PUBLISH_INTERVAL = timedelta(minutes=15)  # 4 vidéos par heure

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("iwatch4u.main")


# ---------------------------------------------------------------------------

def load_data() -> dict:
    """Charge data/videos.json (ou initialise une structure vide)."""
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, encoding="utf-8") as f:
                payload = json.load(f)
            if isinstance(payload.get("videos"), list):
                return payload
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("videos.json illisible (%s), réinitialisation.", exc)
    return {"videos": []}


def save_data(payload: dict) -> None:
    """Écrit data/videos.json de façon atomique."""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp_file = DATA_FILE.with_suffix(".tmp")
    with open(tmp_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(tmp_file, DATA_FILE)


def compute_publish_base(videos: list[dict]) -> datetime:
    """
    Point de départ de la planification :
      - si des vidéos sont déjà programmées dans le futur -> juste après la dernière ;
      - sinon -> l'heure courante.
    Garantit exactement 1 heure entre chaque nouvelle publication.
    """
    now = datetime.now(timezone.utc)
    latest = None
    for video in videos:
        raw = video.get("publish_at")
        if not raw:
            continue
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            continue
        if dt > now and (latest is None or dt > latest):
            latest = dt
    return latest + PUBLISH_INTERVAL if latest else now


def enrich_and_schedule(items: list[dict], existing: list[dict],
                        max_items: int) -> int:
    """
    Pour chaque nouvel item : appel Groq (titre/description/tags),
    calcul du publish_at (dernière programmation + 1 h), ajout au JSON.
    Retourne le nombre d'items ajoutés.
    """
    seen_ids = {v.get("id") for v in existing}
    next_slot = compute_publish_base(existing)
    added = 0

    for item in items:
        if added >= max_items:
            break
        if item["id"] in seen_ids:
            logger.debug("Déjà présent, ignor : %s", item["title"][:60])
            continue

        logger.info("Traitement IA : %s", item["title"][:70])
        meta = generate_metadata(item["title"], item["description"])

        entry = {
            "id": item["id"],
            "title": (meta or {}).get("title") or item["title"],
            "description": (meta or {}).get("description")
                           or item["description"]
                           or "Une vidéo virale à ne pas manquer.",
            "tags": (meta or {}).get("tags") or ["viral"],
            "embed_url": item["embed_url"],
            "thumbnail": item["thumbnail"] or "",
            "source": item["source"],
            "publish_at": next_slot.isoformat(timespec="seconds").replace(
                "+00:00", "Z"
            ),
        }

        existing.append(entry)
        next_slot += PUBLISH_INTERVAL
        added += 1
        logger.info("  ✅ Programmée pour %s — %s",
                    entry["publish_at"], entry["title"][:60])

    return added


def main() -> None:
    parser = argparse.ArgumentParser(description="Pipeline iWatch4u")
    parser.add_argument("--max-items", type=int,
                        default=int(os.environ.get("MAX_ITEMS", "5")),
                        help="Nombre max de nouvelles vidéos ajoutées par exécution")
    parser.add_argument("--dry-run", action="store_true",
                        help="N'écrit pas dans data/videos.json")
    args = parser.parse_args()

    logger.info("=== iWatch4u — démarrage du pipeline ===")

    payload = load_data()
    existing = payload["videos"]

    items = scrape_all()
    if not items:
        logger.warning("Aucun item récupéré. Fin sans modification.")
        return

    added = enrich_and_schedule(items, existing, args.max_items)
    existing.sort(key=lambda v: v.get("publish_at", ""))

    if args.dry_run:
        logger.info("[DRY-RUN] %d vidéo(s) auraient été ajoutée(s).", added)
        return

    save_data({"videos": existing})
    logger.info("=== Terminé : %d ajout(s) — total %d vidéos en base ===",
                added, len(existing))


if __name__ == "__main__":
    main()
