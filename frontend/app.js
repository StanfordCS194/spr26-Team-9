// ---------- Supabase ----------
const SUPABASE_URL  = "https://nlcnbcpnljdizedritaj.supabase.co";
const SUPABASE_ANON = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5sY25iY3BubGpkaXplZHJpdGFqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzg0NTkyMDcsImV4cCI6MjA5NDAzNTIwN30.AU1xSkrfd3efDrsvCHAQXD_jsmWGu62eL9kVIuBxLak";
const sb = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON);
let currentUser = null;
let bookmarkedTitles = new Set();
let bookmarkIdMap    = {};
let sessionId = crypto.randomUUID();
let totalVisibleMs = 0;
let visibleSince = document.visibilityState === "visible" ? Date.now() : null;

function postEvent(event, payload = {}) {
  if (!currentUser) return;
  fetch("/api/events", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: currentUser.id, session_id: sessionId, event, payload }),
  }).catch((err) => console.error(`[events] ${event} failed:`, err.message));
}

sb.auth.onAuthStateChange((event, session) => {
  currentUser = session?.user ?? null;
  updateProfileBtn();
  const gate = document.getElementById("login-gate");
  if (currentUser) {
    gate.classList.add("hidden");
    loadUserBookmarks();
    if (event === "SIGNED_IN" || event === "INITIAL_SESSION") postEvent("new_search");
  } else {
    gate.classList.remove("hidden");
    bookmarkedTitles = new Set();
    bookmarkIdMap    = {};
  }
  if (currentView === "account") renderAccountView();
});

async function loadUserBookmarks() {
  if (!currentUser) return;
  const { data } = await sb.from("bookmarks").select("id, article_title");
  bookmarkedTitles = new Set((data || []).map(b => b.article_title));
  bookmarkIdMap    = {};
  (data || []).forEach(b => { bookmarkIdMap[b.article_title] = b.id; });
  if (timelineData.length) renderTimeline();
}

const TOP_N_PER_DATE = 5;

// Higher number = more credible. Sources not listed default to tier 1.
const SOURCE_CREDIBILITY = {
  "New York Times": 3,
  "theguardian":    3,
  "theatlantic":    3,
  "reuters":        3,
  "apnews":         3,
  "CNBC":           2,
  "independent":    2,
  "bbc":            2,
  "standard":       2,
  "detroitnews":    2,
};

function cleanSourceName(src) {
  return src
    .trim()
    .replace(/\.(com|co\.uk|co\.in|co\.nz|co\.za|co\.jp|org|net|uk|ie|us|io|tv|au|ca|de|fr|gov|edu)$/i, "");
}

function credibilityScore(src) {
  return SOURCE_CREDIBILITY[src] || 1;
}

const SOURCE_COLORS = [
  "#16A34A", "#2563EB", "#7C3AED", "#EA580C",
  "#DC2626", "#0891B2", "#D97706", "#DB2777",
  "#059669", "#4F46E5", "#65A30D", "#0D9488",
  "#E11D48", "#9333EA", "#0284C7", "#C2410C",
];
const sourceColorMap = {};

function assignSourceColors(sources) {
  sources.forEach((src, i) => {
    sourceColorMap[src] = SOURCE_COLORS[i % SOURCE_COLORS.length];
  });
}

function sourceColor(src) {
  return sourceColorMap[src] || "#94a3b8";
}

// Global state — populated after fetch
let timelineData = [];
let channelData  = {};
let selectedCompareTitles = [];
let selectedCompareArticles = [];
const MIN_COMPARE_ARTICLES = 2;
const MAX_COMPARE_ARTICLES = 3;
let currentQuery = null;

// ---------- Landing page ----------

const landingEl            = document.getElementById("landing");
const landingInput         = document.getElementById("landing-input");
const landingBtn           = document.getElementById("landing-btn");
const landingStatus        = document.getElementById("landing-status");
const landingProgress      = document.getElementById("landing-progress");
const landingProgressFill  = document.getElementById("landing-progress-fill");
const landingProgressLabel = document.getElementById("landing-progress-label");

const API_LABELS = ["NewsAPI", "NYT", "Currents API"];
// Estimated seconds each API takes — used to pace the smooth animation
const API_DURATIONS = [12, 28, 10]; // newsapi, nyt, current
const TOTAL_ESTIMATED_SECS = API_DURATIONS.reduce((a, b) => a + b, 0);

// Poll /api/ready on page load; disable search until articles are available
let _readyPoller = null;
function startReadyPolling() {
  landingBtn.disabled = true;
  landingInput.disabled = true;
  showLandingStatus("Loading articles… please wait.");

  _readyPoller = setInterval(async () => {
    try {
      const res = await fetch("/api/ready");
      const { ready } = await res.json();
      if (ready) {
        clearInterval(_readyPoller);
        _readyPoller = null;
        landingBtn.disabled = false;
        landingInput.disabled = false;
        landingStatus.hidden = true;
      }
    } catch (_) {}
  }, 3000);
}
startReadyPolling();

function showLandingStatus(msg, isError = false) {
  landingStatus.textContent = msg;
  landingStatus.hidden = false;
  landingStatus.classList.toggle("error", isError);
}

function setProgressUI(pct, label) {
  landingProgress.hidden = false;
  landingProgressFill.style.width = pct + "%";
  landingProgressLabel.textContent = label;
}

let progressPoller      = null;
let animationFrame      = null;
let currentPct          = 0;
let targetPct           = 0;
let startTime           = null;
let progressStatusText  = "Fetching articles…";

function animateProgress() {
  const elapsed = (Date.now() - startTime) / 1000;
  const timePct = Math.min(88, (elapsed / TOTAL_ESTIMATED_SECS) * 88);
  currentPct = Math.max(currentPct, timePct, targetPct);
  landingProgressFill.style.width = currentPct.toFixed(1) + "%";
  landingProgressLabel.textContent = `${Math.round(currentPct)}% — ${progressStatusText}`;
  if (currentPct < 99) {
    animationFrame = requestAnimationFrame(animateProgress);
  }
}

function startProgressPolling() {
  currentPct = 0;
  targetPct  = 5;
  startTime  = Date.now();
  setProgressUI(0, "Connecting to APIs…");
  landingProgress.hidden = false;
  animationFrame = requestAnimationFrame(animateProgress);

  progressPoller = setInterval(async () => {
    try {
      const res = await fetch("/api/progress");
      const { done, total } = await res.json();
      const milestones = [0, 30, 65, 90];
      targetPct = Math.max(targetPct, milestones[done] ?? 90);
      progressStatusText = done === 0
        ? "Fetching articles from all sources…"
        : `Fetched ${API_LABELS.slice(0, done).join(", ")} — ${total - done} source${total - done !== 1 ? "s" : ""} left…`;
    } catch (_) {}
  }, 1500);
}

