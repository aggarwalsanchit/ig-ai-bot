"""
Test script for Carousel Post
Run: python test_carousel.py
"""
import os
import json
import sys
import time

# Add the scripts directory to path
sys.path.insert(0, os.path.dirname(__file__))

# Import from generate_and_notify
from generate_and_notify import (
    call_gemini, make_carousel_images, save_for_github_hosting, 
    CATEGORIES, GITHUB_REPOSITORY, GITHUB_REF_NAME,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
)
import requests

# Check for required environment variables
if not os.environ.get("GEMINI_API_KEY"):
    print("⚠️  GEMINI_API_KEY not set in environment!")
    print("💡 For local testing, run: export GEMINI_API_KEY='your-key'")
    sys.exit(1)

def send_telegram_carousel(image_paths, caption):
    """Send all carousel images to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram credentials not set - skipping Telegram notification")
        return
    
    try:
        # Send first image with caption
        with open(image_paths[0], "rb") as f:
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
                print("✅ First slide sent to Telegram!")
            else:
                print(f"⚠️ Telegram send failed: {resp.text}")
        
        # Send remaining images as separate messages (no caption)
        for i, img_path in enumerate(image_paths[1:], start=2):
            time.sleep(0.5)  # Small delay to avoid rate limiting
            with open(img_path, "rb") as f:
                resp = requests.post(
                    f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto",
                    data={
                        "chat_id": TELEGRAM_CHAT_ID,
                        "caption": f"📄 *Slide {i}/{len(image_paths)}*",
                        "parse_mode": "Markdown",
                    },
                    files={"photo": f},
                    timeout=30,
                )
                if resp.ok:
                    print(f"✅ Slide {i} sent to Telegram!")
                else:
                    print(f"⚠️ Slide {i} send failed: {resp.text}")
                    
    except Exception as e:
        print(f"⚠️ Could not send to Telegram: {e}")

def test_carousel():
    print("="*60)
    print("🧪 TESTING: CAROUSEL POST (5 slides)")
    print("="*60)
    
    # Get category from env or use default
    category = os.environ.get("TEST_CATEGORY", CATEGORIES[1])
    
    print(f"📂 Category: {category}")
    print("🤖 Calling Gemini for carousel content...")
    
    try:
        # Generate content
        idea = call_gemini(category, "carousel")
        print(f"✅ Tool: {idea['tool_name']}")
        
        # Generate carousel images
        print("📚 Creating 5 carousel slides...")
        image_paths = make_carousel_images(idea, "test_carousel")
        
        print(f"✅ Created {len(image_paths)} slides")
        for i, path in enumerate(image_paths):
            print(f"   Slide {i+1}: {path}")
        
        # Save to GitHub hosting
        saved_paths, image_urls = [], []
        for img_path in image_paths:
            saved_path, image_url = save_for_github_hosting(img_path, "carousel")
            saved_paths.append(saved_path)
            image_urls.append(image_url)
        
        print("✅ All images saved to GitHub")
        
        # Create draft
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
            "created_at": "2026-08-26T12:00:00+00:00",
            "status": "pending",
        }
        
        # Save draft for inspection
        with open("test_carousel_draft.json", "w") as f:
            json.dump(draft, f, indent=2)
        
        # Send to Telegram
        caption_text = f"""📚 *CAROUSEL TEST - {len(image_paths)} SLIDES*

📌 *Tool:* {idea['tool_name']}

{idea['caption']}

{idea['hashtags']}

---
✅ Test completed successfully!
📄 Draft saved to: test_carousel_draft.json"""
        
        send_telegram_carousel(image_paths, caption_text)
        
        print("="*60)
        print("✅ TEST COMPLETE")
        print("📄 Draft saved to: test_carousel_draft.json")
        print("="*60)
        
        return 0
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(test_carousel())