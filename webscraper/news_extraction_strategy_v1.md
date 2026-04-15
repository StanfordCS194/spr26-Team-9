# Media Data Extraction Strategy: Free & Accessible Sources

This document outlines the primary data targets for the **LLM & Media Bias Tracker** project. Given the goal to build a working prototype by June 2026, the strategy prioritizes sources that provide high-quality, politically diverse text without triggering enterprise-grade anti-bot defenses (like Cloudflare or DataDome). 

The data extracted here will feed directly into the NLP clustering algorithms and the LLM bias detection pipeline.

---

## 1. Official Open APIs (High Reliability, Clean Data)
These sources provide official API endpoints. They require an API key but are free for non-commercial and academic use.

### The Guardian
* **Access Method:** The Guardian Open Platform API.
* **What it offers:** Full article text, rich metadata, tags, author info, and exact publication timestamps. 
* **Project Application:** This should be the foundational anchor for **Feature 1 (Narrative Timeline)**. Because it provides the full text cleanly, it is also the best baseline dataset for training the clustering models in **Feature 3**.

### The New York Times
* **Access Method:** NYT Article Search API.
* **What it offers:** Extensive metadata, headlines, publication dates, and the *lead paragraph* (but not the full text).
* **Project Application:** Excellent for tracking *when* a major US publication picks up a story. The lead paragraph is usually sufficient to map the initial framing of the narrative for the timeline overview, even without the full body text.

---

## 2. Permissive Scraping Targets (The Hybrid Approach)
These sites do not offer full-text APIs but maintain relatively permissive `robots.txt` files and are less likely to aggressively block standard scraping tools. 
**Best Extraction Method:** Parse their RSS Feeds to get the article URLs, then use the `newspaper3k` Python library to extract the clean text.

### Politico
* **Political Leaning:** Center / Center-Left (US Politics focus).
* **What it offers:** In-depth political coverage and analysis. RSS feeds are highly active.
* **Project Application:** Crucial for tracking shifts in US political narratives. The text extracted here will be highly useful for highlighting conflicting claims in the deep-dive timeline.

### Fox News
* **Political Leaning:** Right / Conservative.
* **What it offers:** Extensive coverage of breaking news with a distinct editorial framing. Relatively open to basic web crawlers.
* **Project Application:** Essential for the **Media Bias Database (Feature 3)**. Comparing the narrative framing extracted from Fox News against The Guardian or NYT will form the basis of the clustering algorithm's bias metrics.

### Al Jazeera (English)
* **Political Leaning:** Non-Western / Global perspective.
* **What it offers:** Broad international coverage, often highlighting details or angles omitted by US/UK domestic media.
* **Project Application:** Adds a necessary global dimension to the timeline, allowing the platform to showcase how a narrative is framed outside of standard Western media bubbles.

### NPR (National Public Radio)
* **Political Leaning:** Center / Public Broadcasting.
* **What it offers:** Transcripts and text articles. Public broadcasters generally utilize fewer commercial anti-bot protections.
* **Project Application:** Provides a highly factual, relatively neutral baseline to compare against more heavily opinionated outlets.

---

## 3. The LLM Testing Endpoints (Feature 2)
To execute the novel LLM bias detection, the pipeline must query the models themselves.

### OpenAI (ChatGPT), Anthropic (Claude), Google (Gemini)
* **Access Method:** Official Developer APIs (Free tiers / developer credits).
* **What it offers:** Programmatic access to the models.
* **Project Application:** The automated testing loop. The pipeline will send standard, neutral prompts (e.g., "Summarize the events of [Topic X]. Cite your sources.") to these APIs. The system will then extract the URLs/publishers returned in the LLM's response and cross-reference them against the bias clusters formed from the data in Categories 1 & 2 to quantify the LLM's implicit bias.

---

## Technical Implementation Summary

To ensure the architecture remains stable through the spring semester:
1. **Metadata & URL Discovery:** Rely exclusively on Official APIs and RSS Feeds. Do not write custom HTML scrapers to find links on homepages.
2. **Text Extraction:** Pass discovered URLs to `newspaper3k`. 
3. **Data Storage:** Store all extracted text, metadata, and assigned source bias in a structured database (e.g., PostgreSQL) to be queried by the frontend timeline visualization and the ML clustering scripts.
