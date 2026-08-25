"""
Generates one "AI tool solves a real problem" post idea using Gemini,
renders a simple image card, uploads it to Imgur (free, anonymous),
saves a draft.json, and sends a Telegram preview with Approve/Skip instructions.

Run by: .github/workflows/generate.yml (once a day on a schedule)
"""
import os
import json
import time
import textwrap
import requests
from datetime import datetime, timezone
from PIL import Image, ImageDraw, ImageFont

# ---------- Config (read from GitHub Actions secrets) ----------
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
# GitHub repo info, used to build a public raw URL for the generated image
GITHUB_REPOSITORY = os.environ["GITHUB_REPOSITORY"]  # e.g. "yourname/ig-ai-bot", auto-provided by Actions
GITHUB_REF_NAME = os.environ.get("GITHUB_REF_NAME", "main")

STATE_FILE = "state.json"
DRAFT_FILE = "draft.json"

CATEGORIES = [
    "writing & content creation",
    "coding & debugging",
    "research & summarizing information",
    "scheduling & meetings",
    "design & visuals",
    "data entry & spreadsheets",
]


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"category_index": 0, "telegram_offset": 0}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def call_gemini(category):
    prompt = f"""You help run an Instagram account about AI tools that solve real work problems
and save people time. Give me ONE post idea for the category: "{category}".

Pick a real, currently well-known AI tool (do not invent fake tools or fake features).
Keep it genuinely useful and specific.

Respond ONLY with valid JSON, no markdown, no backticks, in this exact shape:
{{
  "tool_name": "short tool name",
  "problem": "one sentence describing the real problem/pain point",
  "solution": "one or two sentences on how the tool solves it",
  "time_saved": "short phrase, e.g. 'saves ~2 hours a week'",
  "headline": "short punchy headline for the image, max 8 words",
  "caption": "engaging instagram caption, 2-4 short paragraphs, no hashtags in this field",
  "hashtags": "12-18 relevant hashtags separated by spaces, include #AItools and similar"
}}"""

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-latest:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"thinkingConfig": {"thinkingBudget": 0}},
    }

    last_error = None
    for attempt in range(5):
        try:
            resp = requests.post(url, json=payload, timeout=120)
            if resp.status_code in (429, 500, 502, 503, 504):
                last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                raise requests.exceptions.HTTPError(last_error)
            resp.raise_for_status()
            text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
            text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            return json.loads(text)
        except (requests.exceptions.RequestException, KeyError, json.JSONDecodeError) as e:
            last_error = str(e)
            wait = 10 * (attempt + 1)
            print(f"Gemini call failed (attempt {attempt + 1}/5): {last_error}. Retrying in {wait}s...")
            time.sleep(wait)

    raise RuntimeError(f"Gemini API failed after 5 attempts. Last error: {last_error}")


def make_image(headline, tool_name, out_path="post_image.png"):
    W, H = 1080, 1080
    bg = (17, 17, 24)
    accent = (120, 170, 255)
    img = Image.new("RGB", (W, H), bg)
    draw = ImageDraw.Draw(img)

    try:
        font_headline = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 72
        )
        font_tool = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 44
        )
        font_tag = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 34
        )
    except OSError:
        font_headline = font_tool = font_tag = ImageFont.load_default()

    draw.text((70, 70), "AI TOOL TIP", font=font_tag, fill=accent)

    wrapped = textwrap.wrap(headline, width=18)
    y = 220
    for line in wrapped:
        draw.text((70, y), line, font=font_headline, fill="white")
        y += 90

    draw.rectangle([70, y + 20, 300, y + 26], fill=accent)
    draw.text((70, y + 60), f"Tool: {tool_name}", font=font_tool, fill=accent)

    img.save(out_path)
    return out_path


def save_for_github_hosting(image_path):
    """
    Instead of uploading to a third-party image host, we commit the image
    into the repo (in /posts/) and use GitHub's raw content URL, which is
    publicly accessible for public repos. The workflow's git-commit step
    pushes this file right after this script runs.
    """
    os.makedirs("posts", exist_ok=True)
    filename = f"post_{int(time.time())}.png"
    dest_path = os.path.join("posts", filename)
    with open(image_path, "rb") as src, open(dest_path, "wb") as dst:
        dst.write(src.read())

    raw_url = (
        f"https://raw.githubusercontent.com/{GITHUB_REPOSITORY}/"
        f"{GITHUB_REF_NAME}/{dest_path}"
    )
    return dest_path, raw_url


def send_telegram_preview(local_image_path, caption, hashtags):
    full_caption = f"{caption}\n\n{hashtags}"
    text = (
        "📋 *New post ready for review*\n\n"
        f"{full_caption}\n\n"
        "Reply *APPROVE* to publish this to Instagram, or *SKIP* to discard it."
    )
    with open(local_image_path, "rb") as f:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": text[:1024],  # Telegram caption limit
                "parse_mode": "Markdown",
            },
            files={"photo": f},
            timeout=30,
        )


def main():
    state = load_state()
    category = CATEGORIES[state["category_index"] % len(CATEGORIES)]

    idea = call_gemini(category)
    image_path = make_image(idea["headline"], idea["tool_name"])
    saved_path, image_url = save_for_github_hosting(image_path)

    draft = {
        "category": category,
        "tool_name": idea["tool_name"],
        "caption": idea["caption"],
        "hashtags": idea["hashtags"],
        "image_path": saved_path,
        "image_url": image_url,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending",
    }
    with open(DRAFT_FILE, "w") as f:
        json.dump(draft, f, indent=2)

    send_telegram_preview(image_path, idea["caption"], idea["hashtags"])

    state["category_index"] = (state["category_index"] + 1) % len(CATEGORIES)
    save_state(state)


if __name__ == "__main__":
    main()