function stopProgressPolling() {
  if (progressPoller)  { clearInterval(progressPoller); progressPoller = null; }
  if (animationFrame)  { cancelAnimationFrame(animationFrame); animationFrame = null; }
}

landingBtn.addEventListener("click", triggerSearch);
landingInput.addEventListener("keydown", (e) => { if (e.key === "Enter") triggerSearch(); });

document.getElementById("new-search-btn").addEventListener("click", () => {
  landingEl.classList.remove("hidden");
  landingStatus.hidden = true;
  landingBtn.disabled = false;
  postEvent("new_search");
});

function setStoryHeadline(query) {
  const text = `"${query}"`;
  document.getElementById("timeline-headline").textContent = text;
  document.querySelectorAll(".story-headline-dynamic").forEach(el => el.textContent = text);
}

async function runSearchQuery(query) {
  const res = await fetch(`/api/search?q=${encodeURIComponent(query)}&limit=10`);
  if (!res.ok) throw new Error((await res.json()).error || "Search failed");
  const { results } = await res.json();
  currentQuery = query;
  await loadAndRender(query, results);
  setStoryHeadline(query);
}

async function triggerSearch() {
  const query = landingInput.value.trim();
  if (!query) return;

  landingBtn.disabled = true;
  showLandingStatus("Fetching articles… this may take up to 1 minute.");
  startProgressPolling();

  try {
    await runSearchQuery(query);
    postEvent("search", { query });
    stopProgressPolling();
    landingProgressFill.style.width = "100%";
    landingProgressLabel.textContent = "100% — Done!";
    await new Promise(r => setTimeout(r, 500));
    landingEl.classList.add("hidden");
  } catch (err) {
    stopProgressPolling();
    landingProgress.hidden = true;
    showLandingStatus("Error: " + err.message, true);
    landingBtn.disabled = false;
  }
}

// ---------- Data loading ----------

async function loadArticles(query) {
  const url = query ? `/api/search?q=${encodeURIComponent(query)}` : "/api/articles";
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  const data = await res.json();
  if (Array.isArray(data)) return { articles: data, updatedAt: null };
  // /api/search returns {query, results}; /api/articles returns {articles, updatedAt}
  if (data.results) return { articles: data.results, updatedAt: null };
  return data;
}

function toTimelineData(articles) {
  // First pass: group by date and track distinct sources per day
  const groups = {};
  for (const a of articles) {
    const isoDate = (a.date || "").slice(0, 10);
    if (!isoDate) continue;
    if (!groups[isoDate]) {
      const d = new Date(a.date);
      groups[isoDate] = {
        date:     isNaN(d) ? isoDate : d.toLocaleDateString("en-US", { month: "long", day: "numeric" }),
        isoDate,
        sources:  new Set(),
        articles: [],
      };
    }
    groups[isoDate].sources.add(a.source);
    const d = new Date(a.date);
    groups[isoDate].articles.push({
      time:    isNaN(d) ? "" : d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }),
      isoTime: a.date,
      src:     a.source,
      title:   a.title,
      summary: a.description || "",
      url:     a.url,
    });
  }

  // Coverage bonus: days covered by more outlets get a 0–1 bonus on top of credibility
  const maxSources = Math.max(...Object.values(groups).map(g => g.sources.size), 1);

  return Object.values(groups)
    .sort((a, b) => a.isoDate.localeCompare(b.isoDate))
    .map((group) => {
      const coverageBonus = (group.sources.size - 1) / (maxSources - 1 || 1);
      return {
        date:     group.date,
        isoDate:  group.isoDate,
        articles: group.articles
          .sort((a, b) => {
            const scoreDiff = (credibilityScore(b.src) + coverageBonus) -
                              (credibilityScore(a.src) + coverageBonus);
            // coverageBonus is equal for all articles on the same day,
            // so this effectively sorts by credibility tier, then by time
            return scoreDiff || new Date(a.isoTime) - new Date(b.isoTime);
          })
          .slice(0, TOP_N_PER_DATE),
      };
    });
}

function toChannelData(articles) {
  const channels = {};
  for (const a of articles) {
    if (!channels[a.source]) channels[a.source] = [];
    const d = new Date(a.date);
    channels[a.source].push({
      time:    isNaN(d) ? "" : d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }),
      date:    isNaN(d) ? (a.date || "").slice(0, 10) : d.toLocaleDateString("en-US", { month: "long", day: "numeric" }),
      isoDate: (a.date || "").slice(0, 10),
      title:   a.title,
      summary: a.description || "",
      url:     a.url,
    });
  }
  return channels;
}

// ---------- Dynamic UI builders ----------

function buildSourceFilters(sources) {
  const container = document.getElementById("source-checkboxes");
  container.innerHTML = "";

  const toggleRow = document.createElement("div");
  toggleRow.className = "source-toggle-row";
  const allBtn = document.createElement("button");
  allBtn.className = "source-toggle-btn";
  allBtn.textContent = "All";
  const noneBtn = document.createElement("button");
  noneBtn.className = "source-toggle-btn";
  noneBtn.textContent = "None";
  allBtn.addEventListener("click", () => {
    container.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = true);
  });
  noneBtn.addEventListener("click", () => {
    container.querySelectorAll('input[type="checkbox"]').forEach(cb => cb.checked = false);
  });
  toggleRow.appendChild(allBtn);
  toggleRow.appendChild(noneBtn);
  container.appendChild(toggleRow);

  sources.forEach((src) => {
    const label = document.createElement("label");
    label.className = "check";
    label.innerHTML = `<input type="checkbox" data-src="${src}" checked /> <span class="dot" style="background:${sourceColor(src)}"></span> ${src}`;
    container.appendChild(label);
  });
}

function buildChannelCards(sources) {
  const container = document.getElementById("channel-cards-container");
  container.innerHTML = "";
  sources.forEach((src) => {
    const card = document.createElement("div");
    card.className = "channel-card";
    card.dataset.src = src;
    card.innerHTML = `
      <span class="channel-card-dot" style="background:${sourceColor(src)}"></span>
      <span class="channel-card-name">${src}</span>
    `;
    card.addEventListener("click", () => showChannelDetail(src));
    container.appendChild(card);
  });
}

// ---------- View switching ----------

const views  = { timeline: "view-timeline", channels: "view-channels", llm: "view-llm", account: "view-account" };
const titles = { timeline: "Coverage Timeline", channels: "Channels", llm: "LLM Analysis", account: "Account" };
let selectedTimelineSource = null;
const timelineColumnsEl = document.getElementById("timeline-columns");
const startDateFilterEl = document.getElementById("start-date-filter");
const endDateFilterEl   = document.getElementById("end-date-filter");
const applyFiltersBtn   = document.getElementById("apply-filters-btn");

