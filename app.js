/* ============================================================
   iWatch4u — Frontend dynamique
   Lit data/videos.json et ne révèle que les vidéos publiées
   (publish_at <= maintenant). Rafraîchit chaque minute.
   ============================================================ */
(() => {
  "use strict";

  const DATA_URL = new URL("data/videos.json", window.location.href).href;

  const grid = document.getElementById("video-grid");
  const emptyState = document.getElementById("empty-state");
  const tagFilters = document.getElementById("tag-filters");
  const banner = document.getElementById("next-video-banner");
  const countdownEl = document.getElementById("countdown");

  const modal = document.getElementById("player-modal");
  const playerIframe = document.getElementById("player-iframe");
  const playerTitle = document.getElementById("player-title");
  const playerDesc = document.getElementById("player-description");
  const playerTags = document.getElementById("player-tags");
  const playerSource = document.getElementById("player-source");

  let allVideos = [];
  let activeTag = null;

  /* ---------------- Chargement des données ---------------- */

  async function loadVideos() {
    try {
      const res = await fetch(`${DATA_URL}?t=${Date.now()}`, { cache: "no-store" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const payload = await res.json();
      allVideos = (payload.videos || []).map(normalizeVideo);
      render();
    } catch (err) {
      console.error("iWatch4u : impossible de charger videos.json", err);
      grid.innerHTML =
        '<p class="empty-state">Erreur de chargement du contenu. 🔄 Réessayez plus tard.</p>';
    }
  }

  function normalizeVideo(v) {
    return {
      id: v.id,
      title: v.title || "Vidéo sans titre",
      description: v.description || "",
      embed_url: v.embed_url,
      thumbnail: v.thumbnail || "",
      source: v.source || "#",
      tags: Array.isArray(v.tags) ? v.tags.slice(0, 5) : [],
      publishAt: v.publish_at ? new Date(v.publish_at).getTime() : Date.now(),
    };
  }

  /* ---------------- Rendu ---------------- */

  function publishedVideos() {
    const now = Date.now();
    return allVideos
      .filter((v) => v.publishAt <= now)
      .sort((a, b) => b.publishAt - a.publishAt); // + récentes en premier
  }

  function nextScheduledVideo() {
    return allVideos
      .filter((v) => v.publishAt > Date.now())
      .sort((a, b) => a.publishAt - b.publishAt)[0] || null;
  }

  function render() {
    renderTagFilters();
    updateCountdown();

    const visible = publishedVideos().filter(
      (v) => !activeTag || v.tags.includes(activeTag)
    );

    grid.innerHTML = "";
    emptyState.classList.toggle("hidden", publishedVideos().length > 0);

    for (const video of visible) {
      grid.appendChild(createCard(video));
    }
  }

  function createCard(video) {
    const card = document.createElement("article");
    card.className = "video-card";
    card.setAttribute("role", "button");
    card.setAttribute("tabindex", "0");

    const thumb = document.createElement("div");
    thumb.className = "thumb-wrapper";

    if (video.thumbnail) {
      const img = document.createElement("img");
      img.src = video.thumbnail;
      img.alt = video.title;
      img.loading = "lazy";
      img.onerror = () => img.remove();
      thumb.appendChild(img);
    }

    const badge = document.createElement("div");
    badge.className = "play-badge";
    badge.innerHTML = "<span>▶</span>";
    thumb.appendChild(badge);

    const body = document.createElement("div");
    body.className = "card-body";

    const title = document.createElement("h3");
    title.className = "card-title";
    title.textContent = video.title;
    body.appendChild(title);

    if (video.description) {
      const desc = document.createElement("p");
      desc.className = "card-desc";
      desc.textContent = video.description;
      body.appendChild(desc);
    }

    const meta = document.createElement("div");
    meta.className = "card-meta";

    const tagsWrap = document.createElement("div");
    tagsWrap.className = "card-tags";
    for (const tag of video.tags.slice(0, 3)) {
      const chip = document.createElement("span");
      chip.className = "card-tag";
      chip.textContent = `#${tag}`;
      tagsWrap.appendChild(chip);
    }

    const date = document.createElement("span");
    date.className = "card-date";
    date.textContent = formatDate(video.publishAt);

    meta.append(tagsWrap, date);
    body.appendChild(meta);
    card.append(thumb, body);

    card.addEventListener("click", () => openPlayer(video));
    card.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") openPlayer(video);
    });

    return card;
  }

  function renderTagFilters() {
    const counts = new Map();
    for (const v of publishedVideos()) {
      for (const t of v.tags) counts.set(t, (counts.get(t) || 0) + 1);
    }
    const topTags = [...counts.entries()]
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10)
      .map(([t]) => t);

    tagFilters.innerHTML = "";
    if (topTags.length < 2) {
      if (activeTag) activeTag = null;
      return;
    }

    for (const tag of topTags) {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `tag-chip${tag === activeTag ? " active" : ""}`;
      btn.textContent = `#${tag}`;
      btn.addEventListener("click", () => {
        activeTag = activeTag === tag ? null : tag;
        render();
      });
      tagFilters.appendChild(btn);
    }
  }

  /* ---------------- Countdown « 1 vidéo / heure » ---------------- */

  function updateCountdown() {
    banner.classList.toggle("hidden", !nextScheduledVideo());
    tick();
  }

  function tick() {
    const next = nextScheduledVideo();
    if (!next) return;
    const diff = Math.max(0, next.publishAt - Date.now());
    const h = String(Math.floor(diff / 3600000)).padStart(2, "0");
    const m = String(Math.floor(diff / 60000) % 60).padStart(2, "0");
    const s = String(Math.floor(diff / 1000) % 60).padStart(2, "0");
    countdownEl.textContent = `${h}:${m}:${s}`;
  }

  setInterval(tick, 1000);          // compte à rebours à la seconde
  setInterval(render, 60 * 1000);   // révèle les nouvelles vidéos chaque minute

  /* ---------------- Lecteur modal ---------------- */

  function openPlayer(video) {
    const sep = video.embed_url.includes("?") ? "&" : "?";
    playerIframe.src = `${video.embed_url}${sep}autoplay=1`;
    playerTitle.textContent = video.title;
    playerDesc.textContent = video.description;

    playerTags.innerHTML = "";
    for (const tag of video.tags) {
      const chip = document.createElement("span");
      chip.className = "card-tag";
      chip.textContent = `#${tag}`;
      playerTags.appendChild(chip);
    }

    playerSource.href = video.source;
    modal.classList.remove("hidden");
    document.body.style.overflow = "hidden";
  }

  function closePlayer() {
    playerIframe.src = ""; // stoppe la lecture
    modal.classList.add("hidden");
    document.body.style.overflow = "";
  }

  modal.addEventListener("click", (e) => {
    if (e.target.hasAttribute("data-close")) closePlayer();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !modal.classList.contains("hidden")) closePlayer();
  });

  /* ---------------- Utilitaires ---------------- */

  function formatDate(ms) {
    return new Intl.DateTimeFormat("fr-FR", {
      day: "numeric",
      month: "short",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(ms));
  }

  document.getElementById("year").textContent = new Date().getFullYear();

  loadVideos();
})();

