const TOP_N_PER_DATE = 5;

// Higher number = more credible. Sources not listed default to tier 1.
const SOURCE_CREDIBILITY = {
  "NYTAPI":            3,
  "theguardian.com":   3,
  "theatlantic.com":   3,
  "reuters.com":       3,
  "apnews.com":        3,
  "CNBC":              2,
  "independent.co.uk": 2,
  "independent.ie":    2,
  "bbc.co.uk":         2,
  "bbc.com":           2,
  "standard.co.uk":    2,
  "detroitnews.com":   2,
};

function credibilityScore(src) {
  return SOURCE_CREDIBILITY[src] || 1;
}

const SOURCE_COLORS = [
  "#38b86b", "#4f9eea", "#8b5cf6", "#f97316",
  "#e84545", "#06b6d4", "#f59e0b", "#ec4899",
  "#10b981", "#6366f1", "#84cc16", "#14b8a6",
  "#f43f5e", "#a855f7", "#0ea5e9", "#fb923c",
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

// ---------- Data loading ----------

async function loadArticles() {
  const res = await fetch("/data/articles.json");
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
}

function toTimelineData(articles) {
  // First pass: group by date and track distinct sources per day
  const groups = {};
  for (const a of articles) {
    const isoDate = a.date.slice(0, 10);
    if (!groups[isoDate]) {
      const d = new Date(a.date);
      groups[isoDate] = {
        date:     d.toLocaleDateString("en-US", { month: "long", day: "numeric" }),
        isoDate,
        sources:  new Set(),
        articles: [],
      };
    }
    groups[isoDate].sources.add(a.source);
    const d = new Date(a.date);
    groups[isoDate].articles.push({
      time:    d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }),
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
      time:    d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" }),
      date:    d.toLocaleDateString("en-US", { month: "long", day: "numeric" }),
      isoDate: a.date.slice(0, 10),
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
    card.textContent = src;
    card.addEventListener("click", () => showChannelDetail(src));
    container.appendChild(card);
  });
}

// ---------- View switching ----------

const views  = { timeline: "view-timeline", channels: "view-channels", llm: "view-llm" };
const titles = { timeline: "Coverage Timeline", channels: "Channels", llm: "LLM Analysis" };
let selectedTimelineSource = null;
const timelineColumnsEl = document.getElementById("timeline-columns");
const startDateFilterEl = document.getElementById("start-date-filter");
const endDateFilterEl   = document.getElementById("end-date-filter");
const applyFiltersBtn   = document.getElementById("apply-filters-btn");

document.querySelectorAll(".menu-item").forEach((btn) => {
  btn.addEventListener("click", () => setView(btn.dataset.view));
});