let currentView = "timeline";

function closeFilters() {
  document.getElementById("filters-panel").classList.remove("open");
}

document.getElementById("filters-close").addEventListener("click", closeFilters);
document.getElementById("filters-panel").classList.add("open"); // open by default on first load

document.querySelectorAll(".menu-item").forEach((btn) => {
  btn.addEventListener("click", () => {
    const name = btn.dataset.view;
    if (name === "timeline" && currentView === "timeline") {
      document.getElementById("filters-panel").classList.toggle("open");
    } else {
      setView(name);
      if (name === "timeline") {
        document.getElementById("filters-panel").classList.add("open");
      } else {
        closeFilters();
      }
    }
  });
});

function setView(name) {
  currentView = name;
  document.querySelectorAll(".menu-item").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  document.getElementById(views[name]).classList.add("active");
  document.getElementById("page-title").textContent = titles[name];
  if (name !== "timeline") clearTimelineSourceSelection();
  if (name === "channels") showChannelsGrid();
  if (name === "account") renderAccountView();
}

// ---------- Timeline rendering ----------

function renderTimeline() {
  clearTimelineSourceSelection();
  const filtered = getFilteredTimelineData();
  timelineColumnsEl.innerHTML = "";
  if (!filtered.length) {
    timelineColumnsEl.innerHTML = '<div class="timeline-empty-state">No coverage matches the selected filters.</div>';
    return;
  }
  filtered.forEach((col) => {
    const colEl = document.createElement("div");
    colEl.className = "timeline-column";
    colEl.appendChild(makeTimelineStage(col.date));
    col.articles.forEach((a) => colEl.appendChild(makeArticleCard(a)));
    timelineColumnsEl.appendChild(colEl);
  });
}

function getFilteredTimelineData() {
  const selectedSources = new Set(
    Array.from(document.querySelectorAll('#source-checkboxes input[type="checkbox"]:checked')).map((el) => el.dataset.src)
  );
  const startDate = startDateFilterEl.value;
  const endDate   = endDateFilterEl.value;
  const leanValue = parseInt(document.getElementById("lean-slider").value, 10);
  // |leanValue| 1-2 = mild side, 3-5 = strong side, 0 = all
  const leanDir    = leanValue < 0 ? "Left" : leanValue > 0 ? "Right" : null;
  const leanStrong = Math.abs(leanValue) >= 3; // past halfway (2.5) on a -5..5 scale

  return timelineData
    .filter((group) => {
      if (startDate && group.isoDate < startDate) return false;
      if (endDate   && group.isoDate > endDate)   return false;
      return true;
    })
    .map((group) => ({
      ...group,
      articles: group.articles.filter((a) => {
        if (!selectedSources.has(a.src)) return false;
        if (leanDir) {
          const bias = biasMap[a.url];
          if (bias) {
            if (bias.bias_label !== leanDir) return false;
            const magnitude = Math.abs(bias.bias_signed);
            if (leanStrong  && magnitude < 0.5) return false; // want strong, article is mild
            if (!leanStrong && magnitude >= 0.5) return false; // want mild, article is strong
          }
        }
        return true;
      }),
    }))
    .filter((group) => group.articles.length > 0);
}

function makeTimelineStage(date) {
  const stage = document.createElement("div");
  stage.className = "timeline-stage";
  stage.innerHTML = `<div class="stage-date">${date}</div>`;
  return stage;
}

function makeArticleCard(a) {
  const card = document.createElement("div");
  card.className = "article-card";
  card.dataset.src = a.src;
  card._articleData = a;
  card.innerHTML = `
    <div class="meta">
      <span class="time">${a.time}</span>
      <span class="dot" style="background:${sourceColor(a.src)}"></span>
      <span class="src" data-src="${a.src}">${a.src}</span>
    </div>
    <div class="title">${a.title}</div>
  `;
  const slider = makeBiasSlider(a.url);
  if (slider) card.appendChild(slider);
  if (bookmarkedTitles.has(a.title)) {
    const star = document.createElement("button");
    star.className = "bookmark-star";
    star.title = "Remove bookmark";
    star.textContent = "★";
    star.addEventListener("click", async (e) => {
      e.stopPropagation();
      const id = bookmarkIdMap[a.title];
      if (!id) return;
      await sb.from("bookmarks").delete().eq("id", id);
      bookmarkedTitles.delete(a.title);
      delete bookmarkIdMap[a.title];
      star.remove();
      showToast("Bookmark removed");
      if (currentView === "account") renderAccountView();
    });
    card.appendChild(star);
  }

  card.addEventListener("mousemove", (e) => showTooltip(e, a.summary));
  card.addEventListener("mouseleave", hideTooltip);
  card.querySelector(".src").addEventListener("click", (e) => {
    if (document.body.classList.contains("compare-mode")) return;
    e.stopPropagation();
    if (selectedTimelineSource === a.src) {
      clearTimelineSourceSelection();
      setView("channels");
      showChannelDetail(a.src);
      return;
    }
    setTimelineSourceSelection(a.src);
  });
  card.addEventListener("click", () => {
    if (document.body.classList.contains("compare-mode")) {
      const title = a.title;
  
      if (selectedCompareTitles.includes(title)) {

        // REMOVE TITLE
        selectedCompareTitles = selectedCompareTitles.filter(t => t !== title);
      
        // REMOVE ARTICLE OBJECT
        selectedCompareArticles =
          selectedCompareArticles.filter(article => article.title !== title);
      
        card.style.border = "";
        card.style.backgroundColor = "";
      
      } else {
      
        if (selectedCompareTitles.length >= MAX_COMPARE_ARTICLES) {
          alert(`You can only select up to ${MAX_COMPARE_ARTICLES} articles.`);
          return;
        }
      
        // ADD TITLE
        selectedCompareTitles.push(title);
      
        // ADD FULL ARTICLE OBJECT
        selectedCompareArticles.push(a);
      
        card.style.border = "4px solid #2563eb";
        card.style.backgroundColor = "rgba(37, 99, 235, 0.12)";
      }
  
      updateCompareControls();
  
      return;
    }
  
    if (a.url) { recordView(a); window.open(a.url, "_blank"); }
  });

  return card;
}

function setTimelineSourceSelection(src) {
  selectedTimelineSource = src;
  document.querySelectorAll("#timeline-columns .article-card").forEach((card) => {
    const isMatch = card.dataset.src === src;
    card.classList.toggle("is-active-source", isMatch);
    card.classList.toggle("is-dimmed", !isMatch);
  });
  document.querySelectorAll("#timeline-columns .src").forEach((label) => {
    const isMatch = label.dataset.src === src;
    label.classList.toggle("is-active-source", isMatch);
    label.classList.toggle("is-dimmed", !isMatch);
  });
}

