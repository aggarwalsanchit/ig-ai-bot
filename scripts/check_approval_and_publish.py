"""
Polls Telegram for your APPROVE / SKIP reply. Each reply acts on the
OLDEST pending draft in the queue (so twice-daily generation doesn't
overwrite anything — drafts just queue up until you respond).
If approved, publishes that post to Instagram, and to your linked
Facebook Page too if FB_PAGE_ID / FB_PAGE_ACCESS_TOKEN are configured.

Run by: .github/workflows/publish.yml (every ~20 minutes)
"""
import os
import json
import time
import requests
import subprocess
from datetime import datetime

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
IG_USER_ID = os.environ.get("IG_USER_ID")
IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN")
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
FB_PAGE_ACCESS_TOKEN = os.environ.get("FB_PAGE_ACCESS_TOKEN")

# Debug - check if Facebook variables are loaded
print(f"FB_PAGE_ID present: {'Yes' if FB_PAGE_ID else 'No'}")
print(f"FB_PAGE_ACCESS_TOKEN present: {'Yes' if FB_PAGE_ACCESS_TOKEN else 'No'}")
if FB_PAGE_ID:
    print(f"FB_PAGE_ID length: {len(FB_PAGE_ID)}")
if FB_PAGE_ACCESS_TOKEN:
    print(f"FB_PAGE_ACCESS_TOKEN starts with: {FB_PAGE_ACCESS_TOKEN[:10]}...")

STATE_FILE = "state.json"
DRAFTS_FILE = "drafts.json"


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            try:
                state = json.load(f)
                # Add missing fields if needed
                if "failed_attempts" not in state:
                    state["failed_attempts"] = 0
                if "last_skip_time" not in state:
                    state["last_skip_time"] = None
                if "total_generated" not in state:
                    state["total_generated"] = 0
                if "total_published" not in state:
                    state["total_published"] = 0
                if "total_skipped" not in state:
                    state["total_skipped"] = 0
                return state
            except json.JSONDecodeError:
                print(f"Warning: {STATE_FILE} is corrupted. Resetting.")
                return {
                    "category_index": 0, 
                    "telegram_offset": 0,
                    "failed_attempts": 0,
                    "total_generated": 0,
                    "total_published": 0,
                    "total_skipped": 0
                }
    return {
        "category_index": 0, 
        "telegram_offset": 0,
        "failed_attempts": 0,
        "total_generated": 0,
        "total_published": 0,
        "total_skipped": 0
    }


def save_json_atomic(data, filename):
    """Save JSON data atomically to prevent corruption."""
    temp_file = f"{filename}.tmp"
    with open(temp_file, "w") as f:
        json.dump(data, f, indent=2)
    os.replace(temp_file, filename)


def save_state(state):
    save_json_atomic(state, STATE_FILE)


def load_drafts():
    """Load drafts with support for both list and single-object formats."""
    if not os.path.exists(DRAFTS_FILE):
        return []
    
    try:
        with open(DRAFTS_FILE) as f:
            data = json.load(f)
        
        # Handle single object format (backward compatibility)
        if isinstance(data, dict):
            print("Info: Converting single draft object to list format")
            return [data]
        
        # Handle list format
        if isinstance(data, list):
            # Filter out non-dict items
            valid_drafts = [item for item in data if isinstance(item, dict)]
            if len(valid_drafts) != len(data):
                print(f"Warning: Removed {len(data) - len(valid_drafts)} invalid items from drafts")
            return valid_drafts
        
        print(f"Error: {DRAFTS_FILE} contains invalid data type: {type(data)}. Resetting.")
        backup_corrupted_file()
        return []
    
    except json.JSONDecodeError as e:
        print(f"Error: {DRAFTS_FILE} is corrupted ({e}). Resetting.")
        backup_corrupted_file()
        return []
    except Exception as e:
        print(f"Unexpected error loading drafts: {e}")
        return []


def backup_corrupted_file(filename=DRAFTS_FILE):
    """Create a backup of corrupted file before resetting."""
    if os.path.exists(filename):
        backup_name = f"{filename}.corrupted_{int(time.time())}.bak"
        try:
            os.rename(filename, backup_name)
            print(f"Backed up corrupted file to {backup_name}")
        except Exception as e:
            print(f"Could not backup corrupted file: {e}")


