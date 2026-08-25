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
DRAFTS_FILE = "drafts.json"

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

Writing style rules (very important):
- Use very simple, plain English. Short words. Short sentences.
- Write like you're explaining to a friend, not a tech expert.
- "problem" must be ONE short sentence, max 14 words.
- "solution" must be ONE short sentence, max 16 words.
- "headline" must be max 6 words, punchy and simple.

Respond ONLY with valid JSON, no markdown, no backticks, in this exact shape:
{{
  "tool_name": "short tool name",
  "problem": "one very short simple sentence, max 14 words",
  "solution": "one very short simple sentence, max 16 words",
  "time_saved": "short phrase, e.g. 'Saves ~2 hours a week'",
  "headline": "short punchy headline for the image, max 6 words",
  "caption": "engaging instagram caption, 2-4 short paragraphs, simple English, no hashtags in this field",
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


def _wrap_limited(draw, text, font, max_width, max_lines):
    """Wrap text, and if it's still too long, truncate with an ellipsis so
    it can never overflow into other elements."""
    lines = _wrap_by_pixels(draw, text, font, max_width)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while draw.textlength(last + "...", font=font) > max_width and len(last) > 1:
            last = last[:-1].rstrip()
        lines[-1] = last + "..."
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


def _draw_code_window(draw, x, y, w, h):
    """A little stylized code-editor mockup for visual flair — pure vector,
    no external images needed."""
    draw.rounded_rectangle([x, y, x + w, y + h], radius=18, fill=(26, 27, 40))
    draw.rounded_rectangle([x, y, x + w, y + 40], radius=18, fill=(38, 40, 58))
    draw.rectangle([x, y + 22, x + w, y + 40], fill=(38, 40, 58))  # square off bottom of title bar

    dot_colors = [(255, 95, 86), (255, 189, 46), (39, 201, 63)]
    for i, c in enumerate(dot_colors):
        draw.ellipse([x + 18 + i * 24, y + 14, x + 30 + i * 24, y + 26], fill=c)

    line_colors = [(120, 170, 255), (255, 150, 200), (150, 255, 190),
                   (255, 210, 120), (180, 150, 255), (120, 200, 255)]
    widths = [0.75, 0.5, 0.85, 0.4, 0.65, 0.3, 0.55]
    ly = y + 62
    for i, wfrac in enumerate(widths):
        if ly > y + h - 22:
            break
        col = line_colors[i % len(line_colors)]
        lw = int((w - 36) * wfrac)
        draw.rounded_rectangle([x + 18, ly, x + 18 + lw, ly + 14], radius=7, fill=col)
        ly += 30


def _draw_laptop(draw, x, y, w, h, color, accent):
    screen_h = int(h * 0.68)
    draw.rounded_rectangle([x, y, x + w, y + screen_h], radius=14, fill=(24, 26, 40), outline=color, width=5)
    inset = 12
    draw.rounded_rectangle(
        [x + inset, y + inset, x + w - inset, y + screen_h - inset],
        radius=8, fill=(16, 18, 30)
    )
    # a little code glyph on the screen
    draw.rounded_rectangle([x + inset + 14, y + inset + 16, x + inset + 60, y + inset + 26], radius=5, fill=accent)
    draw.rounded_rectangle([x + inset + 14, y + inset + 34, x + inset + 90, y + inset + 44], radius=5, fill=(150, 255, 190))
    draw.rounded_rectangle([x + inset + 14, y + inset + 52, x + inset + 45, y + inset + 62], radius=5, fill=(255, 150, 200))

    base_y = y + screen_h + 8
    draw.rounded_rectangle([x - 18, base_y, x + w + 18, base_y + 16], radius=8, fill=color)


def _draw_clock_icon(draw, cx, cy, r, color):
    draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=5)
    draw.line([cx, cy, cx, cy - int(r * 0.55)], fill=color, width=5)
    draw.line([cx, cy, cx + int(r * 0.45), cy + int(r * 0.15)], fill=color, width=5)


def make_image(idea, out_path="post_image.png"):
    W, H = 1080, 1350  # portrait 4:5 — Instagram's recommended feed size, extra room for text
    bg_top = (16, 17, 26)
    bg_bottom = (9, 10, 18)
    accent = (99, 155, 255)
    accent_soft = (40, 50, 75)
    white = (245, 246, 250)
    muted = (170, 176, 195)
    green = (110, 220, 160)
    orange = (255, 176, 102)

    img = Image.new("RGB", (W, H), bg_top)
    draw = ImageDraw.Draw(img)
    _vertical_gradient(draw, W, H, bg_top, bg_bottom)

    def font(path, size):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            return ImageFont.load_default()

    f_badge = font("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
    f_headline = font("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 62)
    f_label = font("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
    f_body = font("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 34)
    f_tool = font("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 34)
    f_footer = font("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)

    margin = 72
    content_width = W - margin * 2
    y = 64

    # Top badge
    _rounded_pill(draw, (margin, y), "AI TOOL TIP", f_badge, (12, 14, 22), accent)

    # Little code-editor mockup, top right, for visual flair
    _draw_code_window(draw, W - 300, 50, 230, 150)

    y += 170

    # Headline (max 3 lines, always fits since it's short by prompt design)
    for line in _wrap_limited(draw, idea["headline"], f_headline, content_width, 3):
        draw.text((margin, y), line, font=f_headline, fill=white)
        y += 74
    y += 16

    draw.rounded_rectangle([margin, y, margin + 180, y + 6], radius=3, fill=accent)
    y += 46

    # Tool name pill (colored square bullet instead of an emoji icon)
    pill_box = _rounded_pill(draw, (margin, y), idea["tool_name"], f_tool, white, accent_soft, pad_x=26)
    draw.rounded_rectangle([margin + 10, y + 16, margin + 22, y + 28], radius=3, fill=accent)
    y += 96

    # Problem block (capped at 3 lines so it can never collide with what follows)
    draw.text((margin, y), "THE PROBLEM", font=f_label, fill=orange)
    y += 42
    for line in _wrap_limited(draw, idea["problem"], f_body, content_width, 3):
        draw.text((margin, y), line, font=f_body, fill=white)
        y += 44
    y += 26

    # Solution block (capped at 3 lines)
    draw.text((margin, y), "THE FIX", font=f_label, fill=green)
    y += 42
    for line in _wrap_limited(draw, idea["solution"], f_body, content_width, 3):
        draw.text((margin, y), line, font=f_body, fill=white)
        y += 44
    y += 40

    # Time-saved highlight card — placed dynamically right after the content,
    # never at a fixed spot, so it can never overlap the text above it
    card_h = 100
    draw.rounded_rectangle(
        [margin, y, W - margin, y + card_h],
        radius=20, outline=accent, width=3, fill=(20, 24, 38)
    )
    _draw_clock_icon(draw, margin + 45, y + card_h // 2, 24, accent)
    draw.text((margin + 90, y + 28), idea["time_saved"], font=f_tool, fill=accent)
    y += card_h + 40

    # Little laptop graphic for extra "tech" visual flavor
    _draw_laptop(draw, margin, y, 150, 110, accent, accent)

    # Footer, to the right of the laptop
    draw.text((margin + 190, y + 20), "Follow for daily AI tool tips",
              font=f_footer, fill=muted)
    draw.text((margin + 190, y + 54), "Save this post so you don't lose it",
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
    with open(DRAFTS_FILE, "w") as f:
        json.dump(draft, f, indent=2)

    send_telegram_preview(image_path, idea["caption"], idea["hashtags"])

    state["category_index"] = (state["category_index"] + 1) % len(CATEGORIES)
    save_state(state)


if __name__ == "__main__":
    main()