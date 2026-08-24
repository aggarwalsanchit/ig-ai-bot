"""
Generates one "AI tool solves a real problem" post idea using Gemini,
renders a simple image card, uploads it to Imgur (free, anonymous),
saves a draft.json, and sends a Telegram preview with Approve/Skip instructions.

Run by: .github/workflows/generate.yml (once a day on a schedule)
"""
import os
import json
import textwrap
import requests
from datetime import datetime, timezone
from PIL import Image, ImageDraw, ImageFont

# ---------- Config (read from GitHub Actions secrets) ----------
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
IMGUR_CLIENT_ID = os.environ["IMGUR_CLIENT_ID"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

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

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}"
    resp = requests.post(
        url,
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=60,
    )
    resp.raise_for_status()
    text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    text = text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    return json.loads(text)


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


def upload_to_imgur(image_path):
    with open(image_path, "rb") as f:
        resp = requests.post(
            "https://api.imgur.com/3/image",
            headers={"Authorization": f"Client-ID {IMGUR_CLIENT_ID}"},
            files={"image": f},
            timeout=60,
        )
    resp.raise_for_status()
    return resp.json()["data"]["link"]


def send_telegram_preview(image_url, caption, hashtags):
    full_caption = f"{caption}\n\n{hashtags}"
    text = (
        "📋 *New post ready for review*\n\n"
        f"{full_caption}\n\n"
        "Reply *APPROVE* to publish this to Instagram, or *SKIP* to discard it."
    )
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
        data={
            "chat_id": TELEGRAM_CHAT_ID,
            "caption": text[:1024],  # Telegram caption limit
            "parse_mode": "Markdown",
        },
        files={"photo": requests.get(image_url, timeout=30).content},
        timeout=30,
    )


def main():
    state = load_state()
    category = CATEGORIES[state["category_index"] % len(CATEGORIES)]

    idea = call_gemini(category)
    image_path = make_image(idea["headline"], idea["tool_name"])
    image_url = upload_to_imgur(image_path)

    draft = {
        "category": category,
        "tool_name": idea["tool_name"],
        "caption": idea["caption"],
        "hashtags": idea["hashtags"],
        "image_url": image_url,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "status": "pending",
    }
    with open(DRAFT_FILE, "w") as f:
        json.dump(draft, f, indent=2)

    send_telegram_preview(image_url, idea["caption"], idea["hashtags"])

    state["category_index"] = (state["category_index"] + 1) % len(CATEGORIES)
    save_state(state)


if __name__ == "__main__":
    main()