function clearTimelineSourceSelection() {
  selectedTimelineSource = null;
  document.querySelectorAll("#timeline-columns .article-card, #timeline-columns .src").forEach((el) => {
    el.classList.remove("is-active-source", "is-dimmed");
  });
}

// ---------- Tooltip ----------

const tooltipEl = document.getElementById("tooltip");
function showTooltip(e, text) {
  if (!text) return;
  tooltipEl.textContent = text;
  tooltipEl.hidden = false;
  tooltipEl.style.left = e.pageX + 12 + "px";
  tooltipEl.style.top  = e.pageY + 12 + "px";
}
function hideTooltip() { tooltipEl.hidden = true; }

// ---------- Compare modal ----------

const modal = document.getElementById("compare-modal");

function updateCompareControls() {
  if (!runCompareBtn) return;

  const isCompareMode = document.body.classList.contains("compare-mode");
  const selectedCount = selectedCompareTitles.length;

  if (selectedCompareTitles.length === 0) {
    runCompareBtn.textContent = `Select ${MIN_COMPARE_ARTICLES}-${MAX_COMPARE_ARTICLES} articles`;
  }

  if (selectedCompareTitles.length === 1) {
    runCompareBtn.textContent = "Select 1-2 more articles";
  }

  if (selectedCompareTitles.length >= MIN_COMPARE_ARTICLES) {
    runCompareBtn.textContent = "Compare Selected Articles";
  }

  if (cancelCompareBtn) {
    cancelCompareBtn.hidden = !isCompareMode;
  }

  if (compareSelectedCountEl) {
    compareSelectedCountEl.hidden = !isCompareMode;
    compareSelectedCountEl.textContent = `${selectedCount} selected`;
  }

  runCompareBtn.disabled = isCompareMode && selectedCount < MIN_COMPARE_ARTICLES;
}

function resetArticleComparison() {
  selectedCompareTitles = [];
  selectedCompareArticles = [];

  document.getElementById("selected-article-links").innerHTML = "";

  document.querySelectorAll(".article-card").forEach(card => {
    card.style.border = "";
    card.style.backgroundColor = "";
  });

  runCompareBtn.textContent = "Article Comparison";
  runCompareBtn.disabled = false;
  if (cancelCompareBtn) cancelCompareBtn.hidden = true;
  if (compareSelectedCountEl) compareSelectedCountEl.hidden = true;
  document.body.classList.remove("compare-mode");
}

document.getElementById("modal-close").addEventListener("click", () => {
  modal.classList.remove("open");
  resetArticleComparison();
});

modal.addEventListener("click", (e) => {
  if (e.target === modal) {
    modal.classList.remove("open");
    resetArticleComparison();
  }
});
// ---------- Channels view ----------

function showChannelsGrid() {
  document.getElementById("channels-grid").classList.add("active");
  document.getElementById("channels-detail").classList.remove("active");
}

const CHANNEL_ANALYSIS = {
  "New York Times": `The New York Times covered the Trump–Pope Leo dispute primarily as a domestic political story rather than a religious one, with most reporting filed by White House and politics correspondents. The arc unfolds across two days:

<strong>April 13 — Trigger and response.</strong> Coverage opens with Katie Rogers framing Trump's Truth Social attack as showing "no boundaries" on whom the president will target, setting an editorially critical tone from the start. The story expands across multiple fronts the same day: the Pope's restrained pushback from his plane to Algeria, reported sympathetically by Motoko Rich, and Trump's AI-generated Jesus image, which drew bipartisan Catholic backlash that NYT amplified through extensive quotes from bishops, the U.S. Conference of Catholic Bishops, and even Trump-aligned figures like Bishop Robert Barron.
<strong>April 14 — Political fallout.</strong> The frame shifts decisively to electoral math: Lerer and Epstein cast the feud as a GOP "headache" threatening Catholic swing voters in Michigan, Ohio, Wisconsin, and South Texas, while VP Vance's Fox News defense telling the Vatican to "stick to matters of morality" is covered as administration damage control.

Across all five articles, NYT consistently centers political consequences and Catholic institutional reaction, with less prominent attention to the theological substance of Leo's anti-war message itself.
`,
};

function showChannelDetail(src) {
  document.getElementById("channels-grid").classList.remove("active");
  document.getElementById("channels-detail").classList.add("active");
  document.getElementById("channel-name").textContent = src;

  const analysisBox = document.getElementById("channel-analysis-box");
  if (CHANNEL_ANALYSIS[src]) {
    analysisBox.innerHTML = CHANNEL_ANALYSIS[src];
    analysisBox.style.display = "block";
  } else {
    analysisBox.style.display = "none";
  }

  const wrap = document.getElementById("channel-timeline");
  wrap.innerHTML = "";

  // Group this source's articles by date
  const byDate = {};
  (channelData[src] || []).forEach((a) => {
    if (!byDate[a.isoDate]) byDate[a.isoDate] = { date: a.date, articles: [] };
    byDate[a.isoDate].articles.push(a);
  });

  Object.entries(byDate)
    .sort(([a], [b]) => a.localeCompare(b))
    .forEach(([, bucket], index) => {
      const col = document.createElement("div");
      col.className = "timeline-column";
      col.appendChild(makeTimelineStage(bucket.date, index));
      bucket.articles.forEach((a) => {
        const card = document.createElement("div");
        card.className = "article-card";
        card._articleData = { ...a, src };
        card.innerHTML = `
          <div class="meta"><span class="time">${a.time}</span> <strong>${src}</strong></div>
          <div class="title">${a.title}</div>
          <div class="summary">${a.summary}</div>
        `;
        card.addEventListener("click", () => { if (a.url) { recordView({ ...a, src }); window.open(a.url, "_blank"); } });
        col.appendChild(card);
      });
      wrap.appendChild(col);
    });
}

document.getElementById("channels-back").addEventListener("click", showChannelsGrid);
applyFiltersBtn.addEventListener("click", renderTimeline);

document.getElementById("view-timeline").addEventListener("click", (e) => {
  if (!selectedTimelineSource) return;
  if (e.target.closest(".article-card, .timeline-stage, .filters, .compare-btn")) return;
  clearTimelineSourceSelection();
});

// ---------- LLM view ----------

