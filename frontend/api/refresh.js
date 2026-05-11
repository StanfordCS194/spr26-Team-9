module.exports = async function handler(req, res) {
  if (req.method !== "POST") {
    return res.status(405).json({ ok: false, error: "Method not allowed" });
  }

  const token = process.env.GITHUB_TOKEN;
  if (!token) {
    return res.status(500).json({ ok: false, error: "GITHUB_TOKEN not configured" });
  }

  const response = await fetch(
    "https://api.github.com/repos/StanfordCS194/spr26-Team-9/actions/workflows/refresh.yml/dispatches",
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        ref: "main",
        inputs: {
          query: req.body?.query
        }
      }),
    }
  );

  if (response.status === 204) {
    return res.json({ ok: true });
  }

  const text = await response.text();
  console.error("GitHub API error", response.status, text);
  return res.status(500).json({ ok: false, status: response.status, error: text });
};
