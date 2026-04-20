import json
import requests
from api_keys import NYT_API_KEY

res = requests.get(
    "https://api.nytimes.com/svc/search/v2/articlesearch.json",
    params={
        "q":       "Trump Pope Leo",
        "api-key": NYT_API_KEY,
        "page":    0,
    },
    timeout=15,
)
res.raise_for_status()

docs = res.json().get("response", {}).get("docs", [])
if not docs:
    print("No results.")
else:
    print(f"=== {len(docs)} docs returned. First doc keys and values: ===\n")
    for key, value in docs[0].items():
        print(f"{key}:\n  {json.dumps(value, indent=4)}\n")