const llmData = [
  {
    name: "ChatGPT",
    color: "#10a37f",
    url: "https://chatgpt.com/s/t_69efdcf511d08191b5fa81803342b111",
    summary: "A dramatized, narrative-heavy account that frames the feud as a major ideological clash between nationalism and global humanitarianism. It consistently favors Leo's position through asymmetric language and relies on a narrow set of center-left sources. The least factually precise of the three, with editorial bias baked into its structure and framing.",
    biases: [
      {
        title: "Political / Framing Bias (Pro-Pope)",
        body: `The response consistently frames Trump's positions with charged language (“hardline,” “personal attacks,” “unusually blunt”) while describing the pope's stances in neutral or positive terms (“moral restraint,” “peace,” “humanitarian focus”). This is asymmetric framing. Notably, the response omits that religion experts described the pope's words as “quite banal” and “the status quo of Catholic social teachings” — framing Leo as more of a reformer than he may actually be. It also omits Trump's specific, substantive criticisms (e.g., concerns about Iran's nuclear ambitions), which are present in the original source material.`,
      },
      {
        title: "Source Bias",
        body: "The response cites CBS News, Reuters, and Boston.com — all centrist-to-left-leaning outlets — with no counterbalancing sources from right-leaning media. This creates a one-sided evidentiary base. For example, polling data showing Trump's approval among Catholic voters actually rebounded during the feud is entirely absent, which would have complicated the narrative that Trump's attacks are broadly damaging.",
      },
      {
        title: "False Equivalence / Asymmetry Bias",
        body: `The response labels this a mutual “conflict” and “feud,” but one religion expert described it as a “one-way feud,” with Trump berating a critic. Calling it a two-sided clash inflates the pope's aggressiveness in the exchange.`,
      },
      {
        title: "Omission Bias (Temporal)",
        body: `The response presents the feud's origins somewhat loosely. The actual catalytic event was Operation Epic Fury, a joint U.S.-Israeli military operation beginning February 28, 2026 — a specific detail the chatbot omits, replacing it with vaguer language about a “2026 conflict involving Iran.” This obscures the timeline and reduces factual precision.`,
      },
      {
        title: "Editorial / Structural Bias",
        body: `The use of emoji headers (🔥⚔️🧠🌍🧩) and dramatic section labels like “What sparked the dispute” and “Main points of conflict” imposes a narrative arc that subtly dramatizes the story and primes the reader to see it as a significant moral clash rather than a political disagreement.`,
      },
    ],
    sources: [
      { label: "cbsnews.com — Trump-Pope Leo feud politics", url: "https://www.cbsnews.com/news/trump-pope-leo-feud-politics/" },
      { label: "reuters.com — Pope Leo decries migrants", url: "https://www.reuters.com/world/pope-leo-decries-migrants-being-treated-worse-than-house-pets-2026-04-23/" },
      { label: "boston.com — Trump lambasts Pope Leo XIV", url: "https://www.boston.com/news/politics/2026/04/12/trump-lambasts-pope-leo-xiv-extending-feud-over-iran-war-with-first-american-pontiff/" },
      { label: "cbsnews.com — How dispute escalated", url: "https://www.cbsnews.com/news/how-dispute-trump-pope-leo-escalated/" },
    ],
  },
  {
    name: "Perplexity",
    color: "#6e57e0",
    url: "https://www.perplexity.ai/search/98d83dc7-a3f4-449f-a15b-e7a4b5acd894",
    summary: "A clean, plain-prose account that presents both sides' positions without heavy editorializing or dramatic framing. Its weaknesses are mostly sins of omission — particularly missing polling data — and vague sourcing with no inline citations. Reads like a competent news brief but lacks the depth to fully contextualize the story.",
    biases: [
      {
        title: "Framing Bias (Mild, Against Trump)",
        body: `Trump “attacked” the pope, while Leo “took the stance” — subtly casting Trump as aggressor and Leo as principled respondent. Similarly, describing Leo as “defiant” carries a mildly heroic connotation that isn't balanced by an equivalently characterful word for Trump's persistence. The language is mostly even, but these small asymmetries add up.`,
      },
      {
        title: "Omission Bias (Pope Leo's sharpening rhetoric)",
        body: `The response describes Leo as speaking “from a moral and gospel-based perspective, not as a partisan politician” — but omits that the pope's own language sharpened over time, escalating from prayers for peace to calling the war “unjust” and labeling Trump's threat to destroy Iranian civilization “truly unacceptable.” Leaving this out makes Leo appear more passive and measured than the record shows.`,
      },
      {
        title: "Source Bias (Implicit)",
        body: `The response cites no sources at all, making it impossible to evaluate where the claims originate. The characterization that Leo has been “defiant and unwilling to back down” is attributed only vaguely to “reports” — a weak attribution that obscures potential editorial slant in the underlying sources.`,
      },
      {
        title: "Omission Bias (Catholic polling data)",
        body: `The “Why it matters” section says the feud has created “political fallout on the right,” implying Trump has been politically damaged. But polling data shows Trump's approval among Catholic voters actually rebounded in April despite the feud intensifying — a significant fact that contradicts the implied narrative of political cost.`,
      },
      {
        title: "Temporal / Factual Vagueness",
        body: "Like ChatGPT, this response never names the specific triggering event. Operation Epic Fury — the joint U.S.-Israeli military strike on Iran beginning February 28, 2026 — was the direct catalyst, and omitting it leaves the timeline fuzzy and harder to fact-check.",
      },
    ],
    sources: [
      { label: "youtube.com — PBS News Hour", url: "https://www.youtube.com/watch?v=Vt2l9sujNTk" },
      { label: "nytimes.com — Republicans, Trump, Pope midterms", url: "https://www.nytimes.com/2026/04/17/us/politics/republicans-trump-pope-midterms.html" },
      { label: "bbc.com — Trump-Pope Leo coverage", url: "https://www.bbc.com/news/articles/c070jxyjrmeo" },
      { label: "pbs.org — Trump clashes with Pope Leo", url: "https://www.pbs.org/newshour/show/trump-clashes-with-pope-leo-who-vows-to-continue-speaking-out-against-war" },
      { label: "npr.org — American Catholics in awkward spot", url: "https://www.npr.org/2026/04/18/nx-s1-5788718/tensions-between-president-trump-and-pope-leo-put-american-catholics-in-awkward-spot" },
      { label: "cbsnews.com — Trump-Pope Leo feud politics", url: "https://www.cbsnews.com/news/trump-pope-leo-feud-politics/" },
    ],
  },
  {
    name: "Gemini",
    color: "#4285f4",
    url: "https://gemini.google.com/app/8adea3eab974b7d2",
    summary: "A well-structured account that correctly names the triggering event and provides a useful comparison table of both positions. It contains one potentially hallucinated specific claim about an AI-generated image, and mildly favors Leo through subtle language choices. High-variance: well-organized and detailed but carries reliability risks from unverified specifics.",
    biases: [
      {
        title: "Sensationalism / Hyperbole Bias",
        body: `Calling this “one of the most high-profile diplomatic rifts in modern history” is unsupported editorializing. It overstates the significance of what religion experts have described as fairly routine papal behavior — “quite banal” and “the status quo of Catholic social teachings.”`,
      },
      {
        title: "Fabrication Risk / Unverified Claim",
        body: `The response mentions Trump sharing an AI-generated image depicting himself as Jesus-like, which “many Catholic leaders and the Vatican viewed as sacrilegious.” This specific claim does not appear in any of the verified sources reviewed. It may be accurate, but its inclusion without a citation in a context with other verifiable facts is a red flag for hallucination or embellishment.`,
      },
      {
        title: "Framing Bias (Subtle, Pro-Leo)",
        body: `The summary table is structurally fair, but the language choices favor Leo. His position on military action is described as “advocacy for non-violent resolution and 'just war' doctrine” — a sophisticated, theologically grounded framing — while Trump's is simply “necessary for global stability and ending nuclear threats,” which sounds blunter by comparison.`,
      },
      {
        title: "Omission Bias (Catholic public opinion)",
        body: "Like the previous two responses, this one omits polling showing Trump's approval among Catholic voters rebounded in April 2026 despite the feud intensifying — arguably the most important data point for understanding how the dispute has actually landed with the relevant public.",
      },
      {
        title: "Quote Accuracy Issue",
        body: `The response quotes Trump as saying to “stay in his lane” — but verified sources show Trump's actual language was to “get his act together as Pope, use Common Sense, stop catering to the Radical Left, and focus on being a Great Pope, not a Politician.” Paraphrasing quotes without flagging them as paraphrases misrepresents tone and substance.`,
      },
    ],
    sources: [
      { label: "whyy.org — Trump-Pope dispute, Catholics in Bucks County", url: "https://whyy.org/articles/trump-pope-dispute-catholics-bucks-county/" },
      { label: "georgetown.edu — First American Pope", url: "https://www.georgetown.edu/news/what-it-means-for-the-first-american-to-be-chosen-as-pope/" },
      { label: "war.gov — Operation Epic Fury", url: "https://www.war.gov/Spotlights/Operation-Epic-Fury/" },
      { label: "americamagazine.org — Pope Leo on Iran war", url: "https://www.americamagazine.org/news/2026/04/10/pope-leo-war-iran-criticism/" },
      { label: "usccb.org — Pope Leo calls for ceasefire", url: "https://www.usccb.org/news/2026/pope-leo-calls-ceasefire-middle-east-special-prayers-lebanon" },
      { label: "livenowfox.com — Trump blasts Pope Leo XIV", url: "https://www.livenowfox.com/news/trump-blasts-pope-leo-xiv-truth-social-weak-crime-foreign-policy" },
      { label: "cbsnews.com — How dispute escalated", url: "https://www.cbsnews.com/news/how-dispute-trump-pope-leo-escalated/" },
      { label: "pbs.org — Trump says he doesn't owe Pope an apology", url: "https://www.pbs.org/newshour/politics/watch-trump-says-he-doesnt-owe-pope-leo-an-apology-after-attacking-him-for-comments-on-iran" },
      { label: "wikipedia.org — 2026 US–Holy See rift", url: "https://en.wikipedia.org/wiki/2026_United_States%E2%80%93Holy_See_rift" },
      { label: "ncregister.com — Trump-Pope Leo takeaways", url: "https://www.ncregister.com/commentaries/editorial-trump-pope-leo-takeaways" },
      { label: "ncronline.org — Trump says he has right to disagree", url: "https://www.ncronline.org/news/trump-says-he-has-right-disagree-pope-leo-meeting-him-not-necessary" },
    ],
  },
];

