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

#Content scheduling configuration
SCHEDULE_CONFIG = {
    "morning": {
        "time": "09:00",
        "type": "single_image",
        "label": "🖼️ Single Image Post"
    },
    "afternoon": {
        "time": "14:00", 
        "type": "carousel",
        "label": "📚 Carousel (Swipeable)"
    },
    "evening": {
        "time": "19:00",
        "type": "reel",
        "label": "🎬 Reel (Video)"
    }
}

# Prompt styles for each content type
PROMPT_STYLES = {
    "single_image": {
        "headline_max_words": 6,
        "caption_style": "concise, punchy, gets to the point quickly",
        "hashtags_count": "12-15"
    },
    "carousel": {
        "headline_max_words": 8,
        "caption_style": "short, engaging, colorful description",
        "hashtags_count": "15-20"
    },
    "reel": {
        "headline_max_words": 4,
        "caption_style": "super short, exciting, call to action focused",
        "hashtags_count": "10-14"
    }
}

def save_json_atomic(data, filename):
    """Save JSON data atomically to prevent corruption."""
    temp_file = f"{filename}.tmp"
    with open(temp_file, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(temp_file, filename)


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            state = json.load(f)
            # Add default scheduling fields if missing
            if "last_post_time" not in state:
                state["last_post_time"] = ""
            if "posts_today" not in state:
                state["posts_today"] = {
                    "single_image": 0,
                    "carousel": 0,
                    "reel": 0
                }
            if "date" not in state:
                state["date"] = datetime.now().date().isoformat()
            if "content_type_counter" not in state:
                state["content_type_counter"] = 0
            return state
    return {
        "category_index": 0, 
        "telegram_offset": 0,
        "last_post_time": "",
        "posts_today": {"single_image": 0, "carousel": 0, "reel": 0},
        "date": datetime.now().date().isoformat(),
        "content_type_counter": 0
    }


def save_state(state):
    save_json_atomic(state, STATE_FILE)

def get_next_content_type():
    """Determine what type of content to generate based on time of day."""
    state = load_state()
    
    # Reset daily counters if it's a new day
    today = datetime.now().date().isoformat()
    if state.get("date") != today:
        state["date"] = today
        state["posts_today"] = {"single_image": 0, "carousel": 0, "reel": 0}
        state["content_type_counter"] = 0
        save_state(state)
    
    current_hour = datetime.now().hour
    
    # Morning (6 AM - 12 PM): Single Image
    if 6 <= current_hour < 12:
        if state["posts_today"]["single_image"] < 1:
            return "single_image"
    
    # Afternoon (12 PM - 6 PM): Carousel
    elif 12 <= current_hour < 18:
        if state["posts_today"]["carousel"] < 1:
            return "carousel"
    
    # Evening (6 PM - 11 PM): Reel
    elif 18 <= current_hour <= 23:
        if state["posts_today"]["reel"] < 1:
            return "reel"
    
    # If already posted this type today, cycle to next available
    content_types = ["single_image", "carousel", "reel"]
    for ct in content_types:
        if state["posts_today"].get(ct, 0) < 1:
            return ct
    
    # All posted today - return single_image (will be skipped by workflow)
    return "single_image"


def call_gemini(category, content_type="single_image"):
    """
    Generate content based on the content type.
    content_type: "single_image", "carousel", or "reel"
    """
    style = PROMPT_STYLES.get(content_type, PROMPT_STYLES["single_image"])
    
    # Different prompts for different content types
    prompts = {
        "single_image": f"""You help run an Instagram account about AI tools that solve real work problems
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
}}""",

        "carousel": f"""You help run an Instagram account about AI tools.
Create a COLORFUL, VISUAL CAROUSEL (swipeable slides) about: "{category}".

Each slide should be a short, punchy visual statement with minimal text.
Think of it like a vibrant infographic or visual story.

IMPORTANT RULES:
- Each slide MUST have a short title (2-4 words) - think of it as a bold header
- Each slide MUST have very short content (8-12 words max) - like a subtitle or quick fact
- Make it engaging, colorful, and easy to digest visually
- Use action words and make it exciting

Respond ONLY with valid JSON:
{{
  "tool_name": "short tool name (2-3 words)",
  "slides": [
    {{"title": "BOLD HEADER 1", "content": "Quick fact or benefit (8-12 words)"}},
    {{"title": "BOLD HEADER 2", "content": "Quick fact or benefit (8-12 words)"}},
    {{"title": "BOLD HEADER 3", "content": "Quick fact or benefit (8-12 words)"}},
    {{"title": "BOLD HEADER 4", "content": "Quick fact or benefit (8-12 words)"}},
    {{"title": "BOLD HEADER 5", "content": "Quick fact or benefit (8-12 words)"}}
  ],
  "caption": "engaging caption for the carousel, 2-3 short paragraphs, simple English, no hashtags",
  "hashtags": "15-20 relevant hashtags separated by spaces, include #AItools and similar"
}}""",

        "reel": f"""You help run an Instagram account about AI tools.
Create an ENGAGING, VISUAL REEL script about: "{category}".

Reels are fast-paced, colorful, and visually exciting with minimal text.
Think of this like a short animated video with bold text overlays.

IMPORTANT RULES:
- Hook: Very short (3-6 words) - like a bold title card
- Each scene: One BIG idea with very few words (5-8 words max per scene)
- Use emoji and visual language
- Keep it fast-paced and energetic

Respond ONLY with valid JSON:
{{
  "tool_name": "short tool name (2-3 words)",
  "hook": "Super short hook (3-6 words)",
  "problem": "One short sentence (5-8 words)",
  "solution": "One short sentence (5-8 words)", 
  "benefit": "One short sentence (5-8 words)",
  "call_to_action": "Short CTA (3-5 words)",
  "text_overlays": [
    "Scene 1 text: 3-5 words",
    "Scene 2 text: 3-5 words",
    "Scene 3 text: 3-5 words",
    "Scene 4 text: 3-5 words"
  ],
  "caption": "short engaging caption for the reel, 2-3 short paragraphs, no hashtags",
  "hashtags": "12-16 relevant hashtags separated by spaces, include #AItools and similar"
}}"""
    }
    
    prompt = prompts.get(content_type, prompts["single_image"])
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

def make_carousel_images(idea, out_prefix="carousel"):
    """Generate colorful, visual carousel slides with minimal text."""
    image_paths = []
    
    # Color palette for each slide - vibrant and engaging
    color_palettes = [
        # (bg_top, bg_bottom, accent_color, text_color)
        ((255, 107, 107), (200, 50, 50), (255, 255, 255), (255, 255, 255)),   # Red
        ((78, 205, 196), (40, 150, 140), (255, 255, 255), (255, 255, 255)),   # Teal
        ((255, 159, 67), (230, 100, 20), (255, 255, 255), (255, 255, 255)),   # Orange
        ((108, 92, 231), (70, 50, 180), (255, 255, 255), (255, 255, 255)),    # Purple
        ((253, 121, 168), (220, 80, 130), (255, 255, 255), (255, 255, 255)),  # Pink
    ]
    
    slides = idea.get("slides", [
        {"title": "✨ AI POWER", "content": "Transform your workflow with AI"},
        {"title": "⚡ SAVE TIME", "content": "Focus on what really matters"},
        {"title": "🚀 BOOST OUTPUT", "content": "Work faster and smarter"},
        {"title": "💡 SMART TOOLS", "content": "Let AI handle the heavy lifting"},
        {"title": "🎯 GET STARTED", "content": "Try it today and see the difference"}
    ])
    
    for i, slide in enumerate(slides[:5]):
        out_path = f"{out_prefix}_slide_{i+1}.png"
        
        W, H = 1080, 1080
        colors = color_palettes[i % len(color_palettes)]
        bg_top, bg_bottom, accent, text_color = colors
        
        # Create gradient background
        img = Image.new("RGB", (W, H), bg_top)
        draw = ImageDraw.Draw(img)
        _vertical_gradient(draw, W, H, bg_top, bg_bottom)
        
        try:
            f_title = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 80)
            f_content = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 44)
            f_slide = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
            f_tool = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
        except:
            f_title = f_content = f_slide = f_tool = ImageFont.load_default()
        
        margin = 70
        y = 80
        
        # Tool name pill with accent color
        tool_name = idea.get("tool_name", "AI Tool")
        _rounded_pill(draw, (margin, margin), tool_name, f_tool, (255, 255, 255), (0, 0, 0, 80))
        
        # Slide indicator with accent color
        slide_text = f"{i+1}/{len(slides[:5])}"
        _rounded_pill(draw, (W - margin - 120, margin), slide_text, f_slide, (255, 255, 255), (0, 0, 0, 80))
        
        # Big bold title - centered
        title_text = slide.get("title", f"Slide {i+1}")
        y = 350
        for line in _wrap_limited(draw, title_text, f_title, W - margin * 2, 2):
            # Center align
            bbox = draw.textbbox((0, 0), line, font=f_title)
            text_width = bbox[2] - bbox[0]
            x = (W - text_width) // 2
            draw.text((x, y), line, font=f_title, fill=text_color)
            y += 100
        
        y += 40
        
        # Content text - smaller, bold, with accent color
        content_text = slide.get("content", "")
        for line in _wrap_limited(draw, content_text, f_content, W - margin * 2, 2):
            bbox = draw.textbbox((0, 0), line, font=f_content)
            text_width = bbox[2] - bbox[0]
            x = (W - text_width) // 2
            draw.text((x, y), line, font=f_content, fill=accent)
            y += 60
        
        # Decorative bottom line
        y = H - 100
        draw.line([(W//2 - 100, y), (W//2 + 100, y)], fill=accent, width=4)
        
        img.save(out_path)
        image_paths.append(out_path)
        print(f"✅ Carousel slide {i+1} created: {out_path}")
    
    return image_paths

def make_reel_images(reel_idea, out_prefix="reel_scene"):
    """
    Generate colorful, visual reel scenes with minimal text.
    Each scene looks like an animated card.
    """
    image_paths = []
    
    # Vibrant color schemes for each scene
    color_schemes = [
        # (bg_top, bg_bottom, accent_color, glow_color)
        ((255, 71, 87), (180, 20, 40), (255, 255, 255), (255, 200, 200)),     # Red glow
        ((54, 201, 201), (20, 150, 150), (255, 255, 255), (200, 255, 255)),   # Teal glow
        ((255, 159, 67), (230, 100, 20), (255, 255, 255), (255, 220, 200)),   # Orange glow
        ((108, 92, 231), (70, 50, 180), (255, 255, 255), (200, 200, 255)),    # Purple glow
    ]
    
    # Default scenes if not provided
    default_scenes = [
        {"text": "AI TOOL TIP", "subtext": "Your productivity booster"},
        {"text": "THE PROBLEM", "subtext": "Too much manual work"},
        {"text": "THE SOLUTION", "subtext": "Let AI do the heavy lifting"},
        {"text": "START NOW", "subtext": "Try it today 💪"}
    ]
    
    text_overlays = reel_idea.get("text_overlays", [])
    scenes = []
    
    # Build scenes from available data
    if text_overlays:
        for i, text in enumerate(text_overlays[:4]):
            scenes.append({"text": text, "subtext": ""})
    else:
        scenes = default_scenes
    
    # Override with specific reel data if available
    if "hook" in reel_idea and len(scenes) > 0:
        scenes[0]["text"] = reel_idea["hook"]
        scenes[0]["subtext"] = "🔥 Start here"
    
    if "problem" in reel_idea and len(scenes) > 1:
        scenes[1]["text"] = reel_idea["problem"]
        scenes[1]["subtext"] = "⚠️ Common issue"
    
    if "solution" in reel_idea and len(scenes) > 2:
        scenes[2]["text"] = reel_idea["solution"]
        scenes[2]["subtext"] = "✅ Game changer"
    
    if "benefit" in reel_idea and len(scenes) > 3:
        scenes[3]["text"] = reel_idea["benefit"]
        scenes[3]["subtext"] = "💡 Key benefit"
    
    for i, scene in enumerate(scenes[:4]):
        out_path = f"{out_prefix}_{i+1}.png"
        
        W, H = 1080, 1920  # 9:16 for Reels
        colors = color_schemes[i % len(color_schemes)]
        bg_top, bg_bottom, accent, glow = colors
        
        # Create gradient background
        img = Image.new("RGB", (W, H), bg_top)
        draw = ImageDraw.Draw(img)
        _vertical_gradient(draw, W, H, bg_top, bg_bottom)
        
        # Add a subtle glow effect (rounded rectangle in background)
        glow_margin = 60
        glow_rect = [glow_margin, 200, W - glow_margin, H - 200]
        draw.rounded_rectangle(
            glow_rect, 
            radius=40, 
            fill=(*bg_bottom, 120)  # Semi-transparent
        )
        
        try:
            f_main = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 100)
            f_sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 50)
            f_tool = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 35)
            f_label = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
        except:
            f_main = f_sub = f_tool = f_label = ImageFont.load_default()
        
        margin = 80
        
        # Tool name at top
        tool_name = reel_idea.get("tool_name", "AI Tool")
        _rounded_pill(draw, (margin, 80), f"⚡ {tool_name}", f_tool, (255, 255, 255), (0, 0, 0, 80))
        
        # Scene indicator
        scene_text = f"{i+1}/{len(scenes[:4])}"
        _rounded_pill(draw, (W - margin - 120, 80), scene_text, f_label, (255, 255, 255), (0, 0, 0, 60))
        
        # Main text - big and bold
        main_text = scene.get("text", "")
        y = 550
        for line in _wrap_limited(draw, main_text, f_main, W - margin * 2, 3):
            # Center align
            bbox = draw.textbbox((0, 0), line, font=f_main)
            text_width = bbox[2] - bbox[0]
            x = (W - text_width) // 2
            draw.text((x, y), line, font=f_main, fill=accent)
            y += 120
        
        y += 60
        
        # Subtext - smaller, with glow color
        sub_text = scene.get("subtext", "")
        if sub_text:
            for line in _wrap_limited(draw, sub_text, f_sub, W - margin * 2, 2):
                bbox = draw.textbbox((0, 0), line, font=f_sub)
                text_width = bbox[2] - bbox[0]
                x = (W - text_width) // 2
                draw.text((x, y), line, font=f_sub, fill=glow)
                y += 70
        
        # Call to action on last slide
        if i == len(scenes[:4]) - 1 and "call_to_action" in reel_idea:
            y = H - 300
            cta_text = reel_idea["call_to_action"]
            bbox = draw.textbbox((0, 0), cta_text, font=f_sub)
            text_width = bbox[2] - bbox[0]
            x = (W - text_width) // 2
            _rounded_pill(draw, (x - 40, y - 20), cta_text, f_sub, (255, 255, 255), (0, 0, 0, 80))
        
        # Bottom tag
        draw.text((margin, H - 100), "✨ Follow for daily AI tips", font=f_label, fill=(255, 255, 255))
        
        img.save(out_path)
        image_paths.append(out_path)
        print(f"✅ Reel scene {i+1} created: {out_path}")
    
    return image_paths

