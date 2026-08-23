#!/usr/bin/env python3
"""
iWatch4u - Traitement IA via l'API Groq (modèles Llama 3).
Génère : titre accrocheur FR, description courte FR, et tags.
"""

import json
import logging
import os
import re

import requests

logger = logging.getLogger("iwatch4u.groq")

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-20b"

SYSTEM_PROMPT = (
    "Tu es l'éditeur en chef du site iWatch4u, un agrégateur français de "
    "zappings web et de vidéos virales. Tu écris des titres courts, punchy et "
    "accrocheurs en français, dans le style des sites de zapping (Koreus, "
    "Spi0n). Tu réponds STRICTEMENT au format JSON, sans texte autour."
)

USER_PROMPT_TEMPLATE = """Génère le contenu éditorial pour cette vidéo virale.

Titre original : {title}
Description originale : {description}

Réponds UNIQUEMENT avec ce JSON (valide, sans markdown) :
{{
  "title": "nouveau titre accrocheur en français (max 90 caractères)",
  "description": "résumé rédigé en 2 à 3 phrases en français",
  "tags": ["tag1", "tag2", "tag3"]
}}
Règles :
- 3 à 5 tags pertinents, en minuscules, sans accent.
- Le titre ne doit pas être un clicbait mensonger mais rester très attractif."""


class GroqError(Exception):
    """Erreur lors de l'appel à l'API Groq."""


def _get_api_key() -> str:
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise GroqError(
            "La variable d'environnement GROQ_API_KEY n'est pas définie."
        )
    return key


def _extract_json(raw: str) -> dict:
    """Extrait le premier objet JSON valide du texte renvoyé par le modèle."""
    raw = raw.strip()
    # Retire les éventuels blocs ```json ... ```
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw)
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        raise ValueError("Aucun objet JSON trouvé dans la réponse.")
    return json.loads(match.group(0))


def generate_metadata(title: str, description: str) -> dict | None:
    """
    Appelle Groq et retourne {"title", "description", "tags"}.
    Retourne None en cas d'échec (le pipeline continuera avec les valeurs
    d'origine, jamais bloqué).
    """
    payload = {
        "model": os.environ.get("GROQ_MODEL", DEFAULT_MODEL),
        "temperature": 0.7,
        "max_completion_tokens": 1500,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": USER_PROMPT_TEMPLATE.format(
                    title=title or "(sans titre)",
                    description=description[:600] or "(aucune description)",
                ),
            },
        ],
    }

    try:
        resp = requests.post(
            GROQ_API_URL,
            headers={
                "Authorization": f"Bearer {_get_api_key()}",
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        if not resp.ok:
            logger.error("Groq HTTP %d: %s", resp.status_code, resp.text)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
    except Exception as exc:  # noqa: BLE001
        logger.error("Appel Groq échoué : %s", exc)
        return None

    try:
        data = _extract_json(content)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.error("Réponse Groq illisible (%s) : %r", exc, content[:200])
        return None

    tags_raw = data.get("tags", [])
    if isinstance(tags_raw, str):
        tags_raw = [t.strip() for t in tags_raw.split(",")]

    return {
        "title": str(data.get("title") or "").strip()[:120],
        "description": str(data.get("description") or "").strip(),
        "tags": [str(t).lower().strip() for t in tags_raw if str(t).strip()][:5],
    }