function renderLLM() {
  const wrap = document.getElementById("llm-cards");
  wrap.innerHTML = "";
  llmData.forEach((m) => {
    const card = document.createElement("div");
    card.className = "llm-card collapsed";
    card.style.borderTopColor = m.color;

    const biasItems = m.biases.map((b, i) => `
      <li class="llm-bias-item">
        <span class="llm-bias-title">${i + 1}. ${b.title}</span>
        <span class="llm-bias-body">${b.body}</span>
      </li>
    `).join("");

    const sourceItems = m.sources.map((s) => `
      <li><a href="${s.url}" target="_blank" rel="noopener">${s.label}</a></li>
    `).join("");

    card.innerHTML = `
      <div class="llm-card-header">
        <a class="llm-name" href="${m.url}" target="_blank" rel="noopener">${m.name}</a>
        <span class="chevron">›</span>
      </div>
      <p class="llm-summary">${m.summary}</p>
      <div class="llm-card-detail">
        <div class="llm-section-label">Bias Analysis</div>
        <ol class="llm-bias-list">${biasItems}</ol>
        <div class="llm-section-label">Sources</div>
        <ul class="llm-sources-list">${sourceItems}</ul>
      </div>
    `;

    card.querySelector(".chevron").addEventListener("click", () => {
      card.classList.toggle("collapsed");
      card.querySelector(".chevron").textContent = card.classList.contains("collapsed") ? "›" : "⌄";
    });
    wrap.appendChild(card);
  });
}

// Show comparison results after selecting articles
const runCompareBtn = document.getElementById("compare-btn");
const cancelCompareBtn = document.getElementById("compare-cancel-btn");
const compareSelectedCountEl = document.getElementById("compare-selected-count");
const comparisonResults = document.getElementById("comparison-results");

if (cancelCompareBtn) {
  cancelCompareBtn.addEventListener("click", resetArticleComparison);
}

document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && document.body.classList.contains("compare-mode")) {
    resetArticleComparison();
  }
});

if (runCompareBtn && comparisonResults) {
  runCompareBtn.addEventListener("click", () => {
    console.log("compare button clicked");
    console.log("selected count:", selectedCompareTitles.length);

    if (!document.body.classList.contains("compare-mode")) {
      document.body.classList.add("compare-mode");
      selectedCompareTitles = [];
      selectedCompareArticles = [];
      updateCompareControls();
      return;
    }

    if (selectedCompareTitles.length < MIN_COMPARE_ARTICLES) {
      alert(`Select at least ${MIN_COMPARE_ARTICLES} articles to compare.`);
      return;
    }
    const selectedLinksEl = document.getElementById("selected-article-links");

    selectedLinksEl.innerHTML = selectedCompareArticles
      .map((article, index) => `
        <div style="margin-bottom: 10px;">
          <strong>Article ${index + 1}:</strong>
          <strong>${article.title}</strong>
          <a href="${article.url}" target="_blank">[Link]</a>
        </div>
      `)
      .join("");
  
      modal.classList.add("open");
      comparisonResults.hidden = false;
      comparisonResults.innerHTML = "<h4>Article Comparison</h4><p>Generating comparison...</p>";
      
      //fetch("http://127.0.0.1:8000/api/compare", {
      fetch("/api/compare", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          articles: selectedCompareArticles,
        }),
      })
        .then(async res => {
          const text = await res.text();
          console.log("Raw compare response:", text);

          if (!res.ok) {
            throw new Error(text || "Compare request failed");
          }

          return JSON.parse(text);
        })
        .then(data => {
          console.log("Parsed compare data:", data);
          renderComparison(data.comparison);
          postEvent("comparison", { titles: selectedCompareArticles.map(a => a.title) });
        })
        .catch(err => {
          console.error("Compare error:", err);
          comparisonResults.innerHTML = "<p>Could not generate comparison.</p>";
        });


  });
}

