"""
Test script for Reel Video Post
Run: python test_reel.py
"""
import os
import json
import sys

# Add the scripts directory to path
sys.path.insert(0, os.path.dirname(__file__))

# Import from generate_and_notify
from generate_and_notify import (
    call_gemini, make_reel_images, create_reel_video, save_for_github_hosting,
    send_telegram_preview, save_json_atomic,
    CATEGORIES, GITHUB_REPOSITORY, GITHUB_REF_NAME
)

# Set environment variables
os.environ["GEMINI_API_KEY"] = "your-gemini-key-here"
os.environ["TELEGRAM_BOT_TOKEN"] = "your-telegram-token-here"
os.environ["TELEGRAM_CHAT_ID"] = "your-chat-id-here"
os.environ["GITHUB_REPOSITORY"] = "yourusername/your-repo"
os.environ["GITHUB_REF_NAME"] = "main"

def test_reel():
    print("="*60)
    print("🧪 TESTING: REEL VIDEO POST")
    print("="*60)
    
    # Use category
    category = CATEGORIES[2]  # "research & summarizing information"
    
    print(f"📂 Category: {category}")
    print("🤖 Calling Gemini for reel script...")
    
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
    
    # Save images to GitHub
    saved_paths, image_urls = [], []
    for img_path in image_paths:
        saved_path, image_url = save_for_github_hosting(img_path, "reel")
        saved_paths.append(saved_path)
        image_urls.append(image_url)
    
    print("✅ All images saved to GitHub")
    
    # Save video to GitHub if it exists
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
        video_dest = None
        video_url = None
    
    # Send to Telegram (optional)
    # send_telegram_preview(image_paths[0], idea["caption"], idea["hashtags"], "reel")
    
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
    
    print("="*60)
    print("✅ TEST COMPLETE")
    print("📄 Draft:")
    print(json.dumps(draft, indent=2))
    print("="*60)

if __name__ == "__main__":
    test_reel()