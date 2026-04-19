// ---------- Placeholder data ----------
const timelineData = [
  {
    date: "March 23rd",
    articles: [
      { time: "9:00AM", src: "CNN", title: "Title...", summary: "Initial CNN report on the dispute." },
      { time: "10:00AM", src: "NYT", title: "Title...", summary: "NYT breaks the story with additional sourcing." },
    ],
  },
  {
    date: "April 1st",
    articles: [
      { time: "8:52AM", src: "FOX", title: "Title...", summary: "FOX commentary frames the dispute differently." },
      { time: "1:00PM", src: "CNN", title: "Title...", summary: "Follow-up with new quotes from the Vatican." },
      { time: "2:00PM", src: "NYT", title: "Title...", summary: "Analysis piece covering historical precedent." },
    ],
  },
  {
    date: "April 10th",
    articles: [
      { time: "9:00AM", src: "CNN", title: "Title...", summary: "Narrative shifts after new evidence emerges." },
    ],
  },
];

const channelData = {
  NYT: [
    { time: "9:00AM", date: "March 23rd", title: "Title...", summary: "Summary: early NYT coverage." },
    { time: "10:00AM", date: "April 1st", title: "Title...", summary: "Summary: NYT follow-up analysis." },
    { time: "8:01AM", date: "April 10th", title: "Title...", summary: "Summary: NYT retrospective." },
    { time: "11:00AM", date: "April 10th", title: "Title...", summary: "Summary: additional NYT coverage." },
  ],
  CNN: [
    { time: "9:00AM", date: "March 23rd", title: "Title...", summary: "Summary: CNN initial report." },
  ],
  FOX: [
    { time: "8:52AM", date: "April 1st", title: "Title...", summary: "Summary: FOX commentary." },
  ],
};

const llmData = [
  { name: "ChatGPT", summary: "", sources: "", leaning: "" },
  { name: "Gemini",  summary: "", sources: "", leaning: "" },
];

// ---------- View switching ----------
const views = { timeline: "view-timeline", channels: "view-channels", llm: "view-llm" };
const titles = { timeline: "News Reported on", channels: "Channels", llm: "LLM Analysis" };

document.querySelectorAll(".menu-item").forEach((btn) => {
  btn.addEventListener("click", () => setView(btn.dataset.view));
});

function setView(name) {
  document.querySelectorAll(".menu-item").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  document.querySelectorAll(".view").forEach((v) => v.classList.remove("active"));
  document.getElementById(views[name]).classList.add("active");
  document.getElementById("page-title").textContent = titles[name];
  if (name === "channels") showChannelsGrid();
}

// ---------- Timeline rendering ----------
function renderTimeline() {
  const container = document.getElementById("timeline-columns");
  container.innerHTML = "";
  timelineData.forEach((col) => {
    const colEl = document.createElement("div");
    colEl.className = "timeline-column";
    col.articles.forEach((a) => colEl.appendChild(makeArticleCard(a)));
    container.appendChild(colEl);
  });
}

function makeArticleCard(a) {
  const card = document.createElement("div");
  card.className = "article-card";
  card.innerHTML = `
    <div class="meta">
      <span class="time">${a.time}</span>
      <span class="dot ${a.src.toLowerCase()}"></span>
      <span class="src ${a.src === "NYT" ? "nyt-hl" : ""}" data-src="${a.src}">${a.src}</span>
    </div>
    <div class="title">${a.title}</div>
  `;
  // Hover tooltip with summary
  card.addEventListener("mousemove", (e) => showTooltip(e, a.summary));
  card.addEventListener("mouseleave", hideTooltip);
  // Click source dot/name -> jump to channel deep-dive
  card.querySelector(".src").addEventListener("click", (e) => {
    e.stopPropagation();
    setView("channels");
    showChannelDetail(a.src);
  });
  // Click title -> pretend to open article
  card.addEventListener("click", () => {
    window.alert(`Opening ${a.src} article (placeholder).`);
  });
  return card;
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
  const buckets = { "March 23rd": [], "April 1st": [], "April 10th": [] };
  (channelData[src] || []).forEach((a) => {
    if (buckets[a.date]) buckets[a.date].push(a);
  });
  Object.keys(buckets).forEach((date) => {
    const col = document.createElement("div");
    col.className = "timeline-column";
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
document.querySelectorAll(".channel-card").forEach((c) =>
  c.addEventListener("click", () => showChannelDetail(c.dataset.src))
);

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

// ---------- Init ----------
renderTimeline();
renderLLM();