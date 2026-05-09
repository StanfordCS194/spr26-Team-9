import OpenAI from "openai";

const client = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY,
});

export default async function handler(req, res) {
  if (req.method !== "POST") {
    return res.status(405).json({ error: "Method not allowed" });
  }

  try {
    const { articles } = req.body;

    if (!articles || articles.length !== 2) {
      return res.status(400).json({ error: "Exactly 2 articles required" });
    }

    const response = await client.responses.create({
      model: "gpt-4.1-mini",
      input: `
Compare these two news articles.

Return ONLY valid JSON with this shape:
{
  "article1": {
    "perspectiveTitle": "",
    "source": "",
    "coreArgument": "",
    "keyPoints": ["", "", ""]
  },
  "article2": {
    "perspectiveTitle": "",
    "source": "",
    "coreArgument": "",
    "keyPoints": ["", "", ""]
  },
  "keyDifferences": [
    {
      "category": "",
      "article1View": "",
      "article2View": ""
    }
  ]
}

Article 1:
Title: ${articles[0].title}
Source: ${articles[0].src}
Date: ${articles[0].isoTime || articles[0].date || ""}
Summary: ${articles[0].summary || ""}

Article 2:
Title: ${articles[1].title}
Source: ${articles[1].src}
Date: ${articles[1].isoTime || articles[1].date || ""}
Summary: ${articles[1].summary || ""}
      `,
    });

    const text = response.output_text;
    const json = JSON.parse(text);

    return res.status(200).json(json);
  } catch (err) {
    console.error(err);
    return res.status(500).json({ error: "Comparison failed" });
  }
}