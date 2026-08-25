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
from datetime import datetime

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
IG_USER_ID = os.environ.get("IG_USER_ID")
IG_ACCESS_TOKEN = os.environ.get("IG_ACCESS_TOKEN")
FB_PAGE_ID = os.environ.get("FB_PAGE_ID")
FB_PAGE_ACCESS_TOKEN = os.environ.get("FB_PAGE_ACCESS_TOKEN")

STATE_FILE = "state.json"
DRAFTS_FILE = "drafts.json"


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                print(f"Warning: {STATE_FILE} is corrupted. Resetting.")
                return {"category_index": 0, "telegram_offset": 0}
    return {"category_index": 0, "telegram_offset": 0}


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


def publish_to_facebook(image_url, caption, hashtags):
    """Post the same image + caption to the linked Facebook Page."""
    if not FB_PAGE_ID or not FB_PAGE_ACCESS_TOKEN:
        print("Facebook not configured - skipping")
        return None

    full_caption = f"{caption}\n\n{hashtags}"
    print(f"📘 Publishing to Facebook Page: {FB_PAGE_ID}")
    
    try:
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
            print("✅ Published to Facebook successfully!")
            return resp.json()
        else:
            print(f"❌ Facebook publish failed: {resp.status_code}")
            print(f"Response: {resp.text[:200]}")
            
            error_data = resp.json() if resp.text else {}
            error_msg = error_data.get("error", {}).get("message", "Unknown error")
            print(f"Error: {error_msg}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Facebook publish error: {e}")
        return None


def cleanup_draft_image(draft):
    """Remove the local image file after publishing/skipping."""
    path = draft.get("image_path", "")
    if path and os.path.exists(path):
        try:
            os.remove(path)
            print(f"Cleaned up image: {path}")
        except Exception as e:
            print(f"Could not remove image file {path}: {e}")


def validate_and_fix_draft(draft):
    """Ensure a draft has all required fields."""
    required_fields = ["image_url", "caption", "hashtags", "status"]
    for field in required_fields:
        if field not in draft:
            print(f"Warning: Draft missing '{field}' field")
            return False
    return True


def main():
    # Check required environment variables
    required_vars = {
        "TELEGRAM_BOT_TOKEN": TELEGRAM_BOT_TOKEN,
        "TELEGRAM_CHAT_ID": TELEGRAM_CHAT_ID,
        "IG_USER_ID": IG_USER_ID,
        "IG_ACCESS_TOKEN": IG_ACCESS_TOKEN,
    }
    
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
        
        ig_result = publish_to_instagram(
            oldest["image_url"], 
            oldest["caption"], 
            oldest["hashtags"]
        )
        
        if ig_result:
            oldest["status"] = "published"
            msg = f"✅ Published to Instagram! Media ID: {ig_result.get('id', 'unknown')}"
            
            # Try Facebook publishing
            try:
                fb_result = publish_to_facebook(
                    oldest["image_url"], 
                    oldest["caption"], 
                    oldest["hashtags"]
                )
                if fb_result:
                    msg += f"\n✅ Published to Facebook! Post ID: {fb_result.get('id', 'unknown')}"
                else:
                    msg += "\n⚠️ Facebook publish skipped or failed (Instagram still succeeded)"
            except Exception as e:
                msg += f"\n⚠️ Facebook publish error (Instagram still succeeded): {e}"
        else:
            oldest["status"] = "publish_failed"
            msg = "❌ Instagram publish failed. Please check logs above."
        
        notify(msg)
        cleanup_draft_image(oldest)
        
    elif decision == "skip":
        print("🗑️ Skipping draft")
        oldest["status"] = "skipped"
        notify("🗑️ Draft skipped.")
        cleanup_draft_image(oldest)

    # Save updated drafts
    save_drafts(drafts)
    print("✅ Completed processing")


if __name__ == "__main__":
    main()