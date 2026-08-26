"""
Test script for Carousel Post
Run: python test_carousel.py
"""
import os
import json
import sys

# Add the scripts directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'scripts'))

# Import from generate_and_notify
from generate_and_notify import (
    call_gemini, make_carousel_images, save_for_github_hosting, 
    send_telegram_preview, save_json_atomic,
    CATEGORIES, GITHUB_REPOSITORY, GITHUB_REF_NAME
)

# Set environment variables
os.environ["GEMINI_API_KEY"] = "your-gemini-key-here"
os.environ["TELEGRAM_BOT_TOKEN"] = "your-telegram-token-here"
os.environ["TELEGRAM_CHAT_ID"] = "your-chat-id-here"
os.environ["GITHUB_REPOSITORY"] = "yourusername/your-repo"
os.environ["GITHUB_REF_NAME"] = "main"

def test_carousel():
    print("="*60)
    print("🧪 TESTING: CAROUSEL POST (5 slides)")
    print("="*60)
    
    # Use category
    category = CATEGORIES[1]  # "coding & debugging"
    
    print(f"📂 Category: {category}")
    print("🤖 Calling Gemini for carousel content...")
    
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
    
    # Send to Telegram (optional)
    # send_telegram_preview(image_paths[0], idea["caption"], idea["hashtags"], "carousel", len(image_paths))
    
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
    
    print("="*60)
    print("✅ TEST COMPLETE")
    print("📄 Draft:")
    print(json.dumps(draft, indent=2))
    print("="*60)

if __name__ == "__main__":
    test_carousel()