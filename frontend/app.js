// ---------- Data (loaded from frontend_data.json) ----------
let timelineData = [];
let channelData  = {};

const llmData = [
  { name: "ChatGPT", summary: "", sources: "", leaning: "" },
  { name: "Gemini",  summary: "", sources: "", leaning: "" },
];

// ---------- View switching ----------
const views = { timeline: "view-timeline", channels: "view-channels", llm: "view-llm" };
const titles = { timeline: "Coverage Timeline", channels: "Channels", llm: "LLM Analysis" };
let selectedTimelineSource = null;
const timelineColumnsEl = document.getElementById("timeline-columns");
const startDateFilterEl = document.getElementById("start-date-filter");
const endDateFilterEl = document.getElementById("end-date-filter");
const applyFiltersBtn = document.getElementById("apply-filters-btn");

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
  const filteredTimeline = getFilteredTimelineData();
  timelineColumnsEl.innerHTML = "";
  if (!filteredTimeline.length) {
    timelineColumnsEl.innerHTML = '<div class="timeline-empty-state">No coverage matches the selected filters.</div>';
    return;
  }
  filteredTimeline.forEach((col, index) => {
    const colEl = document.createElement("div");
    colEl.className = "timeline-column";
    colEl.appendChild(makeTimelineStage(col.date, index));
    col.articles.forEach((a) => colEl.appendChild(makeArticleCard(a)));
    timelineColumnsEl.appendChild(colEl);
  });
}

function getFilteredTimelineData() {
  const selectedSources = new Set(
    Array.from(document.querySelectorAll('.filters input[type="checkbox"][data-src]:checked')).map((input) => input.dataset.src)
  );
  const startDate = startDateFilterEl.value;
  const endDate = endDateFilterEl.value;

  return timelineData
    .filter((group) => {
      if (startDate && group.isoDate < startDate) return false;
      if (endDate && group.isoDate > endDate) return false;
      return true;
    })
    .map((group) => ({
      ...group,
      articles: group.articles.filter((article) => selectedSources.has(article.src)),
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
      <span class="dot ${a.src.toLowerCase()}"></span>
      <span class="src" data-src="${a.src}">${a.src}</span>
    </div>
    <div class="title">${a.title}</div>
  `;
  // Hover tooltip with summary
  card.addEventListener("mousemove", (e) => showTooltip(e, a.summary));
  card.addEventListener("mouseleave", hideTooltip);
  // First click filters timeline, second click opens the channel view.
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
  // Click title -> pretend to open article
  card.addEventListener("click", () => {
    window.alert(`Opening ${a.src} article (placeholder).`);
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
  tooltipEl.style.top = e.pageY + 12 + "px";
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

  // Group articles by date dynamically
  const buckets = {};
  (channelData[src] || []).forEach((a) => {
    if (!buckets[a.date]) buckets[a.date] = [];
    buckets[a.date].push(a);
  });

  Object.keys(buckets).forEach((date, index) => {
    const col = document.createElement("div");
    col.className = "timeline-column";
    col.appendChild(makeTimelineStage(date, index));
    buckets[date].forEach((a) => {
      const card = document.createElement("div");
      card.className = "article-card";
      card.innerHTML = `
        <div class="meta"><span class="time">${a.time}</span> <strong>${src}</strong></div>
        <div class="title">${a.title}</div>
        <div class="summary">${a.summary}</div>
      `;
      col.appendChild(card);
    });
    wrap.appendChild(col);
  });
}

document.getElementById("channels-back").addEventListener("click", showChannelsGrid);

function renderChannelCards() {
  const grid = document.querySelector(".channel-cards");
  grid.innerHTML = "";
  Object.keys(channelData).forEach((src) => {
    const card = document.createElement("div");
    card.className = "channel-card";
    card.dataset.src = src;
    card.textContent = src;
    card.addEventListener("click", () => showChannelDetail(src));
    grid.appendChild(card);
  });
}
applyFiltersBtn.addEventListener("click", renderTimeline);

document.getElementById("view-timeline").addEventListener("click", (e) => {
  if (!selectedTimelineSource) return;
  if (e.target.closest(".article-card, .timeline-stage, .filters, .compare-btn")) return;
  clearTimelineSourceSelection();
});

// ---------- LLM view ----------
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
fetch("frontend_data.json")
  .then((r) => r.json())
  .then((data) => {
    timelineData = data.timelineData || [];
    channelData  = data.channelData  || {};
    renderTimeline();
    renderLLM();
    renderChannelCards();
  })
  .catch((err) => {
    console.error("Failed to load frontend_data.json:", err);
    renderTimeline();
    renderLLM();
  });