def save_for_github_hosting(image_path, content_type="single_image"):
    """
    Save images with content type subfolders.
    Organizes posts by type for better management.
    """
    # Create content type subfolder
    subfolder = content_type if content_type in ["carousel", "reel"] else "single"
    os.makedirs(f"posts/{subfolder}", exist_ok=True)
    
    filename = f"post_{int(time.time())}.png"
    dest_path = os.path.join("posts", subfolder, filename)
    with open(image_path, "rb") as src, open(dest_path, "wb") as dst:
        dst.write(src.read())

    raw_url = (
        f"https://raw.githubusercontent.com/{GITHUB_REPOSITORY}/"
        f"{GITHUB_REF_NAME}/{dest_path}"
    )
    return dest_path, raw_url


def send_telegram_preview(local_image_path, caption, hashtags, content_type="single_image", slide_count=0):
    """Send preview with content type indicator."""
    full_caption = f"{caption}\n\n{hashtags}"
    
    # Emoji and label for each content type
    type_labels = {
        "single_image": ("🖼️", "Single Image Post"),
        "carousel": ("📚", f"Carousel ({slide_count} slides)"),
        "reel": ("🎬", "Reel (Video)")
    }
    
    emoji, label = type_labels.get(content_type, ("🖼️", "Post"))
    
    text = (
        f"{emoji} *{label} Ready for Review*\n\n"
        f"{full_caption}\n\n"
        "Reply *APPROVE* to publish, or *SKIP* to discard."
    )
    with open(local_image_path, "rb") as f:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": text[:1024],
                "parse_mode": "Markdown",
            },
            files={"photo": f},
            timeout=30,
        )


