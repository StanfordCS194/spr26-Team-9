## Link to the Wiki Homepage
[home](https://github.com/StanfordCS194/spr26-Team-9/wiki) 

## Repository Overview

### `frontend/`
Frontend for the user-facing web application. 

### `backend/`
Backend for the user-facing web application. 

### `webscraper/`
Automated data ingestion pipeline. Fetches news articles from NewsAPI, NYT, and Currents API, normalizes them into a common format, and saves results to `data/`.

### `data_analysis_nlp/`
NLP analysis scripts for source bias clustering, sentiment analysis, and text statistics.

### `data_analysis_llms/`
LLM-based article analysis pipeline using NVIDIA Nemotron. Produces structured per-article analysis (claims, framing, stakeholders) cached in `data/llm_analysis.json`.

### `visualizations/`
Visualizations from experiments 
