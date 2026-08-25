"""
Polls Telegram for your APPROVE / SKIP reply on the pending draft.
If approved, publishes the post to Instagram via the Graph API.

Run by: .github/workflows/publish.yml (every 15-30 minutes)
"""
import os
import json
import time
import requests

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
IG_USER_ID = os.environ["IG_USER_ID"]
IG_ACCESS_TOKEN = os.environ["IG_ACCESS_TOKEN"]

STATE_FILE = "state.json"
DRAFT_FILE = "draft.json"


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"category_index": 0, "telegram_offset": 0}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_telegram_replies(offset):
    resp = requests.get(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates",
        params={"offset": offset, "timeout": 5},
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["result"]


def notify(text):
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        data={"chat_id": TELEGRAM_CHAT_ID, "text": text},
        timeout=15,
    )


def publish_to_instagram(image_url, caption, hashtags):
    full_caption = f"{caption}\n\n{hashtags}"

    # Step 1: create media container
    create_resp = requests.post(
        f"https://graph.facebook.com/v20.0/{IG_USER_ID}/media",
        data={
            "image_url": image_url,
            "caption": full_caption,
            "access_token": IG_ACCESS_TOKEN,
        },
        timeout=30,
    )
    if not create_resp.ok:
        print(f"Instagram media creation failed: {create_resp.status_code} {create_resp.text}")
    create_resp.raise_for_status()
    creation_id = create_resp.json()["id"]

    # Step 2: publish the container (Instagram needs a moment to process the
    # media container after creation, so we retry with short waits if needed)
    for attempt in range(6):
        publish_resp = requests.post(
            f"https://graph.facebook.com/v20.0/{IG_USER_ID}/media_publish",
            data={"creation_id": creation_id, "access_token": IG_ACCESS_TOKEN},
            timeout=30,
        )
        if publish_resp.ok:
            return publish_resp.json()

        print(f"Instagram publish failed (attempt {attempt + 1}/6): "
              f"{publish_resp.status_code} {publish_resp.text}")
        if "not ready" in publish_resp.text.lower() or "media id is not available" in publish_resp.text.lower():
            time.sleep(10)
            continue
        break  # different kind of error, no point retrying

    publish_resp.raise_for_status()
    return publish_resp.json()


def main():
    if not os.path.exists(DRAFT_FILE):
        return  # nothing pending

    with open(DRAFT_FILE) as f:
        draft = json.load(f)

    if draft.get("status") != "pending":
        return

    state = load_state()
    updates = get_telegram_replies(state.get("telegram_offset", 0))

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
        elif "SKIP" in text:
            decision = "skip"

    state["telegram_offset"] = max_update_id
    save_state(state)

    if decision == "approve":
        result = publish_to_instagram(
            draft["image_url"], draft["caption"], draft["hashtags"]
        )
        draft["status"] = "published"
        notify(f"✅ Published to Instagram! Media ID: {result.get('id')}")
        os.remove(DRAFT_FILE)
    elif decision == "skip":
        notify("🗑️ Draft skipped.")
        os.remove(DRAFT_FILE)
    # else: no decision yet, leave draft.json pending for next run


if __name__ == "__main__":
    main()
