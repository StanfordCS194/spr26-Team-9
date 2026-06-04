## Quickstart

**Prerequisites:** Python 3.12–3.14 and [uv](https://docs.astral.sh/uv/getting-started/installation/).

1. Install dependencies from the project root:
   ```
   uv sync
   ```

2. Create a `.env` file in the project root with any required API keys (see `.env.example` if present).

3. Start the backend (also serves the frontend):
   ```
   uv run --directory backend uvicorn main:app --port 8000 --reload
   ```

4. Open **http://127.0.0.1:8000** in your browser.

---

## Link to the Wiki Homepage
[home](https://github.com/StanfordCS194/spr26-Team-9/wiki) 

## Repository Overview

### `frontend/`
Frontend for the user-facing web application. 

### `backend/`
Backend for the user-facing web application. 

### `webscraper/`
Automated data ingestion pipeline. Fetches news articles from NewsAPI, NYT, and Currents API, normalizes them into a common format, and saves results to `data/`.

### `experiments/`
Experiments with story clustering using NLP and LLMs. Also includes data visualizations. These are purely exploratory experiments to guide development; code is not used in final app. 

### `data_analysis_nlp/`
NLP analysis scripts for NLP-powered computation of bias labels.

### `data_public/` 
Lightweight bias data and cached webscraped files to be referenced in web app. 