// ---------- Supabase ----------
const SUPABASE_URL  = "https://nlcnbcpnljdizedritaj.supabase.co";
const SUPABASE_ANON = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im5sY25iY3BubGpkaXplZHJpdGFqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3Nzg0NTkyMDcsImV4cCI6MjA5NDAzNTIwN30.AU1xSkrfd3efDrsvCHAQXD_jsmWGu62eL9kVIuBxLak";
const sb = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON, {
  auth: {
    storage: window.sessionStorage,
  },
});
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
// Source lean ratings based on AllSides / Ad Fontes Media.
// Keys cover both cleaned domain names (after cleanSourceName) and formatted API names.
const SOURCE_LEAN = {
  // Left
  "cnn": "Left", "CNN": "Left",
  "msnbc": "Left", "MSNBC": "Left",
  "huffpost": "Left", "HuffPost": "Left", "huffingtonpost": "Left",
  "motherjones": "Left", "Mother Jones": "Left",
  "vox": "Left", "Vox": "Left",
  "slate": "Left", "Slate": "Left",
  "thenation": "Left", "The Nation": "Left",
  "rawstory": "Left", "Raw Story": "Left",
  "crooksandliars": "Left", "Crooksandliars": "Left",
  "truthout": "Left", "Truthout": "Left",
  "juancole": "Left", "Juancole": "Left",
  "aljazeera": "Left", "Al Jazeera": "Left",
  "nytimes": "Left", "New York Times": "Left",
  "washingtonpost": "Left", "Washington Post": "Left",
  "theguardian": "Left", "Guardian": "Left",
  "nbcnews": "Left", "NBC News": "Left",
  "cbsnews": "Left", "CBS News": "Left",
  "abcnews": "Left", "ABC News": "Left", "abc": "Left",
  "npr": "Left", "NPR": "Left",
  "pbs": "Left", "PBS": "Left",
  "theatlantic": "Left", "The Atlantic": "Left", "atlantic": "Left",
  "politico": "Left", "Politico": "Left",
  "time": "Left", "Time": "Left",
  "thedailybeast": "Left", "Daily Beast": "Left",
  "salon": "Left", "Salon": "Left",
  "msn": "Left", "MSN": "Left",
  "consequence": "Left", "Consequence": "Left",
  "globalresearch": "Left", "Globalresearch": "Left",
  // Center
  "apnews": "Center", "AP News": "Center", "Associated Press": "Center",
  "reuters": "Center", "Reuters": "Center",
  "bbc": "Center", "BBC": "Center", "BBC News": "Center",
  "usatoday": "Center", "USA Today": "Center",
  "thehill": "Center", "The Hill": "Center",
  "bloomberg": "Center", "Bloomberg": "Center",
  "axios": "Center", "Axios": "Center",
  "theconversation": "Center", "The Conversation": "Center",
  "mediaite": "Center", "Mediaite": "Center",
  "perthnow": "Center",
  "independent": "Center", "Independent": "Center",
  "standard": "Center",
  // Right
  "foxnews": "Right", "Fox News": "Right",
  "nypost": "Right", "New York Post": "Right",
  "wsj": "Right", "Wall Street Journal": "Right",
  "breitbart": "Right", "Breitbart": "Right",
  "dailywire": "Right", "Daily Wire": "Right",
  "newsmax": "Right", "Newsmax": "Right",
  "washingtonexaminer": "Right", "Washington Examiner": "Right",
  "washingtontimes": "Right", "Washington Times": "Right",
  "epochtimes": "Right", "Epoch Times": "Right",
  "thefederalist": "Right", "The Federalist": "Right",
  "dailymail": "Right", "Daily Mail": "Right",
  "dailycaller": "Right", "Daily Caller": "Right",
  "oann": "Right", "OAN": "Right",
  "nypost": "Right", "New York Post": "Right",
};

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
let clusterData  = [];
let selectedCompareTitles = [];
let selectedCompareArticles = [];
const MIN_COMPARE_ARTICLES = 2;
const MAX_COMPARE_ARTICLES = 3;
let currentQuery = null;

