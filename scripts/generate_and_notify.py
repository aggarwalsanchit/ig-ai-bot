"""
Generates one "AI tool solves a real problem" post idea using Gemini,
renders a polished image card, commits it to the repo for public hosting,
saves a draft.json, and sends a Telegram preview with Approve/Skip instructions.

Run by: .github/workflows/generate.yml (once a day on a schedule)
"""
import os
import json
import time
import requests
import google.generativeai as genai
from datetime import datetime, timezone
from PIL import Image, ImageDraw, ImageFont

# ---------- Config (read from GitHub Actions secrets) ----------
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
# GitHub repo info, used to build a public raw URL for the generated image
GITHUB_REPOSITORY = os.environ["GITHUB_REPOSITORY"]  # e.g. "yourname/ig-ai-bot", auto-provided by Actions
GITHUB_REF_NAME = os.environ.get("GITHUB_REF_NAME", "main")

genai.configure(api_key=GEMINI_API_KEY)

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

    model = genai.GenerativeModel("gemini-2.5-flash-lite")

    last_error = None
    for attempt in range(5):
        try:
            resp = model.generate_content(prompt)
            text = resp.text.strip()
            text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
            return json.loads(text)
        except Exception as e:
            last_error = str(e)
            wait = 10 * (attempt + 1)
            print(f"Gemini call failed (attempt {attempt + 1}/5): {last_error}. Retrying in {wait}s...")
            time.sleep(wait)

    raise RuntimeError(f"Gemini API failed after 5 attempts. Last error: {last_error}")


def _wrap_by_pixels(draw, text, font, max_width):
    """Wrap text so each line fits within max_width pixels for the given font."""
    words = text.split()
    lines, current = [], ""
    for word in words:
        trial = f"{current} {word}".strip()
        if draw.textlength(trial, font=font) <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def _vertical_gradient(draw, W, H, top_color, bottom_color):
    for y in range(H):
        ratio = y / H
        r = int(top_color[0] + (bottom_color[0] - top_color[0]) * ratio)
        g = int(top_color[1] + (bottom_color[1] - top_color[1]) * ratio)
        b = int(top_color[2] + (bottom_color[2] - top_color[2]) * ratio)
        draw.line([(0, y), (W, y)], fill=(r, g, b))


def _rounded_pill(draw, xy, text, font, fg, bg, pad_x=22, pad_y=12):
    x, y = xy
    w = draw.textlength(text, font=font)
    ascent, descent = font.getmetrics()
    h = ascent + descent
    box = [x, y, x + w + pad_x * 2, y + h + pad_y * 2]
    draw.rounded_rectangle(box, radius=(h + pad_y * 2) // 2, fill=bg)
    draw.text((x + pad_x, y + pad_y), text, font=font, fill=fg)
    return box


def make_image(idea, out_path="post_image.png"):
    W, H = 1080, 1080
    bg_top = (18, 18, 28)
    bg_bottom = (10, 12, 20)
    accent = (99, 155, 255)
    accent_soft = (40, 50, 75)
    white = (245, 246, 250)
    muted = (170, 176, 195)
    green = (110, 220, 160)

    img = Image.new("RGB", (W, H), bg_top)
    draw = ImageDraw.Draw(img)
    _vertical_gradient(draw, W, H, bg_top, bg_bottom)

    draw.ellipse([W - 420, -220, W + 180, 380], fill=(28, 34, 52))
    draw.ellipse([W - 320, -160, W + 60, 260], fill=(24, 28, 44))

    def font(path, size):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            return ImageFont.load_default()

    f_badge = font("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
    f_headline = font("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 66)
    f_label = font("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
    f_body = font("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 34)
    f_tool = font("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 36)
    f_footer = font("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 26)

    margin = 72
    y = 80

    _rounded_pill(draw, (margin, y), "AI TOOL TIP", f_badge, (12, 14, 22), accent)
    y += 100

    for line in _wrap_by_pixels(draw, idea["headline"], f_headline, W - margin * 2):
        draw.text((margin, y), line, font=f_headline, fill=white)
        y += 78
    y += 10

    draw.rounded_rectangle([margin, y, margin + 180, y + 6], radius=3, fill=accent)
    y += 50

    _rounded_pill(draw, (margin, y), f"🔧  {idea['tool_name']}", f_tool, (12, 14, 22), accent_soft)
    y += 100

    draw.text((margin, y), "THE PROBLEM", font=f_label, fill=muted)
    y += 44
    for line in _wrap_by_pixels(draw, idea["problem"], f_body, W - margin * 2):
        draw.text((margin, y), line, font=f_body, fill=white)
        y += 46
    y += 30

    draw.text((margin, y), "THE FIX", font=f_label, fill=green)
    y += 44
    for line in _wrap_by_pixels(draw, idea["solution"], f_body, W - margin * 2):
        draw.text((margin, y), line, font=f_body, fill=white)
        y += 46
    y += 40

    card_top = H - 220
    draw.rounded_rectangle(
        [margin, card_top, W - margin, card_top + 110],
        radius=20, outline=accent, width=3, fill=(22, 26, 40)
    )
    draw.text((margin + 30, card_top + 30), f"⏱  {idea['time_saved']}", font=f_tool, fill=accent)

    draw.text((margin, H - 70), "Follow for daily AI tool tips → save this post 📌",
              font=f_footer, fill=muted)

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
    image_path = make_image(idea)
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