function setView(name) {
  document.querySelectorAll(".menu-item").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  document.getElementById(views[name]).classList.add("active");
  document.getElementById("page-title").textContent = titles[name];
  if (name !== "timeline") clearTimelineSourceSelection();
  if (name === "channels") showChannelsGrid();
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
  filtered.forEach((col, index) => {
    const colEl = document.createElement("div");
    colEl.className = "timeline-column";
    colEl.appendChild(makeTimelineStage(col.date, index));
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

  return timelineData
    .filter((group) => {
      if (startDate && group.isoDate < startDate) return false;
      if (endDate   && group.isoDate > endDate)   return false;
      return true;
    })
    .map((group) => ({
      ...group,
      articles: group.articles.filter((a) => selectedSources.has(a.src)),
    }))
    .filter((group) => group.articles.length > 0);
}

function makeTimelineStage(date, index) {
  const stage = document.createElement("div");
  stage.className = "timeline-stage";
  stage.innerHTML = `
    <div class="stage-step">Stage ${String(index + 1).padStart(2, "0")}</div>
    <div class="stage-date">${date}</div>
  `;
  return stage;
}

function makeArticleCard(a) {
  const card = document.createElement("div");
  card.className = "article-card";
  card.dataset.src = a.src;
  card.innerHTML = `
    <div class="meta">
      <span class="time">${a.time}</span>
      <span class="dot" style="background:${sourceColor(a.src)}"></span>
      <span class="src" data-src="${a.src}">${a.src}</span>
    </div>
    <div class="title">${a.title}</div>
  `;
  card.addEventListener("mousemove", (e) => showTooltip(e, a.summary));
  card.addEventListener("mouseleave", hideTooltip);
  card.querySelector(".src").addEventListener("click", (e) => {
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
    if (a.url) window.open(a.url, "_blank");
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
document.getElementById("compare-btn").addEventListener("click", () => modal.classList.add("open"));
document.getElementById("modal-close").addEventListener("click", () => modal.classList.remove("open"));
modal.addEventListener("click", (e) => { if (e.target === modal) modal.classList.remove("open"); });

// ---------- Channels view ----------

function showChannelsGrid() {
  document.getElementById("channels-grid").classList.add("active");
  document.getElementById("channels-detail").classList.remove("active");
}

function showChannelDetail(src) {
  document.getElementById("channels-grid").classList.remove("active");
  document.getElementById("channels-detail").classList.add("active");
  document.getElementById("channel-name").textContent = src;

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
        card.innerHTML = `
          <div class="meta"><span class="time">${a.time}</span> <strong>${src}</strong></div>
          <div class="title">${a.title}</div>
          <div class="summary">${a.summary}</div>
        `;
        card.addEventListener("click", () => { if (a.url) window.open(a.url, "_blank"); });
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
  { name: "ChatGPT", summary: "", sources: "", leaning: "" },
  { name: "Gemini",  summary: "", sources: "", leaning: "" },
];

function renderLLM() {
  const wrap = document.getElementById("llm-cards");
  wrap.innerHTML = "";
  llmData.forEach((m) => {
    const card = document.createElement("div");
    card.className = "llm-card";
    card.innerHTML = `
      <h4>${m.name}</h4>
      <div class="field"><strong>Summary:</strong> ${m.summary || "____"}</div>
      <div class="field"><strong>Sources used:</strong> ${m.sources || "____"}</div>
      <div class="field"><strong>Political leaning:</strong> ${m.leaning || "____"}</div>
      <span class="chevron">⌄</span>
    `;
    card.querySelector(".chevron").addEventListener("click", () => {
      card.classList.toggle("collapsed");
      card.querySelector(".chevron").textContent = card.classList.contains("collapsed") ? "›" : "⌄";
    });
    wrap.appendChild(card);
  });
}

// Hardcode to show comparison results when "Run Comparison" is clicked, since we don't have real LLM outputs in this prototype.
const runCompareBtn = document.getElementById("run-compare-btn");
const comparisonResults = document.getElementById("comparison-results");
if (runCompareBtn && comparisonResults) {
  runCompareBtn.addEventListener("click", () => {
    comparisonResults.hidden = false;
  });
}

// Hardcode to close the comparison results when "Close" is clicked.
const modalCloseBtn = document.getElementById("modal-close");
if (modalCloseBtn && comparisonResults) {
  modalCloseBtn.addEventListener("click", () => {
    comparisonResults.hidden = true;
  });
}

// ---------- Init ----------

async function init() {
  try {
    const raw = await loadArticles();
    timelineData = toTimelineData(raw);
    channelData  = toChannelData(raw);
    const sources = Object.keys(channelData).sort();
    assignSourceColors(sources);
    buildSourceFilters(sources);
    buildChannelCards(sources);
  } catch (err) {
    console.error("Could not load articles:", err);
    timelineColumnsEl.innerHTML =
      '<div class="timeline-empty-state">No articles loaded. Run <code>python refresh.py</code> then serve from repo root with <code>python -m http.server 8080</code>.</div>';
  }
  renderTimeline();
  renderLLM();
}

init();