def main():
    state = load_state()
    
    # Determine what to generate based on time of day
    content_type = get_next_content_type()
    
    # Get category (rotate through categories)
    category_index = state.get("category_index", 0)
    category = CATEGORIES[category_index % len(CATEGORIES)]
    
    print(f"🎯 Generating {content_type} post for category: {category}")
    print(f"📅 Date: {state.get('date', 'unknown')}")
    print(f"📊 Posts today: {state.get('posts_today', {})}")
    
    # Generate content based on type
    idea = call_gemini(category, content_type)
    
    if content_type == "single_image":
        # Single image generation
        print("🖼️ Creating single image...")
        image_path = make_image(idea)
        saved_path, image_url = save_for_github_hosting(image_path)
        
        draft = {
            "category": category,
            "tool_name": idea["tool_name"],
            "caption": idea["caption"],
            "hashtags": idea["hashtags"],
            "image_paths": [saved_path],
            "image_urls": [image_url],
            "is_carousel": False,
            "is_reel": False,
            "content_type": "single_image",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending",
        }
        send_telegram_preview(image_path, idea["caption"], idea["hashtags"], "single_image")
        
    elif content_type == "carousel":
        # Carousel generation
        print("📚 Creating carousel images...")
        image_paths = make_carousel_images(idea)
        saved_paths, image_urls = [], []
        for img_path in image_paths:
            saved_path, image_url = save_for_github_hosting(img_path)
            saved_paths.append(saved_path)
            image_urls.append(image_url)
        
        draft = {
            "category": category,
            "tool_name": idea["tool_name"],
            "caption": idea["caption"],
            "hashtags": idea["hashtags"],
            "image_paths": saved_paths,
            "image_urls": image_urls,
            "is_carousel": True,
            "is_reel": False,
            "content_type": "carousel",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending",
        }
        # Send first image as preview
        send_telegram_preview(image_paths[0], idea["caption"], idea["hashtags"], "carousel", len(image_paths))
        
    elif content_type == "reel":
        # Reel generation - create images for video
        print("🎬 Creating reel scenes...")
        image_paths = make_reel_images(idea)
        saved_paths, image_urls = [], []
        for img_path in image_paths:
            saved_path, image_url = save_for_github_hosting(img_path)
            saved_paths.append(saved_path)
            image_urls.append(image_url)
        
        draft = {
            "category": category,
            "tool_name": idea["tool_name"],
            "caption": idea["caption"],
            "hashtags": idea["hashtags"],
            "image_paths": saved_paths,
            "image_urls": image_urls,
            "text_overlays": idea.get("text_overlays", []),
            "is_carousel": False,
            "is_reel": True,
            "content_type": "reel",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending",
        }
        send_telegram_preview(image_paths[0], idea["caption"], idea["hashtags"], "reel")
    
    # Load existing drafts or create new list
    if os.path.exists(DRAFTS_FILE):
        try:
            with open(DRAFTS_FILE, "r") as f:
                existing_drafts = json.load(f)
                if isinstance(existing_drafts, dict):
                    existing_drafts = [existing_drafts]
                elif not isinstance(existing_drafts, list):
                    existing_drafts = []
        except (json.JSONDecodeError, FileNotFoundError):
            existing_drafts = []
    else:
        existing_drafts = []

    # Append new draft
    existing_drafts.append(draft)
    
    # Save as list with atomic write
    save_json_atomic(existing_drafts, DRAFTS_FILE)
    
    # Update state
    state["category_index"] = (category_index + 1) % len(CATEGORIES)
    state["posts_today"][content_type] = state["posts_today"].get(content_type, 0) + 1
    state["last_post_time"] = datetime.now().isoformat()
    state["content_type_counter"] = state.get("content_type_counter", 0) + 1
    state["total_generated"] = state.get("total_generated", 0) + 1
    save_state(state)
    
    print(f"✅ {content_type} draft created and sent for review!")
    print(f"📊 Updated state: {state}")

if __name__ == "__main__":
    main()