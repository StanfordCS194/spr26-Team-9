## `frontend/`

For UI. Display timeline

---

### Files

| File | Description |
|---|---|
| `index.html` | App shell — defines the three views: Timeline, Channels, LLM, and the compare modal |
| `app.js` | All application logic — data loading, transformation, rendering, and interaction |
| `styles.css` | Styling using CSS variables; responsive breakpoint at 1100px |
| `frontend_data.json` | Static sample data, not used at runtime. The app loads from `../data/articles.json` |

---

### Views

**Timeline**  
Default view. Articles are grouped by date in chronological columns. Up to 5 articles are shown per day, ranked by source credibility and cross-outlet coverage. Hovering shows a summary tooltip, and clicking a source name highlights only that source across the timeline.

**Channels**  
Grid of news source cards. Clicking a source shows all of its articles grouped by date.

**LLM**  
Collapsible cards showing AI-generated summaries, such as ChatGPT and Gemini, with political leaning. Currently hardcoded.

---

### Filters: Timeline View

| Filter | Description |
|---|---|
| Source checkboxes | Show or hide individual outlets; includes All/None toggles |
| Date range | Restrict the timeline to a start and end date |
| Political leaning slider | UI only — not yet wired up |

---

### Data Flow

```text
data/articles.json
        ↓
init() in app.js
        ↓
toTimelineData()  →  renderTimeline()
toChannelData()   →  buildChannelCards()

app.js fetches ../data/articles.json on load. If it is missing, an error suggests running: python webscraper/refresh.py


Source credibility tiers used for ranking:

  Tier 3, highest: NYT, Reuters, AP, BBC, NPR, PBS, The Guardian, Washington Post
  Tier 2: The Atlantic, Politico, Axios, The Hill, CNN, ABC, NBC, CBS
  Tier 1, default: everything else

### Running

Before running, make sure you ran refresh.py inside webscraper directory

From the repo root:

python -m http.server 8080

Then open:

http://localhost:8080/frontend/




