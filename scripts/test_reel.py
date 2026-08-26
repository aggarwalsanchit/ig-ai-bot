"""
Test script for Reel Video Post
Run: python test_reel.py
"""
import os
import json
import sys
import time

# Add the scripts directory to path
sys.path.insert(0, os.path.dirname(__file__))

# Import from generate_and_notify
from generate_and_notify import (
    call_gemini, make_reel_images, create_reel_video, save_for_github_hosting,
    CATEGORIES, GITHUB_REPOSITORY, GITHUB_REF_NAME,
    TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
)
import requests

# Check for required environment variables
if not os.environ.get("GEMINI_API_KEY"):
    print("⚠️  GEMINI_API_KEY not set in environment!")
    print("💡 For local testing, run: export GEMINI_API_KEY='your-key'")
    sys.exit(1)

def send_telegram_reel(video_path, caption):
    """Send a video (reel) to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram credentials not set - skipping Telegram notification")
        return
    
    if not os.path.exists(video_path):
        print(f"⚠️ Video not found: {video_path}")
        return
    
    try:
        with open(video_path, "rb") as f:
            resp = requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendVideo",
                data={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "caption": caption[:1024],
                    "parse_mode": "Markdown",
                    "supports_streaming": True,
                },
                files={"video": f},
                timeout=60,
            )
            if resp.ok:
                print("✅ Reel video sent to Telegram! (It should play inline)")
            else:
                print(f"⚠️ Telegram send failed: {resp.text}")
    except Exception as e:
        print(f"⚠️ Could not send to Telegram: {e}")

def test_reel():
    print("="*60)
    print("🧪 TESTING: REEL VIDEO POST")
    print("="*60)
    
    # Get category from env or use default
    category = os.environ.get("TEST_CATEGORY", CATEGORIES[2])
    
    print(f"📂 Category: {category}")
    print("🤖 Calling Gemini for reel script...")
    
    try:
        # Generate content
        idea = call_gemini(category, "reel")
        print(f"✅ Tool: {idea['tool_name']}")
        print(f"📝 Hook: {idea.get('hook', 'N/A')}")
        
        # Generate reel scene images
        print("🎬 Creating 4 reel scenes...")
        image_paths = make_reel_images(idea, "test_reel_scene")
        
        print(f"✅ Created {len(image_paths)} scenes")
        for i, path in enumerate(image_paths):
            print(f"   Scene {i+1}: {path}")
        
        # Create video from images
        print("🎬 Creating video with ffmpeg...")
        video_path = create_reel_video(image_paths, "test_reel_video.mp4")
        
        if video_path and os.path.exists(video_path):
            file_size = os.path.getsize(video_path) / (1024 * 1024)
            print(f"✅ Video created: {video_path} ({file_size:.1f} MB)")
        else:
            print("❌ Video creation failed - ffmpeg might not be installed")
            print("💡 Install ffmpeg: sudo apt-get install ffmpeg")
            video_path = None
        
        # Save images to GitHub
        saved_paths, image_urls = [], []
        for img_path in image_paths:
            saved_path, image_url = save_for_github_hosting(img_path, "reel")
            saved_paths.append(saved_path)
            image_urls.append(image_url)
        
        print("✅ All images saved to GitHub")
        
        # Save video to GitHub if it exists
        video_dest = None
        video_url = None
        if video_path and os.path.exists(video_path):
            os.makedirs("posts/reel", exist_ok=True)
            video_filename = f"test_reel_{int(time.time())}.mp4"
            video_dest = os.path.join("posts/reel", video_filename)
            with open(video_path, "rb") as src, open(video_dest, "wb") as dst:
                dst.write(src.read())
            video_url = f"https://raw.githubusercontent.com/{GITHUB_REPOSITORY}/{GITHUB_REF_NAME}/{video_dest}"
            os.remove(video_path)  # Clean up temp video
            print(f"✅ Video saved: {video_dest}")
            print(f"🔗 Video URL: {video_url}")
        else:
            print("⚠️ No video to save")
        
        # Create draft
        draft = {
            "category": category,
            "tool_name": idea["tool_name"],
            "caption": idea["caption"],
            "hashtags": idea["hashtags"],
            "image_paths": saved_paths,
            "image_urls": image_urls,
            "video_path": video_dest,
            "video_url": video_url,
            "text_overlays": idea.get("text_overlays", []),
            "is_carousel": False,
            "is_reel": True,
            "content_type": "reel",
            "created_at": "2026-08-26T12:00:00+00:00",
            "status": "pending",
        }
        
        # Save draft for inspection
        with open("test_reel_draft.json", "w") as f:
            json.dump(draft, f, indent=2)
        
        # Send to Telegram
        if video_dest and os.path.exists(video_dest):
            caption_text = f"""🎬 *REEL TEST*

📌 *Tool:* {idea['tool_name']}
📝 *Hook:* {idea.get('hook', 'N/A')}

{idea['caption']}

{idea['hashtags']}

---
✅ Test completed successfully!
📄 Draft saved to: test_reel_draft.json
🎬 Video should play inline!"""
            
            send_telegram_reel(video_dest, caption_text)
        else:
            print("⚠️ No video to send to Telegram")
        
        print("="*60)
        print("✅ TEST COMPLETE")
        print("📄 Draft saved to: test_reel_draft.json")
        print("="*60)
        
        return 0
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(test_reel())