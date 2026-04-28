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
  const res = await fetch("../data/articles.json");
  if (!res.ok) throw new Error(`HTTP ${res.status}`);
  return res.json();
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
    const normalized = raw.map(a => ({ ...a, source: cleanSourceName(a.source) }));
    timelineData = toTimelineData(normalized);
    channelData  = toChannelData(normalized);
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
