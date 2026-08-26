"""
Test script for Single Image Post
Run: python test_single_image.py
"""
import os
import json
import sys

# Add the scripts directory to path so we can import from generate_and_notify
sys.path.append(os.path.join(os.path.dirname(__file__), 'scripts'))

# Import from generate_and_notify
from generate_and_notify import (
    call_gemini, make_image, save_for_github_hosting, 
    send_telegram_preview, save_json_atomic, load_state, save_state,
    CATEGORIES, GITHUB_REPOSITORY, GITHUB_REF_NAME
)

# Set environment variables (you can hardcode or use .env)
os.environ["GEMINI_API_KEY"] = "your-gemini-key-here"
os.environ["TELEGRAM_BOT_TOKEN"] = "your-telegram-token-here"
os.environ["TELEGRAM_CHAT_ID"] = "your-chat-id-here"
os.environ["GITHUB_REPOSITORY"] = "yourusername/your-repo"
os.environ["GITHUB_REF_NAME"] = "main"

def test_single_image():
    print("="*60)
    print("🧪 TESTING: SINGLE IMAGE POST")
    print("="*60)
    
    # Use first category for testing
    category = CATEGORIES[0]  # "writing & content creation"
    
    print(f"📂 Category: {category}")
    print("🤖 Calling Gemini for content...")
    
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
    
    # Send to Telegram (optional - comment out if you don't want to send)
    # send_telegram_preview(image_path, idea["caption"], idea["hashtags"], "single_image")
    
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
    
    print("="*60)
    print("✅ TEST COMPLETE")
    print("📄 Draft:")
    print(json.dumps(draft, indent=2))
    print("="*60)

if __name__ == "__main__":
    test_single_image()