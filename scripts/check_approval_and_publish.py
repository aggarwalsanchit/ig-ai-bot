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


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def load_drafts():
    """Load drafts with validation to prevent corruption issues."""
    if not os.path.exists(DRAFTS_FILE):
        return []
    
    try:
        with open(DRAFTS_FILE) as f:
            data = json.load(f)
        
        # Validate data structure
        if not isinstance(data, list):
            print(f"Error: {DRAFTS_FILE} is not a list. Resetting.")
            backup_corrupted_file()
            return []
        
        # Check if all items are dictionaries
        valid_drafts = []
        for i, item in enumerate(data):
            if isinstance(item, dict):
                valid_drafts.append(item)
            else:
                print(f"Warning: Draft at index {i} is not a dictionary. Skipping.")
        
        return valid_drafts
    
    except json.JSONDecodeError as e:
        print(f"Error: {DRAFTS_FILE} is corrupted ({e}). Resetting.")
        backup_corrupted_file()
        return []
    except Exception as e:
        print(f"Unexpected error loading drafts: {e}")
        return []


def backup_corrupted_file():
    """Create a backup of corrupted file before resetting."""
    if os.path.exists(DRAFTS_FILE):
        backup_name = f"{DRAFTS_FILE}.corrupted_{int(time.time())}.bak"
        try:
            os.rename(DRAFTS_FILE, backup_name)
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
    
    with open(DRAFTS_FILE, "w") as f:
        json.dump(valid_drafts, f, indent=2)


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

    try:
        create_resp = requests.post(
            f"https://graph.facebook.com/v20.0/{IG_USER_ID}/media",
            data={
                "image_url": image_url,
                "caption": full_caption,
                "access_token": IG_ACCESS_TOKEN,
            },
            timeout=30,
        )
        create_resp.raise_for_status()
        creation_id = create_resp.json()["id"]
    except requests.exceptions.RequestException as e:
        print(f"Instagram media creation failed: {e}")
        return None

    # Retry logic for media publishing
    for attempt in range(6):
        try:
            publish_resp = requests.post(
                f"https://graph.facebook.com/v20.0/{IG_USER_ID}/media_publish",
                data={"creation_id": creation_id, "access_token": IG_ACCESS_TOKEN},
                timeout=30,
            )
            if publish_resp.ok:
                return publish_resp.json()

            print(f"Instagram publish failed (attempt {attempt + 1}/6): {publish_resp.text}")
            if "not ready" in publish_resp.text.lower() or "media id is not available" in publish_resp.text.lower():
                time.sleep(10)
                continue
            else:
                break
        except requests.exceptions.RequestException as e:
            print(f"Instagram publish attempt {attempt + 1} failed: {e}")
            time.sleep(5)
            continue

    return None


def publish_to_facebook(image_url, caption, hashtags):
    """Post the same image + caption to the linked Facebook Page."""
    if not FB_PAGE_ID or not FB_PAGE_ACCESS_TOKEN:
        return None

    full_caption = f"{caption}\n\n{hashtags}"
    try:
        resp = requests.post(
            f"https://graph.facebook.com/v20.0/{FB_PAGE_ID}/photos",
            data={
                "url": image_url,
                "caption": full_caption,
                "access_token": FB_PAGE_ACCESS_TOKEN,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        print(f"Facebook publish failed: {e}")
        return None


def cleanup_draft_image(draft):
    """Remove the local image file after publishing/skipping."""
    path = draft.get("image_path", "")
    if path and os.path.exists(path):
        try:
            os.remove(path)
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
        print(f"Approving draft: {oldest.get('tool_name', 'Unknown')}")
        
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
            msg = "❌ Instagram publish failed. Please check logs."
        
        notify(msg)
        cleanup_draft_image(oldest)
        
    elif decision == "skip":
        print("Skipping draft")
        oldest["status"] = "skipped"
        notify("🗑️ Draft skipped.")
        cleanup_draft_image(oldest)

    # Save updated drafts
    save_drafts(drafts)
    print("Completed processing")


if __name__ == "__main__":
    main()