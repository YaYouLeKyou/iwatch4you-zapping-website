#!/usr/bin/env python3
"""
iWatch4u - Scraper de vidéos virales (zapping web).
Récupère les flux RSS de plusieurs sources, extrait titres/liens/miniatures
et convertit les URLs en liens d'intégration (iframe embed).
Aucun fichier vidéo n'est téléchargé : uniquement des liens d'embed légaux.
"""

import hashlib
import logging
import re
import warnings
from concurrent.futures import ThreadPoolExecutor

import requests
from bs4 import BeautifulSoup, XMLParsedAsHTMLWarning

# On parse volontairement les flux RSS/Atom avec html.parser : le filtre
# évite le warning répété de BeautifulSoup dans les logs.
warnings.filterwarnings("ignore", category=XMLParsedAsHTMLWarning)

logger = logging.getLogger("iwatch4u.scraper")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    )
}

# (connect, read) — évite de bloquer indéfiniment sur une source lente.
TIMEOUT = (8, 12)

# ---------------------------------------------------------------------------
# Sources à inspecter (flux RSS / Atom). Ajoutez librement vos propres flux.
# Focus : zapping du web, fails, insolite, viral "crazy stuff"
# ---------------------------------------------------------------------------
FEEDS = [
    # Koreus - flux principal des vidéos virales (conservé)
    "https://www.koreus.com/rss/videos.xml",
    # Chaîne YouTube Fail Army (compilations de fails virals)
    "https://www.youtube.com/feeds/videos.xml?user=FailArmy",
    # Chaîne YouTube TheTryGuys (content viral/entertaining)
    "https://www.youtube.com/feeds/videos.xml?user=TheTryGuys",
    # Site Break - fails et contenus drôles
    "https://www.break.com/rss.xml",
]

YOUTUBE_ID_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/)|youtu\.be/)([\w-]{11})"
)
DAILYMOTION_RE = re.compile(r"dailymotion\.com/video/([a-z0-9]+)", re.IGNORECASE)


def _text(node) -> str:
    """Extrait le texte nettoyé d'un noeud BeautifulSoup."""
    return node.get_text(strip=True) if node else ""


def to_embed_url(url: str) -> str | None:
    """
    Convertit une URL de vidéo en URL d'intégration (embed).
    Retourne None si la plateforme n'est pas supportée.
    """
    if not url:
        return None

    m = YOUTUBE_ID_RE.search(url)
    if m:
        return f"https://www.youtube-nocookie.com/embed/{m.group(1)}"

    m = DAILYMOTION_RE.search(url)
    if m:
        return f"https://www.dailymotion.com/embed/video/{m.group(1)}"

    # Vimeo
    m = re.search(r"vimeo\.com/(\d+)", url)
    if m:
        return f"https://player.vimeo.com/video/{m.group(1)}"

    return None


def thumbnail_for_url(url: str) -> str | None:
    """Miniature officielle déduite de l'URL de la vidéo (sans scraping lourd)."""
    m = YOUTUBE_ID_RE.search(url or "")
    if m:
        return f"https://i.ytimg.com/vi/{m.group(1)}/hqdefault.jpg"

    m = DAILYMOTION_RE.search(url or "")
    if m:
        return f"https://www.dailymotion.com/thumbnail/video/{m.group(1)}"

    m = re.search(r"vimeo\.com/(\d+)", url or "")
    if m:
        return f"https://vumbnail.com/{m.group(1)}.jpg"

    return None


def _parse_feed(feed_url: str) -> list[dict]:
    """Télécharge et parse un flux RSS/Atom avec BeautifulSoup."""
    resp = requests.get(feed_url, headers=HEADERS, timeout=TIMEOUT)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.content, "html.parser")  # gère aussi le XML

    items: list[dict] = []

    entries = soup.find_all("item") or soup.find_all("entry")
    for entry in entries:
        title = _text(entry.find("title"))
        link_node = entry.find("link")
        link = ""
        if link_node:
            link = (link_node.get("href") or "").strip() or _text(link_node)
            if not link:
                link = link_node.get_text(strip=True)

        desc_node = entry.find("description") or entry.find("summary")
        description = _text(desc_node)
        # Nettoyage basique HTML dans la description
        description = re.sub(r"<[^>]+>", " ", description)
        description = re.sub(r"\s+", " ", description).strip()

        # Miniature : media:thumbnail / media:content / enclosure
        thumbnail = None
        for tag_name, attr in (("media:thumbnail", "url"),
                               ("media:content", "url"),
                               ("enclosure", "url")):
            tag = entry.find(tag_name)
            while tag:
                url_attr = tag.get(attr, "")
                ttype = tag.get("type", "")
                if url_attr and (ttype.startswith("image") or not ttype):
                    thumbnail = url_attr
                    break
                tag = tag.find_next(tag_name)
            if thumbnail:
                break

        items.append({
            "title": title,
            "link": link,
            "description": description[:800],
            "scraped_thumbnail": thumbnail,
        })

    return items


def _safe_parse_feed(feed_url: str) -> list[dict]:
    """Parse un flux en isolant les erreurs : une source HS retourne []."""
    logger.info("Inspection de la source : %s", feed_url)
    try:
        return _parse_feed(feed_url)
    except Exception as exc:  # noqa: BLE001 - une source HS ne bloque pas le reste
        logger.warning("Source indisponible (%s) : %s", feed_url, exc)
        return []


def scrape_all(feeds: list[str] | None = None) -> list[dict]:
    """
    Inspecte toutes les sources (en parallèle) et retourne une liste
    d'items normalisés :
    { id, title, description, embed_url, thumbnail, source }
    Les items sans embed possible sont ignorés (on n'affiche que de l'embed).
    """
    results: dict[str, dict] = {}
    feed_list = feeds or FEEDS

    # Téléchargement des flux en parallèle : le temps total reste borné par
    # le flux le plus lent au lieu de la somme de tous les timeouts.
    with ThreadPoolExecutor(max_workers=min(5, len(feed_list))) as pool:
        parsed_feeds = pool.map(_safe_parse_feed, feed_list)

        for entries in parsed_feeds:
            for entry in entries:
                link = entry["link"]
                if not link:
                    continue

                embed_url = to_embed_url(link)
                if not embed_url:
                    # Lien non intégrable (page HTML, article...) : on ignore.
                    logger.debug("Lien ignoré (pas d'embed) : %s", link)
                    continue

                item_id = hashlib.sha256(embed_url.encode()).hexdigest()[:16]
                if item_id in results:
                    continue

                results[item_id] = {
                    "id": item_id,
                    "title": entry["title"],
                    "description": entry["description"],
                    "embed_url": embed_url,
                    "thumbnail": entry["scraped_thumbnail"] or thumbnail_for_url(link),
                    "source": link,
                }

    logger.info("%d nouvelle(s) vidéo(s) récupérée(s) au total.", len(results))
    return list(results.values())