// Hardcode to close the comparison results when "Close" is clicked.
const modalCloseBtn = document.getElementById("modal-close");

if (modalCloseBtn && comparisonResults) {
  modalCloseBtn.addEventListener("click", () => {
    comparisonResults.hidden = true;
  });
}

function renderComparison(comparison) {
  const articleKeys = ["article1", "article2", "article3"].filter(key => comparison[key]);

  const articleCards = articleKeys
    .map(key => `
      <div class="article-card">
        <h5>${comparison[key].title}</h5>
        <p><strong>Source:</strong> ${comparison[key].source}</p>
        <p><strong>Core Argument:</strong> ${comparison[key].core_argument}</p>

        <ul>
          ${(comparison[key].key_points || [])
            .map(point => `<li>${point}</li>`)
            .join("")}
        </ul>
      </div>
    `)
    .join("");

  const differenceRows = (comparison.key_differences || [])
    .map(diff => `
      <p>
        <strong>${diff.label}</strong><br/>
        ${articleKeys
          .map((key, index) => `Article ${index + 1} → ${diff[key] || ""}`)
          .join("<br/>")}
      </p>
    `)
    .join("");

  comparisonResults.innerHTML = `
    <h4>Article Comparison</h4>

    <div class="compare-articles">
      ${articleCards}
    </div>

    <div class="differences">
      <h4>Key Differences</h4>
      ${differenceRows}
    </div>
  `;
}



// ---------- Auth / Profile ----------

