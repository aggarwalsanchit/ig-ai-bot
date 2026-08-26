"""
Test script for Single Image Post
Run: python test_single_image.py
"""
import os
import json
import sys
import time

# Add the scripts directory to path
sys.path.insert(0, os.path.dirname(__file__))

# Import from generate_and_notify
from generate_and_notify import (
    call_gemini, make_image, save_for_github_hosting, 
    CATEGORIES, GITHUB_REPOSITORY, GITHUB_REF_NAME,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
)
import requests

# Check for required environment variables
if not os.environ.get("GEMINI_API_KEY"):
    print("⚠️  GEMINI_API_KEY not set in environment!")
    print("💡 For local testing, run: export GEMINI_API_KEY='your-key'")
    sys.exit(1)

def send_telegram_photo(image_path, caption):
    """Send a single photo to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram credentials not set - skipping Telegram notification")
        return
    
    try:
        with open(image_path, "rb") as f:
            resp = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
                data={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "caption": caption[:1024],
                    "parse_mode": "Markdown",
                },
                files={"photo": f},
                timeout=30,
            )
            if resp.ok:
                print("✅ Telegram preview sent!")
            else:
                print(f"⚠️ Telegram send failed: {resp.text}")
    except Exception as e:
        print(f"⚠️ Could not send to Telegram: {e}")

def test_single_image():
    print("="*60)
    print("🧪 TESTING: SINGLE IMAGE POST")
    print("="*60)
    
    # Get category from env or use default
    category = os.environ.get("TEST_CATEGORY", CATEGORIES[0])
    
    print(f"📂 Category: {category}")
    print("🤖 Calling Gemini for content...")
    
    try:
        # Generate content
        idea = call_gemini(category, "single_image")
        print(f"✅ Tool: {idea['tool_name']}")
        print(f"📝 Headline: {idea['headline']}")
        
        # Generate image
        print("🖼️ Creating image...")
        image_path = make_image(idea, "test_single_image.png")
        
        # Save to GitHub hosting
        saved_path, image_url = save_for_github_hosting(image_path, "single_image")
        print(f"✅ Image saved: {saved_path}")
        print(f"🔗 URL: {image_url}")
        
        # Create draft
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
            "created_at": "2026-08-26T12:00:00+00:00",
            "status": "pending",
        }
        
        # Save draft for inspection
        with open("test_single_image_draft.json", "w") as f:
            json.dump(draft, f, indent=2)
        
        # Send to Telegram
        caption_text = f"""🖼️ *SINGLE IMAGE TEST*

📌 *Tool:* {idea['tool_name']}
📝 *Headline:* {idea['headline']}

{idea['caption']}

{idea['hashtags']}

---
✅ Test completed successfully!
📄 Draft saved to: test_single_image_draft.json"""
        
        send_telegram_photo(image_path, caption_text)
        
        print("="*60)
        print("✅ TEST COMPLETE")
        print("📄 Draft saved to: test_single_image_draft.json")
        print("="*60)
        
        return 0
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(test_single_image())