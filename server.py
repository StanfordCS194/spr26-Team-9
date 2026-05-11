#!/usr/bin/env python3
"""
Local dev server for News Narrative Tracker.
Serves the frontend and handles search requests that trigger the scraper.

Usage:
    python server.py
Then open: http://localhost:8080
"""
import os
import shutil
import subprocess
import sys

# Use the same Python that's running this server (has all project dependencies)
PYTHON = shutil.which("python") or sys.executable

from flask import Flask, jsonify, request, send_from_directory

HERE = os.path.dirname(os.path.abspath(__file__))

app = Flask(__name__)


@app.route("/")
def index():
    return send_from_directory(os.path.join(HERE, "frontend"), "index.html")


@app.route("/<path:filename>")
def frontend_files(filename):
    return send_from_directory(os.path.join(HERE, "frontend"), filename)


@app.route("/data/<path:filename>")
def data_files(filename):
    return send_from_directory(os.path.join(HERE, "data"), filename)


@app.route("/api/articles")
def api_articles():
    return send_from_directory(os.path.join(HERE, "data"), "articles.json")


@app.route("/api/progress")
def api_progress():
    """Returns how many of the 3 API scrapes have completed (0–3)."""
    data_dir = os.path.join(HERE, "data")
    apis = ["newsapi", "nyt", "current"]
    done = sum(
        1 for api in apis
        if os.path.isfile(os.path.join(data_dir, f"{api}_articles.json"))
    )
    merged = os.path.isfile(os.path.join(data_dir, "articles.json"))
    return jsonify({"done": done, "total": len(apis), "merged": merged})


@app.route("/search", methods=["POST"])
def search():
    query = (request.json or {}).get("query", "").strip()
    if not query:
        return jsonify({"error": "No query provided"}), 400

    # Clear old per-API article files so previous query results don't bleed in
    data_dir = os.path.join(HERE, "data")
    if os.path.isdir(data_dir):
        for fname in os.listdir(data_dir):
            if fname.endswith("_articles.json"):
                os.remove(os.path.join(data_dir, fname))

    try:
        subprocess.run(
            [PYTHON, os.path.join(HERE, "webscraper", "refresh.py"),
             "--query", query],
            check=True,
            timeout=180,
        )
        return jsonify({"status": "ok"})
    except subprocess.CalledProcessError as e:
        return jsonify({"error": str(e)}), 500
    except subprocess.TimeoutExpired:
        return jsonify({"error": "Scraping timed out"}), 504


if __name__ == "__main__":
    app.run(port=8080, debug=False)