def save_drafts(drafts):
    """Save drafts with validation."""
    if not isinstance(drafts, list):
        print(f"Error: Attempted to save non-list to {DRAFTS_FILE}")
        return
    
    # Ensure all items are dictionaries
    valid_drafts = [d for d in drafts if isinstance(d, dict)]
    save_json_atomic(valid_drafts, DRAFTS_FILE)

def generate_new_draft(content_type=None):
    """Trigger the generation script to create a new draft."""
    print("🔄 Generating a new draft to replace the skipped one...")
    
    try:
        # Run the generation script
        result = subprocess.run(
            ["python", "scripts/generate_and_notify.py"],
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode == 0:
            print("✅ New draft generated successfully!")
            # Print first 500 chars of output for debugging
            if result.stdout:
                print(f"Output: {result.stdout[:500]}")
            return True
        else:
            print(f"❌ Generation failed with error code: {result.returncode}")
            if result.stderr:
                print(f"Error: {result.stderr[:500]}")
            return False
            
    except subprocess.TimeoutExpired:
        print("❌ Generation timed out after 120 seconds")
        return False
    except FileNotFoundError:
        print("❌ Could not find generate_and_notify.py script")
        return False
    except Exception as e:
        print(f"❌ Failed to run generation script: {e}")
        return False


def get_telegram_replies(offset):
    if not TELEGRAM_BOT_TOKEN:
        print("Error: TELEGRAM_BOT_TOKEN not set")
        return []
    
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
            params={"offset": offset, "timeout": 5},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()["result"]
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Telegram updates: {e}")
        return []


def notify(text):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Error: Telegram credentials not set")
        return
    
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            data={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=15,
        )
    except requests.exceptions.RequestException as e:
        print(f"Error sending Telegram notification: {e}")


def publish_to_instagram(image_url, caption, hashtags):
    if not IG_USER_ID or not IG_ACCESS_TOKEN:
        print("Error: Instagram credentials not set")
        return None
    
    full_caption = f"{caption}\n\n{hashtags}"
    
    print(f"📸 Publishing to Instagram...")
    print(f"Image URL: {image_url[:80]}...")
    print(f"Caption length: {len(full_caption)} chars")
    
    # First, create the media container
    try:
        create_resp = requests.post(
            f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media",
            data={
                "image_url": image_url,
                "caption": full_caption,
                "access_token": IG_ACCESS_TOKEN,
            },
            timeout=30,
        )
        
        # Log the response for debugging
        print(f"Create media response status: {create_resp.status_code}")
        print(f"Create media response: {create_resp.text[:200]}")
        
        if not create_resp.ok:
            error_data = create_resp.json() if create_resp.text else {}
            error_msg = error_data.get("error", {}).get("message", "Unknown error")
            error_code = error_data.get("error", {}).get("code", "N/A")
            
            print(f"❌ Instagram media creation failed:")
            print(f"  - Error Code: {error_code}")
            print(f"  - Error Message: {error_msg}")
            
            # Check for common errors
            if "access_token" in error_msg.lower():
                print("  💡 Your Instagram access token may be expired or invalid!")
                print("  💡 Generate a new token from the Facebook Developer Console")
            elif "image_url" in error_msg.lower():
                print("  💡 The image URL is not accessible or invalid!")
                print(f"  💡 URL: {image_url}")
            elif "permission" in error_msg.lower():
                print("  💡 Missing required permissions!")
                print("  💡 Need: instagram_basic, instagram_content_publish")
            
            return None
        
        create_resp.raise_for_status()
        creation_id = create_resp.json()["id"]
        print(f"✅ Media container created with ID: {creation_id}")
        
    except requests.exceptions.RequestException as e:
        print(f"❌ Instagram media creation request failed: {e}")
        if hasattr(e, 'response') and e.response:
            print(f"Response: {e.response.text[:500]}")
        return None

    # Wait for media to process
    print("⏳ Waiting 15 seconds for media to process...")
    time.sleep(15)

    # Retry logic for media publishing with longer waits
    for attempt in range(10):
        try:
            publish_resp = requests.post(
                f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish",
                data={
                    "creation_id": creation_id,
                    "access_token": IG_ACCESS_TOKEN,
                },
                timeout=30,
            )
            
            if publish_resp.ok:
                print("✅ Successfully published to Instagram!")
                return publish_resp.json()

            error_text = publish_resp.text.lower()
            print(f"Instagram publish failed (attempt {attempt + 1}/10)")
            print(f"Status: {publish_resp.status_code}")
            print(f"Response: {publish_resp.text[:200]}")
            
            # If media isn't ready, wait longer and retry
            if "not ready" in error_text or "media id is not available" in error_text:
                wait_time = 15 + (attempt * 5)  # 15, 20, 25, 30, 35... seconds
                print(f"⏳ Media not ready yet. Waiting {wait_time} seconds...")
                time.sleep(wait_time)
                continue
            else:
                # Other error, break out of retry loop
                print(f"❌ Permanent error occurred: {publish_resp.text}")
                break
                
        except requests.exceptions.RequestException as e:
            print(f"Instagram publish attempt {attempt + 1} failed: {e}")
            time.sleep(10)
            continue

    print("❌ Failed to publish after all attempts")
    return None

def publish_instagram_carousel(image_urls, caption):
    """Publish a carousel post with multiple images."""
    if len(image_urls) < 2:
        print("Carousel needs at least 2 images")
        return None
    
    print(f"📸 Creating carousel with {len(image_urls)} images...")
    
    # Step 1: Create media containers for each image
    media_ids = []
    for i, image_url in enumerate(image_urls):
        try:
            print(f"Creating container {i+1}/{len(image_urls)}...")
            create_resp = requests.post(
                f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media",
                data={
                    "image_url": image_url,
                    "access_token": IG_ACCESS_TOKEN,
                    "is_carousel_item": True,
                },
                timeout=30,
            )
            
            if not create_resp.ok:
                print(f"❌ Failed to create media {i+1}: {create_resp.text}")
                return None
                
            media_id = create_resp.json()["id"]
            media_ids.append(media_id)
            print(f"✅ Container {i+1} created: {media_id}")
            
            if i < len(image_urls) - 1:
                time.sleep(2)
                
        except requests.exceptions.RequestException as e:
            print(f"❌ Error creating media {i+1}: {e}")
            return None

    print(f"✅ All {len(media_ids)} containers created")
    print("⏳ Waiting 15 seconds for media to process...")
    time.sleep(15)

    # Step 2: Create carousel container
    try:
        carousel_data = {
            "media_type": "CAROUSEL",
            "children": ",".join(media_ids),
            "caption": caption,
            "access_token": IG_ACCESS_TOKEN,
        }
        
        print("Creating carousel container...")
        carousel_resp = requests.post(
            f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media",
            data=carousel_data,
            timeout=30,
        )
        
        if not carousel_resp.ok:
            print(f"❌ Carousel creation failed: {carousel_resp.text}")
            return None
            
        carousel_id = carousel_resp.json()["id"]
        print(f"✅ Carousel container created: {carousel_id}")
        
        # Step 3: Publish the carousel
        print("Publishing carousel...")
        publish_resp = requests.post(
            f"https://graph.facebook.com/v19.0/{IG_USER_ID}/media_publish",
            data={
                "creation_id": carousel_id,
                "access_token": IG_ACCESS_TOKEN,
            },
            timeout=30,
        )
        
        if publish_resp.ok:
            print("✅ Carousel published to Instagram!")
            return publish_resp.json()
        else:
            print(f"❌ Carousel publish failed: {publish_resp.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Carousel publish error: {e}")
        return None


def publish_to_facebook(image_url, caption, hashtags):
    """Post the same image + caption to the linked Facebook Page."""
    if not FB_PAGE_ID or not FB_PAGE_ACCESS_TOKEN:
        print("⚠️ Facebook not configured - missing credentials")
        return None

    print(f"📘 Attempting to publish to Facebook Page: {FB_PAGE_ID}")
    print(f"   Token starts with: {FB_PAGE_ACCESS_TOKEN[:15]}...")
    
    full_caption = f"{caption}\n\n{hashtags}"
    
    try:
        # First, try to get page info to verify token works
        verify_url = f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}?access_token={FB_PAGE_ACCESS_TOKEN}"
        verify_resp = requests.get(verify_url, timeout=10)
        if verify_resp.ok:
            page_data = verify_resp.json()
            print(f"✅ Facebook Page verified: {page_data.get('name', 'Unknown')}")
        else:
            print(f"⚠️ Could not verify Facebook Page: {verify_resp.status_code}")
            print(f"Response: {verify_resp.text[:200]}")
            if "access_token" in verify_resp.text.lower():
                print("❌ Facebook access token is invalid or expired!")
                return None
        
        # Now publish the photo
        resp = requests.post(
            f"https://graph.facebook.com/v19.0/{FB_PAGE_ID}/photos",
            data={
                "url": image_url,
                "caption": full_caption,
                "access_token": FB_PAGE_ACCESS_TOKEN,
            },
            timeout=30,
        )
        
        if resp.ok:
            result = resp.json()
            print(f"✅ Published to Facebook successfully! Post ID: {result.get('id', 'unknown')}")
            return result
        else:
            error_msg = "Unknown error"
            error_code = "N/A"
            try:
                error_data = resp.json()
                error_msg = error_data.get("error", {}).get("message", "Unknown error")
                error_code = error_data.get("error", {}).get("code", "N/A")
            except:
                pass
            
            print(f"❌ Facebook publish failed:")
            print(f"   Status: {resp.status_code}")
            print(f"   Error Code: {error_code}")
            print(f"   Error Message: {error_msg}")
            print(f"   Full Response: {resp.text[:300]}")
            
            # Common Facebook errors
            if resp.status_code == 403:
                print("   💡 Permission denied. Make sure your token has 'pages_manage_posts' scope")
            elif resp.status_code == 400:
                if "image_url" in resp.text.lower():
                    print("   💡 The image URL might not be accessible to Facebook")
                elif "caption" in resp.text.lower():
                    print("   💡 The caption might be too long or contain invalid characters")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Facebook publish error: {e}")
        return None


