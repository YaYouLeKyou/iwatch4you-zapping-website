#!/usr/bin/env python3
"""
iWatch4u - Traitement IA : Groq en principal, Gemini en repli.
Génère : titre accrocheur FR, description courte FR, et tags.
Si Groq échoue (quota épuisé, erreur réseau…), bascule automatiquement
sur l'API Google Gemini. En dernier recours, retourne None et le pipeline
utilise les valeurs d'origine.
"""

import json
import logging
import os
import re
import time

import requests

logger = logging.getLogger("iwatch4u.groq")

GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-20b"

GEMINI_API_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)
DEFAULT_GEMINI_MODEL = "gemini-2.5-flash"

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


# Coupe-circuits internes au run : évitent de répéter des appels voués à
# l'échec (quota épuisé, API en panne) et bornent la durée totale.
_groq_disabled = False      # quota Groq définitivement épuisé -> repli direct
_gemini_failures = 0        # après 3 échecs consécutifs, Gemini est ignoré
_MAX_GEMINI_FAILURES = 3


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


def _build_user_prompt(title: str, description: str) -> str:
    """Construit le prompt utilisateur commun aux deux fournisseurs."""
    return USER_PROMPT_TEMPLATE.format(
        title=title or "(sans titre)",
        description=description[:600] or "(aucune description)",
    )


def _call_groq(title: str, description: str) -> str | None:
    """
    Appelle l'API Groq. Retourne le contenu texte, ou None en cas d'échec
    (avec 1 nouvelle tentative après pause sur un HTTP 429).
    Une fois le quota mensuel épuisé, Groq est désactivé pour tout le reste
    du run (bascule immédiate sur Gemini).
    """
    global _groq_disabled
    payload = {
        "model": os.environ.get("GROQ_MODEL", DEFAULT_MODEL),
        "temperature": 0.7,
        "max_completion_tokens": 1500,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(title, description)},
        ],
    }

    max_attempts = 2
    for attempt in range(1, max_attempts + 1):
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
            if resp.status_code == 429:
                # Quota mensuel ou rate-limit dépassé : inutile de retenter
                # immédiatement, mais une seule pause peut suffire pour un
                # simple rate-limit à la minute.
                if attempt < max_attempts:
                    logger.warning(
                        "Groq rate-limit/quota (HTTP 429), nouvelle "
                        "tentative dans 15 s…"
                    )
                    time.sleep(15)
                    continue
                logger.warning(
                    "Quota Groq épuisé (HTTP 429) — Groq désactivé pour "
                    "le reste du run."
                )
                _groq_disabled = True
            elif not resp.ok:
                logger.error("Groq HTTP %d: %s", resp.status_code, resp.text)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:  # noqa: BLE001
            logger.error("Appel Groq échoué : %s", exc)
            return None
    return None


def _call_gemini(title: str, description: str) -> str | None:
    """
    Repli : appelle l'API Google Gemini (Generative Language API).
    Retourne le contenu texte, ou None en cas d'échec.
    """
    if not os.environ.get("GEMINI_API_KEY"):
        logger.warning("GEMINI_API_KEY non définie — repli indisponible.")
        return None

    model = os.environ.get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    payload = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": [
            {"role": "user", "parts": [{"text": _build_user_prompt(title, description)}]}
        ],
        "generationConfig": {
            "temperature": 0.7,
            "maxOutputTokens": 2048,
            "responseMimeType": "application/json",
        },
    }

    try:
        resp = requests.post(
            GEMINI_API_URL.format(model=model),
            headers={
                "x-goog-api-key": os.environ["GEMINI_API_KEY"],
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=30,
        )
        if not resp.ok:
            logger.error("Gemini HTTP %d: %s", resp.status_code, resp.text[:300])
            _gemini_failures += 1
            return None
        candidates = resp.json().get("candidates") or []
        parts = (
            candidates[0].get("content", {}).get("parts", [])
            if candidates
            else []
        )
        text = "".join(p.get("text", "") for p in parts).strip()
        if not text:
            logger.error("Réponse Gemini vide ou bloquée : %s",
                         str(resp.json())[:300])
            _gemini_failures += 1
            return None
        _gemini_failures = 0
        return text
    except Exception as exc:  # noqa: BLE001
        logger.error("Appel Gemini échoué : %s", exc)
        _gemini_failures += 1
        return None


def generate_metadata(title: str, description: str) -> dict | None:
    """
    Génère {"title", "description", "tags"} via Groq, avec repli Gemini.
    Retourne None si les deux fournisseurs échouent (le pipeline continuera
    avec les valeurs d'origine, jamais bloqué).

    Coupe-circuits : une fois le quota Groq épuisé, Groq n'est plus appelé ;
    après 3 échecs Gemini consécutifs, Gemini n'est plus appelé.
    """
    content = None if _groq_disabled else _call_groq(title, description)
    if content is None and _gemini_failures < _MAX_GEMINI_FAILURES:
        logger.info("Bascule sur le repli Gemini…")
        content = _call_gemini(title, description)
    if content is None:
        logger.error("Groq ET Gemini en échec — valeurs d'origine conservées.")
        return None

    try:
        data = _extract_json(content)
    except (ValueError, json.JSONDecodeError) as exc:
        logger.error("Réponse IA illisible (%s) : %r", exc, content[:200])
        return None

    tags_raw = data.get("tags", [])
    if isinstance(tags_raw, str):
        tags_raw = [t.strip() for t in tags_raw.split(",")]

    return {
        "title": str(data.get("title") or "").strip()[:120],
        "description": str(data.get("description") or "").strip(),
        "tags": [str(t).lower().strip() for t in tags_raw if str(t).strip()][:5],
    }