// ---------- Landing page ----------

const landingEl            = document.getElementById("landing");
const landingInput         = document.getElementById("landing-input");
const landingBtn           = document.getElementById("landing-btn");
const landingBypassBtn     = document.getElementById("landing-bypass-btn");
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

async function loadSuggestions() {
  try {
    const res = await fetch("/api/suggestions");
    const { suggestions } = await res.json();
    const wrap = document.getElementById("landing-suggestions");
    const divider = document.getElementById("search-suggestions-divider");
    const chips = document.getElementById("suggestions-chips");
    chips.innerHTML = suggestions.map(q => `
      <button class="suggestion-row" data-query="${q}">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        ${q}
      </button>`).join("");
    chips.addEventListener("click", e => {
      const row = e.target.closest(".suggestion-row");
      if (!row || landingBtn.disabled) return;
      landingInput.value = row.dataset.query;
      triggerSearch();
    });
    divider.hidden = false;
    wrap.hidden = false;
  } catch (_) {}
}
loadSuggestions();

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

function updateLandingBypassLabel() {
  landingBypassBtn.textContent = timelineData.length
    ? "Return Without Searching"
    : "Continue Without Search";
}

landingBtn.addEventListener("click", triggerSearch);
landingBypassBtn.addEventListener("click", () => {
  landingStatus.hidden = true;
  landingProgress.hidden = true;
  if (!timelineData.length) {
    currentQuery = null;
    sessionStorage.removeItem("lastSearch");
    setStoryHeadline("No Search Selected");
  }
  landingEl.classList.add("hidden");
});
landingInput.addEventListener("keydown", (e) => { if (e.key === "Enter") triggerSearch(); });