function updateProfileBtn() {
  const btn = document.getElementById("profile-btn");
  if (!btn) return;
  if (currentUser) {
    btn.textContent = currentUser.email[0].toUpperCase();
    btn.classList.add("signed-in");
  } else {
    btn.innerHTML = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`;
    btn.classList.remove("signed-in");
  }
}

document.getElementById("profile-btn").addEventListener("click", () => setView("account"));

// ---------- Context menu ----------

let ctxArticle = null;
const ctxMenu = document.getElementById("ctx-menu");

document.addEventListener("contextmenu", (e) => {
  const card = e.target.closest(".article-card");
  if (!card || !card._articleData) { ctxMenu.classList.remove("open"); return; }
  e.preventDefault();
  ctxArticle = card._articleData;
  ctxMenu.style.left = Math.min(e.pageX, window.innerWidth  - 190) + "px";
  ctxMenu.style.top  = Math.min(e.pageY, window.innerHeight - 60)  + "px";
  ctxMenu.classList.add("open");
});

document.addEventListener("click",   () => ctxMenu.classList.remove("open"));
document.addEventListener("keydown",  (e) => { if (e.key === "Escape") ctxMenu.classList.remove("open"); });

document.getElementById("ctx-bookmark").addEventListener("click", async () => {
  ctxMenu.classList.remove("open");
  if (!currentUser) { setView("account"); showToast("Sign in to bookmark articles"); return; }
  if (!ctxArticle)  return;
  const { data, error } = await sb.from("bookmarks").insert({
    user_id:         currentUser.id,
    article_title:   ctxArticle.title,
    article_url:     ctxArticle.url    || null,
    article_src:     ctxArticle.src    || "",
    article_summary: ctxArticle.summary || "",
  }).select("id").single();
  if (!error && data) {
    bookmarkedTitles.add(ctxArticle.title);
    bookmarkIdMap[ctxArticle.title] = data.id;
    renderTimeline();
    showToast("Bookmarked!");
  } else {
    showToast("Already bookmarked");
  }
});

function showToast(msg) {
  const t = document.getElementById("toast");
  t.textContent = msg;
  t.classList.add("show");
  setTimeout(() => t.classList.remove("show"), 2500);
}

// ---------- Account view ----------

async function renderAccountView() {
  const container = document.getElementById("account-content");
  if (!container) return;

  if (!currentUser) {
    container.innerHTML = `
      <div class="auth-box">
        <h2 class="auth-title">Sign in</h2>
        <div class="auth-error" id="auth-error" hidden></div>
        <div class="form-group">
          <label class="form-label">Email</label>
          <input class="form-input" type="email" id="auth-email" placeholder="you@example.com" />
        </div>
        <div class="form-group">
          <label class="form-label">Password</label>
          <input class="form-input" type="password" id="auth-password" placeholder="••••••••" />
        </div>
        <div class="auth-actions">
          <button class="auth-btn primary" id="signin-btn">Sign In</button>
          <button class="auth-btn secondary" id="signup-btn">Create Account</button>
        </div>
      </div>`;

    async function handleAuth(mode) {
      const email    = document.getElementById("auth-email").value.trim();
      const password = document.getElementById("auth-password").value;
      const errEl    = document.getElementById("auth-error");
      errEl.hidden   = true;
      const { error } = mode === "signin"
        ? await sb.auth.signInWithPassword({ email, password })
        : await sb.auth.signUp({ email, password });
      if (error) { errEl.textContent = error.message; errEl.hidden = false; }
    }

    document.getElementById("signin-btn").addEventListener("click", () => handleAuth("signin"));
    document.getElementById("signup-btn").addEventListener("click", () => handleAuth("signup"));
    return;
  }

  const [{ data: bookmarks }, { data: history }] = await Promise.all([
    sb.from("bookmarks").select("*").order("bookmarked_at", { ascending: false }),
    sb.from("article_views").select("*").order("viewed_at", { ascending: false }).limit(5),
  ]);

  const cards = (bookmarks || []).map(b => `
    <div class="bookmark-card">
      <div class="bookmark-meta">
        <span class="dot" style="background:${sourceColor(b.article_src)}"></span>
        <span class="bookmark-src">${b.article_src}</span>
        <span class="bookmark-date">${new Date(b.bookmarked_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}</span>
      </div>
      <div class="bookmark-title">${b.article_url
        ? `<a href="${b.article_url}" target="_blank" rel="noopener">${b.article_title}</a>`
        : b.article_title}</div>
      ${b.article_summary ? `<div class="bookmark-summary">${b.article_summary}</div>` : ""}
      <button class="bookmark-remove" data-id="${b.id}">Remove</button>
    </div>`).join("");

  const historyCards = (history || []).map(h => `
    <div class="bookmark-card">
      <div class="bookmark-meta">
        <span class="dot" style="background:${sourceColor(h.article_src)}"></span>
        <span class="bookmark-src">${h.article_src}</span>
        <span class="bookmark-date">${new Date(h.viewed_at).toLocaleDateString("en-US", { month: "short", day: "numeric" })}</span>
      </div>
      <div class="bookmark-title">
        <a href="${h.article_url}" target="_blank" rel="noopener">${h.article_title}</a>
      </div>
    </div>`).join("");

  container.innerHTML = `
    <div class="account-header">
      <div>
        <div class="account-email">${currentUser.email}</div>
        <div class="account-label">Signed in</div>
      </div>
      <button class="signout-btn" id="signout-btn">Sign Out</button>
    </div>
    <h3 class="bookmarks-heading">Recently Viewed</h3>
    ${history?.length
      ? `<div class="bookmarks-list">${historyCards}</div>`
      : `<div class="bookmarks-empty">No history yet — click any article to open it.</div>`}
    <h3 class="bookmarks-heading" style="margin-top:28px">Bookmarks${bookmarks?.length ? ` (${bookmarks.length})` : ""}</h3>
    ${bookmarks?.length
      ? `<div class="bookmarks-list">${cards}</div>`
      : `<div class="bookmarks-empty">No bookmarks yet — right-click any article to bookmark it.</div>`}`;

  document.getElementById("signout-btn").addEventListener("click", () => sb.auth.signOut());
  container.querySelectorAll(".bookmark-remove").forEach(btn => {
    btn.addEventListener("click", async () => {
      await sb.from("bookmarks").delete().eq("id", btn.dataset.id);
      renderAccountView();
    });
  });
}

// ---------- History ----------

async function recordView(a) {
  if (!currentUser || !a.url) return;
  postEvent("article_view", { title: a.title, url: a.url, src: a.src || "" });
  await sb.from("article_views").insert({
    user_id:       currentUser.id,
    article_title: a.title,
    article_url:   a.url,
    article_src:   a.src || "",
  });
}

// ---------- Refresh ----------

const refreshBtn = document.getElementById("refresh-btn");
const refreshIcon = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 4 23 10 17 10"/><path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10"/></svg>`;
if (refreshBtn) {
  refreshBtn.addEventListener("click", async () => {
    if (!currentQuery) return;
    refreshBtn.disabled = true;
    refreshBtn.innerHTML = `${refreshIcon} Fetching…`;
    try {
      await runSearchQuery(currentQuery);
      refreshBtn.innerHTML = `${refreshIcon} Refresh`;
    } catch (err) {
      console.error("Refresh error:", err);
      refreshBtn.innerHTML = "Failed — try again";
    }
    refreshBtn.disabled = false;
  });
}

// ---------- Init ----------

function setLastUpdated(isoString) {
  const el = document.getElementById("last-updated");
  if (!el || !isoString) return;
  const d = new Date(isoString);
  el.textContent = "Updated " + d.toLocaleString("en-US", {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short"
  });
}

// ---------- Bias data ----------

let biasMap = {}; // url → {bias_label, bias_score, bias_signed}

async function loadBias() {
  try {
    const res = await fetch("/api/bias");
    if (res.ok) biasMap = await res.json();
  } catch (_) {}
}

loadBias(); // fire-and-forget; ready before any search completes

function makeBiasSlider(url) {
  const b = biasMap[url];
  const el = document.createElement("div");
  el.className = "bias-slider";
  if (!b) {
    el.title = "Bias data unavailable";
    el.innerHTML = `
      <div class="bias-track bias-track--unknown"></div>
      <div class="bias-labels"><span>L</span><span>R</span></div>
    `;
    return el;
  }
  const pct = ((b.bias_signed + 1) / 2 * 100).toFixed(1); // -1→0%, 0→50%, 1→100%
  const opacity = Math.max(0.25, Math.min(1, b.bias_score)).toFixed(2);
  el.title = `Bias: ${b.bias_label} (score ${b.bias_signed.toFixed(2)})`;
  el.innerHTML = `
    <div class="bias-track" style="opacity:${opacity}">
      <div class="bias-marker" style="left:${pct}%"></div>
    </div>
    <div class="bias-labels"><span>L</span><span>R</span></div>
  `;
  return el;
}

async function loadAndRender(query, prefetchedArticles) {
  try {
    const { articles, updatedAt } = prefetchedArticles
      ? { articles: prefetchedArticles, updatedAt: null }
      : await loadArticles(query);
    const normalized = articles.map(a => ({ ...a, source: cleanSourceName(a.source) }));

    timelineData = toTimelineData(normalized);
    channelData = toChannelData(normalized);

    const sources = Object.keys(channelData).sort();
    assignSourceColors(sources);
    buildSourceFilters(sources);
    buildChannelCards(sources);
    setLastUpdated(updatedAt);

    renderTimeline();
  } catch (err) {
    console.error("Could not load articles:", err);
    timelineColumnsEl.innerHTML =
      '<div class="timeline-empty-state">No articles loaded.</div>';
  }
}

async function init() {
  async function handleGateAuth(mode) {
    const email = document.getElementById("gate-email").value.trim();
    const password = document.getElementById("gate-password").value;
    const errEl = document.getElementById("gate-error");
    errEl.hidden = true;

    const { error } =
      mode === "signin"
        ? await sb.auth.signInWithPassword({ email, password })
        : await sb.auth.signUp({ email, password });

    if (error) {
      errEl.textContent = error.message;
      errEl.hidden = false;
    }
  }

  document.getElementById("gate-signin-btn").addEventListener("click", () => handleGateAuth("signin"));
  document.getElementById("gate-signup-btn").addEventListener("click", () => handleGateAuth("signup"));

  renderLLM();
}

init();

setInterval(() => fetch("/api/ready").catch(() => {}), 30000);

document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") {
    if (visibleSince !== null) {
      totalVisibleMs += Date.now() - visibleSince;
      visibleSince = null;
    }
  } else {
    visibleSince = Date.now();
  }
});

window.addEventListener("beforeunload", () => {
  if (!currentUser) return;
  if (visibleSince !== null) totalVisibleMs += Date.now() - visibleSince;
  const duration_s = Math.round(totalVisibleMs / 1000);
  navigator.sendBeacon(
    "/api/events",
    new Blob(
      [JSON.stringify({ user_id: currentUser.id, session_id: sessionId, event: "session_end", payload: { duration_s } })],
      { type: "application/json" }
    )
  );
});

// Landing page shows first — loadAndRender() is called after a successful search