def cleanup_draft_image(draft):
    """Remove all local image files after publishing/skipping."""
    paths = draft.get("image_paths", [])
    if not paths and "image_path" in draft:
        paths = [draft["image_path"]]
    
    for path in paths:
        if path and os.path.exists(path):
            try:
                os.remove(path)
                print(f"Cleaned up image: {path}")
            except Exception as e:
                print(f"Could not remove image file {path}: {e}")


def validate_and_fix_draft(draft):
    """Ensure a draft has all required fields."""
    # Handle both old and new format
    if "image_url" not in draft and "image_urls" not in draft:
        print(f"Warning: Draft missing image_url or image_urls")
        return False
    
    if "caption" not in draft or "hashtags" not in draft or "status" not in draft:
        print(f"Warning: Draft missing required fields")
        return False
    
    # Handle old format (single image)
    if "image_url" in draft and "image_urls" not in draft:
        draft["image_urls"] = [draft["image_url"]]
        draft["image_paths"] = [draft.get("image_path", "")]
    
    if "is_carousel" not in draft:
        draft["is_carousel"] = False
    if "is_reel" not in draft:
        draft["is_reel"] = False
    if "content_type" not in draft:
        draft["content_type"] = "single_image"
    
    return True


def main():
    # Check required environment variables
    required_vars = {
        "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
        "IG_USER_ID": IG_USER_ID,
        "IG_ACCESS_TOKEN": IG_ACCESS_TOKEN,
    }
    
    # Check optional Facebook
    if FB_PAGE_ID and FB_PAGE_ACCESS_TOKEN:
        print("✅ Facebook publishing is configured")
    else:
        print("ℹ️ Facebook publishing is not configured (skipping)")
    
    missing_vars = [name for name, value in required_vars.items() if not value]
    if missing_vars:
        print(f"Error: Missing required environment variables: {', '.join(missing_vars)}")
        return
    
    # Load drafts with validation
    drafts = load_drafts()
    
    if not drafts:
        print("No drafts found")
        return
    
    # Filter pending drafts
    pending = [d for d in drafts if isinstance(d, dict) and d.get("status") == "pending"]
    
    if not pending:
        print("No pending drafts")
        return
    
    print(f"Found {len(pending)} pending drafts")

    # Get state and check for replies
    state = load_state()
    updates = get_telegram_replies(state.get("telegram_offset", 0))

    if not updates:
        print("No Telegram updates found")
        return

    decision = None
    max_update_id = state.get("telegram_offset", 0)

    for update in updates:
        max_update_id = max(max_update_id, update["update_id"] + 1)
        msg = update.get("message", {})
        text = msg.get("text", "").strip().upper()
        
        if str(msg.get("chat", {}).get("id")) != str(TELEGRAM_CHAT_ID):
            continue
            
        if "APPROVE" in text:
            decision = "approve"
            break
        elif "SKIP" in text:
            decision = "skip"
            break

    state["telegram_offset"] = max_update_id
    save_state(state)

    if decision is None:
        print("No APPROVE or SKIP reply found")
        return

    # Process the oldest pending draft
    oldest = pending[0]
    
    # Validate the draft before processing
    if not validate_and_fix_draft(oldest):
        print("Invalid draft, marking as error")
        oldest["status"] = "error"
        save_drafts(drafts)
        notify("❌ Invalid draft detected and marked as error.")
        return

    if decision == "approve":
        print(f"✅ Approving draft: {oldest.get('tool_name', 'Unknown')}")
        print(f"📊 Content type: {oldest.get('content_type', 'unknown')}")
        
        # Get image URLs (support both old and new format)
        image_urls = oldest.get("image_urls", [])
        if not image_urls and "image_url" in oldest:
            image_urls = [oldest["image_url"]]
        
        is_carousel = oldest.get("is_carousel", False)
        
        # Publish to Instagram
        if is_carousel and len(image_urls) > 1:
            ig_result = publish_instagram_carousel(image_urls, f"{oldest['caption']}\n\n{oldest['hashtags']}")
        else:
            ig_result = publish_to_instagram(
                image_urls[0] if image_urls else oldest.get("image_url", ""),
                oldest["caption"], 
                oldest["hashtags"]
            )
        
        if ig_result:
            oldest["status"] = "published"
            state["total_published"] = state.get("total_published", 0) + 1
            save_state(state)
            msg = f"✅ Published to Instagram! Media ID: {ig_result.get('id', 'unknown')}"
            
            # Try Facebook publishing (uses first image)
            print("\n" + "="*50)
            print("ATTEMPTING FACEBOOK PUBLISH")
            print("="*50)
            
            try:
                fb_result = publish_to_facebook(
                    image_urls[0] if image_urls else oldest.get("image_url", ""),
                    oldest["caption"], 
                    oldest["hashtags"]
                )
                if fb_result:
                    msg += f"\n✅ Published to Facebook! Post ID: {fb_result.get('id', 'unknown')}"
                else:
                    msg += "\n⚠️ Facebook publish failed (Instagram still succeeded)"
            except Exception as e:
                print(f"Exception during Facebook publish: {e}")
                msg += f"\n⚠️ Facebook publish error (Instagram still succeeded): {e}"
                
            # Note: Threads would go here if configured
                
        else:
            oldest["status"] = "publish_failed"
            msg = "❌ Instagram publish failed. Please check logs above."
        
        notify(msg)
        cleanup_draft_image(oldest)
        
    elif decision == "skip":
        print(f"🗑️ Skipping draft: {oldest.get('tool_name', 'Unknown')}")
        print(f"📊 Content type: {oldest.get('content_type', 'unknown')}")
        
        # Mark as skipped
        oldest["status"] = "skipped"
        state["total_skipped"] = state.get("total_skipped", 0) + 1
        save_state(state)
        tool_name = oldest.get('tool_name', 'Unknown')
        notify(f"🗑️ Draft skipped: {tool_name}")
        cleanup_draft_image(oldest)
        
        # Remove the skipped draft from the list
        drafts = [d for d in drafts if d.get("status") != "skipped" or d is not oldest]
        
        # Generate a new draft to replace the skipped one
        notify("🔄 Generating a new post to replace the skipped one...")
        
        # Call the generation script
        generation_success = generate_new_draft()
        
        if generation_success:
            # Reload drafts to get the new one
            reloaded_drafts = load_drafts()
            if reloaded_drafts:
                drafts = reloaded_drafts
                notify("✅ New draft generated! Check your Telegram for approval.")
            else:
                notify("⚠️ New draft was generated but couldn't be loaded. Please check logs.")
        else:
            notify("⚠️ Failed to generate new draft. Please check logs.")

    # Save updated drafts
    save_drafts(drafts)
    print("✅ Completed processing")


if __name__ == "__main__":
    main()