document.getElementById("new-search-btn").addEventListener("click", () => {
  sessionStorage.removeItem("lastSearch");
  updateLandingBypassLabel();
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

async function parseApiResponse(res, fallbackMessage) {
  const contentType = res.headers.get("content-type") || "";
  let data;

  try {
    data = contentType.includes("application/json")
      ? await res.json()
      : await res.text();
  } catch (_) {
    throw new Error(fallbackMessage);
  }

  if (!res.ok) {
    const detail = typeof data === "object" && data
      ? data.detail || data.error
      : "";
    throw new Error(detail || fallbackMessage);
  }

  if (typeof data !== "object" || data === null) {
    throw new Error(fallbackMessage);
  }

  return data;
}

async function runSearchQuery(query) {
  const res = await fetch(`/api/search?q=${encodeURIComponent(query)}&limit=10`);
  const { results } = await parseApiResponse(
    res,
    "Search is temporarily unavailable. Please try again."
  );
  if (!Array.isArray(results)) throw new Error("Search returned an invalid response. Please try again.");
  currentQuery = query;
  try { sessionStorage.setItem("lastSearch", JSON.stringify({ query, results })); } catch (_) {}
  await Promise.all([loadAndRender(query, results), loadBias()]);
  setStoryHeadline(query);
}

async function triggerSearch() {
  const query = landingInput.value.trim();
  if (!query) return;

  landingBtn.disabled = true;
  showLandingStatus("Fetching articles… this may take up to 1 minute.");
  startProgressPolling();
  loadLLMData(query); // fire in parallel, no await

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
  const data = await parseApiResponse(res, "Could not load articles. Please try again.");
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

const CLUSTER_STOP_WORDS = new Set([
  "about", "after", "again", "against", "also", "amid", "among", "and", "are",
  "article", "been", "before", "being", "between", "but", "can", "could",
  "for", "from", "has", "have", "him", "his", "her", "how", "into", "its",
  "may", "more", "new", "news", "not", "now", "off", "one", "over", "says",
  "said", "say", "that", "the", "their", "this", "through", "too", "under",
  "was", "were", "what", "when", "where", "which", "who", "why", "will",
  "with", "you", "your",
]);

const CLUSTER_LABEL_STOP_WORDS = new Set(["trump", "pope", "leo", "xiv", "president"]);

function clusterTokens(article, extraStopWords = new Set()) {
  return `${article.title || ""} ${article.description || ""}`
    .toLowerCase()
    .match(/[a-z0-9]+/g)
    ?.filter(token => (
      token.length > 2 &&
      !CLUSTER_STOP_WORDS.has(token) &&
      !extraStopWords.has(token)
    )) || [];
}

function weightedClusterTokens(article) {
  return [
    ...clusterTokens(article),
    ...clusterTokens({ title: article.title || "" }),
  ];
}

function tokenSimilarity(aTokens, bTokens, docFreq, totalArticles) {
  const a = {};
  const b = {};
  aTokens.forEach(token => { a[token] = (a[token] || 0) + 1; });
  bTokens.forEach(token => { b[token] = (b[token] || 0) + 1; });
  const aKeys = Object.keys(a);
  const bKeys = Object.keys(b);
  if (!aKeys.length || !bKeys.length) return 0;
  const weight = token => Math.log((totalArticles + 1) / ((docFreq[token] || 0) + 1)) + 1;
  let dotProduct = 0;
  let aMagnitude = 0;
  let bMagnitude = 0;
  aKeys.forEach(token => {
    const value = a[token] * weight(token);
    aMagnitude += value * value;
    if (b[token]) dotProduct += value * b[token] * weight(token);
  });
  bKeys.forEach(token => {
    const value = b[token] * weight(token);
    bMagnitude += value * value;
  });
  return dotProduct / Math.sqrt(aMagnitude * bMagnitude);
}

function buildClusterDocumentFrequency(articles) {
  const docFreq = {};
  articles.forEach(article => {
    [...new Set(clusterTokens(article))].forEach(token => {
      docFreq[token] = (docFreq[token] || 0) + 1;
    });
  });
  return docFreq;
}

function formatClusterTerm(token) {
  return token.toUpperCase() === token || token.length <= 3
    ? token.toUpperCase()
    : token[0].toUpperCase() + token.slice(1);
}

function formatClusterPhrase(phrase) {
  return phrase.split(" ").map(formatClusterTerm).join(" ");
}

function clusterPhrases(article) {
  const tokens = clusterTokens(article, CLUSTER_LABEL_STOP_WORDS);
  const phrases = [];
  for (let size = 3; size >= 2; size -= 1) {
    for (let i = 0; i <= tokens.length - size; i += 1) {
      phrases.push(tokens.slice(i, i + size).join(" "));
    }
  }
  return phrases;
}

function formatClusterLabel(phrases, terms) {
  if (phrases.length) return formatClusterPhrase(phrases[0]);
  if (!terms.length) return "Related Coverage";
  if (terms.length === 1) return `${formatClusterTerm(terms[0])} Coverage`;
  return `${formatClusterTerm(terms[0])} and ${formatClusterTerm(terms[1])}`;
}

function labelCluster(articles, docFreq, totalArticles) {
  const counts = {};
  const phraseCounts = {};
  articles.forEach(article => {
    [...new Set(clusterTokens(article, CLUSTER_LABEL_STOP_WORDS))].forEach(token => {
      counts[token] = (counts[token] || 0) + 1;
    });
    [...new Set(clusterPhrases(article))].forEach(phrase => {
      phraseCounts[phrase] = (phraseCounts[phrase] || 0) + 1;
    });
  });

  const maxGlobalShare = articles.length > 2 ? 0.45 : 0.65;
  const phrases = Object.entries(phraseCounts)
    .filter(([, count]) => count > 1)
    .sort((a, b) => b[1] - a[1] || b[0].length - a[0].length)
    .slice(0, 1)
    .map(([phrase]) => phrase);

  const terms = Object.entries(counts)
    .filter(([token, count]) => count > 1 || articles.length === 1)
    .filter(([token]) => ((docFreq[token] || 0) / totalArticles) <= maxGlobalShare)
    .map(([token, count]) => {
      const inverseFrequency = Math.log((totalArticles + 1) / ((docFreq[token] || 0) + 1)) + 1;
      return [token, count * inverseFrequency];
    })
    .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
    .slice(0, 3)
    .map(([token]) => token);

  return formatClusterLabel(phrases, terms);
}

function toClusterData(articles) {
  const clusters = [];
  const sorted = [...articles].sort((a, b) => new Date(a.date || 0) - new Date(b.date || 0));
  const docFreq = buildClusterDocumentFrequency(sorted);

  sorted.forEach(article => {
    const tokens = weightedClusterTokens(article);
    let bestCluster = null;
    let bestScore = 0;

    clusters.forEach(cluster => {
      const score = tokenSimilarity(tokens, cluster.tokens, docFreq, sorted.length);
      if (score > bestScore) {
        bestScore = score;
        bestCluster = cluster;
      }
    });

    if (bestCluster && bestScore >= 0.12) {
      bestCluster.articles.push(article);
      bestCluster.tokens = bestCluster.articles.flatMap(weightedClusterTokens);
    } else {
      clusters.push({ articles: [article], tokens });
    }
  });

  const grouped = clusters.map((cluster, index) => ({
      id: index + 1,
      label: labelCluster(cluster.articles, docFreq, sorted.length),
      articles: cluster.articles,
      sourceCount: new Set(cluster.articles.map(a => a.source)).size,
    }))
    .sort((a, b) => b.articles.length - a.articles.length || b.sourceCount - a.sourceCount);

  const storyClusters = grouped.filter(cluster => cluster.articles.length > 1);
  const singletons = grouped.filter(cluster => cluster.articles.length === 1);
  if (singletons.length) {
    storyClusters.push({
      id: "other",
      label: "Other Coverage",
      articles: singletons.flatMap(cluster => cluster.articles),
      sourceCount: new Set(singletons.flatMap(cluster => cluster.articles.map(a => a.source))).size,
    });
  }

  return storyClusters;
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

const views  = { timeline: "view-timeline", channels: "view-channels", clusters: "view-clusters", llm: "view-llm", account: "view-account" };
const titles = { timeline: "Coverage Timeline", channels: "Channels", clusters: "Story Clusters", llm: "LLM Analysis", account: "Account" };
let selectedTimelineSource = null;
const timelineColumnsEl = document.getElementById("timeline-columns");
const startDateFilterEl = document.getElementById("start-date-filter");
const endDateFilterEl   = document.getElementById("end-date-filter");
const applyFiltersBtn   = document.getElementById("apply-filters-btn");
const leanSliderEl = document.getElementById("lean-slider");

leanSliderEl.addEventListener("input", () => renderTimeline());

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
  if (name === "clusters") renderStoryClusters();
  if (name === "account") renderAccountView();
  if (name === "llm") {
    if (currentQuery && !llmSummaryData && !llmSummaryLoading) {
      loadLLMData(currentQuery);
    } else {
      renderLLM();
    }
  }
}

// ---------- Timeline rendering ----------

function renderBiasBar(filtered) {
  const barEl = document.getElementById("timeline-bias-bar");
  if (!barEl) return;
  const articles = filtered.flatMap((col) => col.articles);
  if (!articles.length) { barEl.innerHTML = ""; return; }
  let rep = 0, dem = 0, neu = 0;
  articles.forEach((a) => {
    const label = biasMap[a.url]?.bias_label
      || SOURCE_LEAN[a.src]
      || SOURCE_LEAN[cleanSourceName(a.src)]
      || "Center";
    if (label === "Right")       rep++;
    else if (label === "Left")   dem++;
    else                         neu++;
  });
  const total = rep + dem + neu;
  const rPct = Math.round(rep / total * 100);
  const dPct = Math.round(dem / total * 100);
  const nPct = 100 - rPct - dPct;
  barEl.innerHTML = `
    <div class="bias-bar-track">
      <div class="bias-segment bias-segment--dem" style="flex:${dPct}"></div>
      <div class="bias-segment bias-segment--neu" style="flex:${nPct}"></div>
      <div class="bias-segment bias-segment--rep" style="flex:${rPct}"></div>
    </div>
    <div class="bias-bar-labels">
      ${dPct > 0 ? `<div class="bias-label" style="flex:${dPct}"><span class="bias-tick"></span>Left · ${dPct}%</div>` : ""}
      ${nPct > 0 ? `<div class="bias-label" style="flex:${nPct}"><span class="bias-tick"></span>Neutral · ${nPct}%</div>` : ""}
      ${rPct > 0 ? `<div class="bias-label" style="flex:${rPct}"><span class="bias-tick"></span>Right · ${rPct}%</div>` : ""}
    </div>
  `;
}

function renderTimeline() {
  clearTimelineSourceSelection();
  renderAISources();
  const filtered = getFilteredTimelineData();
  renderBiasBar(filtered);
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
  const leanValue = parseInt(leanSliderEl.value, 10);
  const leanDir   = leanValue === 0 ? null : leanValue === 1 ? "Left" : leanValue === 2 ? "Center" : "Right";

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
          const label = bias?.bias_label
            || SOURCE_LEAN[a.src]
            || SOURCE_LEAN[cleanSourceName(a.src)]
            || "Center";
          if (label !== leanDir) return false;
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

const channelSummaryCache = new Map();

function renderChannelSummaryPanel(analysisBox, src) {
  analysisBox.innerHTML = "";

  const eyebrow = document.createElement("div");
  eyebrow.className = "channel-analysis-eyebrow";
  eyebrow.textContent = "AI Channel Summary";

  const heading = document.createElement("h4");
  heading.className = "channel-analysis-heading";
  heading.textContent = `${src} coverage overview`;

  const body = document.createElement("p");
  body.className = "channel-analysis-body";

  analysisBox.append(eyebrow, heading, body);
  return body;
}

async function loadChannelSummary(src, articles, analysisBox, summaryBody) {
  if (!articles.length) {
    summaryBody.textContent = `No articles are currently loaded for ${src}.`;
    return;
  }

  if (channelSummaryCache.has(src)) {
    summaryBody.textContent = channelSummaryCache.get(src);
    return;
  }

  analysisBox.classList.add("loading");
  summaryBody.textContent = "Generating summary...";

  try {
    const response = await fetch("/api/channel-summary", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        source: src,
        articles: articles.map(article => ({
          title: article.title,
          summary: article.summary,
          date: article.isoDate,
        })),
      }),
    });
    if (!response.ok) throw new Error("Could not generate the channel summary.");

    const data = await response.json();
    channelSummaryCache.set(src, data.summary);
    if (document.getElementById("channel-name").textContent === src) {
      summaryBody.textContent = data.summary;
    }
  } catch (error) {
    console.error("Could not load channel summary:", error);
    if (document.getElementById("channel-name").textContent === src) {
      summaryBody.textContent = "Could not generate this channel summary. Please try again.";
    }
  } finally {
    analysisBox.classList.remove("loading");
  }
}

function showChannelDetail(src) {
  document.getElementById("channels-grid").classList.remove("active");
  document.getElementById("channels-detail").classList.add("active");
  document.getElementById("channel-name").textContent = src;

  const analysisBox = document.getElementById("channel-analysis-box");
  analysisBox.style.display = "block";
  const summaryBody = renderChannelSummaryPanel(analysisBox, src);
  loadChannelSummary(src, channelData[src] || [], analysisBox, summaryBody);

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

// ---------- Story clusters ----------

function formatArticleDate(isoString) {
  const d = new Date(isoString);
  if (isNaN(d)) return "";
  return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

function renderStoryClusters() {
  const container = document.getElementById("cluster-list");
  if (!container) return;
  container.innerHTML = "";

  if (!clusterData.length) {
    container.innerHTML = '<div class="timeline-empty-state">No story clusters loaded yet.</div>';
    return;
  }

  clusterData.forEach((cluster, index) => {
    const clusterEl = document.createElement("section");
    clusterEl.className = "story-cluster";
    if (index > 0) clusterEl.classList.add("collapsed");

    const sourceText = `${cluster.sourceCount} source${cluster.sourceCount === 1 ? "" : "s"}`;
    const articleText = `${cluster.articles.length} article${cluster.articles.length === 1 ? "" : "s"}`;
    clusterEl.innerHTML = `
      <button class="cluster-header">
        <span class="cluster-chevron">${index === 0 ? "⌄" : "›"}</span>
        <span class="cluster-title">${cluster.label}</span>
        <span class="cluster-meta">${articleText} · ${sourceText}</span>
      </button>
      <div class="cluster-articles"></div>
    `;

    const articleWrap = clusterEl.querySelector(".cluster-articles");
    cluster.articles.forEach(article => {
      const card = document.createElement("article");
      card.className = "cluster-article-card";
      card.innerHTML = `
        <div class="cluster-article-meta">
          <span class="dot" style="background:${sourceColor(article.source)}"></span>
          <span>${article.source}</span>
          <span>${formatArticleDate(article.date)}</span>
        </div>
        <h4>${article.title}</h4>
        <p>${article.description || "No summary available."}</p>
      `;
      card.addEventListener("click", () => {
        if (article.url) { recordView({ ...article, src: article.source, summary: article.description || "" }); window.open(article.url, "_blank"); }
      });
      articleWrap.appendChild(card);
    });

    clusterEl.querySelector(".cluster-header").addEventListener("click", () => {
      clusterEl.classList.toggle("collapsed");
      clusterEl.querySelector(".cluster-chevron").textContent =
        clusterEl.classList.contains("collapsed") ? "›" : "⌄";
    });

    container.appendChild(clusterEl);
  });
}

// ---------- LLM view ----------

let llmSummaryData = null;
let llmSummaryLoading = false;

const LLM_URLS = {
  ChatGPT: "https://chatgpt.com",
  Gemini: "https://gemini.google.com",
  Claude: "https://claude.ai",
};

async function loadLLMData(query) {
  if (!query) return;
  llmSummaryLoading = true;
  llmSummaryData = null;
  renderLLM();
  renderAISources();
  try {
    const res = await fetch(`/api/llm-summary?q=${encodeURIComponent(query)}`);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "LLM analysis failed.");
    llmSummaryData = data;
  } catch (err) {
    llmSummaryData = { error: err.message };
  } finally {
    llmSummaryLoading = false;
  }
  renderLLM();
  renderAISources();
}

function renderAISources() {
  const container = document.getElementById("timeline-ai-sources");
  if (!container) return;
  container.innerHTML = "";
  if (!llmSummaryData || !llmSummaryData.llms || !llmSummaryData.llms.length) return;

  const label = document.createElement("div");
  label.className = "ai-sources-label";
  label.textContent = "AI Sources";
  container.appendChild(label);

  const cards = document.createElement("div");
  cards.className = "ai-sources-cards";
  llmSummaryData.llms.forEach((m) => {
    const card = document.createElement("div");
    card.className = "ai-source-card";
    card.style.borderLeftColor = m.color;
    card.innerHTML = `
      <span class="ai-source-name">${m.name}</span>
      <span class="ai-source-summary">${m.summary}</span>
    `;
    card.addEventListener("click", () => setView("llm"));
    cards.appendChild(card);
  });
  container.appendChild(cards);
}


function renderLLM() {
  const wrap = document.getElementById("llm-cards");
  const headline = document.getElementById("llm-headline");
  if (headline) headline.textContent = currentQuery ? `"${currentQuery}"` : "";

  wrap.innerHTML = "";

  if (llmSummaryLoading) {
    wrap.innerHTML = '<p class="llm-status">Analyzing…</p>';
    return;
  }
  if (!currentQuery) {
    wrap.innerHTML = '<p class="llm-status">Search for a story to see LLM analysis.</p>';
    return;
  }
  if (!llmSummaryData) {
    wrap.innerHTML = '<p class="llm-status">No analysis available.</p>';
    return;
  }
  if (llmSummaryData.error) {
    wrap.innerHTML = `<p class="llm-status llm-status-error">${llmSummaryData.error}</p>`;
    return;
  }

  llmSummaryData.llms.forEach((m) => {
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

    const nameUrl = LLM_URLS[m.name];
    const nameEl = nameUrl
      ? `<a class="llm-name" href="${nameUrl}" target="_blank" rel="noopener">${m.name}</a>`
      : `<span class="llm-name">${m.name}</span>`;

    card.innerHTML = `
      <div class="llm-card-header">
        ${nameEl}
        <span class="chevron">›</span>
      </div>
      <p class="llm-summary">${m.summary}</p>
      <div class="llm-card-detail">
        <div class="llm-section-label">Bias Analysis</div>
        <ol class="llm-bias-list">${biasItems}</ol>
        <div class="llm-section-label">Sources</div>
        <ul class="llm-sources-list">${sourceItems}</ul>
        <button class="llm-raw-toggle" aria-expanded="false">Full Response <span class="llm-raw-chevron">›</span></button>
        <div class="llm-raw-body" hidden></div>
      </div>
    `;

    card.querySelector(".chevron").addEventListener("click", () => {
      card.classList.toggle("collapsed");
      card.querySelector(".chevron").textContent = card.classList.contains("collapsed") ? "›" : "⌄";
    });

    const rawToggle = card.querySelector(".llm-raw-toggle");
    const rawBody = card.querySelector(".llm-raw-body");
    if (m.raw_response) {
      rawBody.innerHTML = marked.parse(m.raw_response);
      rawToggle.addEventListener("click", () => {
        const open = rawBody.hidden;
        rawBody.hidden = !open;
        rawToggle.setAttribute("aria-expanded", open);
        rawToggle.querySelector(".llm-raw-chevron").textContent = open ? "⌄" : "›";
      });
    } else {
      rawToggle.hidden = true;
    }

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
    sb.from("article_views").select("*").order("viewed_at", { ascending: false }).limit(50),
  ]);

  // --- Reading profile ---
  function articleLean(url, src) {
    return biasMap[url]?.bias_label || SOURCE_LEAN[src] || SOURCE_LEAN[cleanSourceName(src)] || null;
  }

  // Top sources: all-time history
  const sourceCounts = {};
  for (const h of (history || [])) {
    const src = h.article_src || "Unknown";
    sourceCounts[src] = (sourceCounts[src] || 0) + 1;
  }
  const topSources = Object.entries(sourceCounts).sort((a, b) => b[1] - a[1]).slice(0, 3);
  const maxCount = topSources[0]?.[1] || 1;

  // Blind spot: per-topic (only views matching current search articles)
  const allCurrentArticles = Object.entries(channelData).flatMap(([src, arts]) => arts.map(a => ({ ...a, src })));
  const currentArticleUrls = new Set(allCurrentArticles.map(a => a.url));
  const viewedUrls = new Set((history || []).map(h => h.article_url));
  const topicViews = (history || []).filter(h => currentArticleUrls.has(h.article_url));

  const leanCounts = { Left: 0, Center: 0, Right: 0 };
  for (const h of topicViews) {
    const lean = articleLean(h.article_url, h.article_src);
    if (lean && leanCounts[lean] !== undefined) leanCounts[lean]++;
  }
  const totalLean = leanCounts.Left + leanCounts.Center + leanCounts.Right;
  const dominantLean = topicViews.length >= 3
    ? Object.entries(leanCounts).sort((a, b) => b[1] - a[1])[0][0] : null;
  const blindSpotLean = dominantLean === "Left" ? "Right" : dominantLean === "Right" ? "Left" : null;

  const blindSpotArticles = [];
  if (blindSpotLean) {
    for (const a of allCurrentArticles) {
      if (articleLean(a.url, a.src) === blindSpotLean && !viewedUrls.has(a.url)) {
        blindSpotArticles.push(a);
        if (blindSpotArticles.length >= 2) break;
      }
    }
  }

  const profileHTML = topSources.length > 0 ? `
    <div class="reading-profile-card">
      <h3 class="bookmarks-heading">Your Reading Profile</h3>
      <div class="profile-grid">
        <div class="profile-block">
          <div class="profile-block-label">Top Sources</div>
          ${topSources.map(([src, count]) => `
            <div class="source-bar-row">
              <span class="source-bar-name"><span class="dot" style="background:${sourceColor(src)}"></span>${src}</span>
              <div class="source-bar-track">
                <div class="source-bar-fill" style="width:${(count / maxCount * 100).toFixed(0)}%;background:${sourceColor(src)}"></div>
              </div>
              <span class="source-bar-count">${count}</span>
            </div>`).join("")}
        </div>
        <div class="profile-block">
          <div class="profile-block-label">Your Blind Spot</div>
          ${!currentQuery ? `<div class="bookmarks-empty" style="padding:16px 0">Search for a topic first to see your blind spot.</div>`
          : topicViews.length < 3 ? `<div class="bookmarks-empty" style="padding:16px 0">Read at least 3 articles on "${currentQuery}" to see your blind spot (${topicViews.length}/3 so far).</div>`
          : !blindSpotLean ? `<div class="bookmarks-empty" style="padding:16px 0">Your reading on this topic looks balanced.</div>`
          : `
            <div class="blindspot-desc">Based on ${totalLean} articles you've clicked on <strong>"${currentQuery}"</strong>, you've read more <strong>${dominantLean}-leaning</strong> sources. These <strong>${blindSpotLean}-leaning</strong> articles haven't been on your radar:</div>
            ${blindSpotArticles.length ? `
              <div class="blindspot-list">
                ${blindSpotArticles.map(a => `
                  <a href="${a.url}" target="_blank" rel="noopener" class="blindspot-article">
                    <span class="blindspot-src"><span class="dot" style="background:${sourceColor(a.src)}"></span>${a.src}</span>
                    <span class="blindspot-title">${a.title}</span>
                  </a>`).join("")}
              </div>` : `<div class="bookmarks-empty" style="padding:16px 0">No unread ${blindSpotLean}-leaning articles found for this topic.</div>`}
          `}
        </div>
      </div>
    </div>` : "";

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

  const historyCards = (history || []).slice(0, 5).map(h => `
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
    ${profileHTML}
    <h3 class="bookmarks-heading" style="margin-top:28px">Recently Viewed</h3>
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
    clusterData = toClusterData(normalized);
    channelSummaryCache.clear();

    const sources = Object.keys(channelData).sort();
    assignSourceColors(sources);
    buildSourceFilters(sources);
    buildChannelCards(sources);
    setLastUpdated(updatedAt);

    renderTimeline();
    if (currentView === "clusters") renderStoryClusters();
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

  renderLLM(); // initial empty state

  const savedSearch = sessionStorage.getItem("lastSearch");
  if (savedSearch) {
    try {
      const { query, results } = JSON.parse(savedSearch);
      currentQuery = query;
      landingEl.classList.add("hidden");
      loadLLMData(query); // fire in parallel, no await
      await loadAndRender(query, results);
      setStoryHeadline(query);
    } catch (_) {
      sessionStorage.removeItem("lastSearch");
    }
  }
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
