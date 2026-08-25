"""
Polls Telegram for your APPROVE / SKIP reply. Each reply acts on the
OLDEST pending draft in the queue (so twice-daily generation doesn't
overwrite anything — drafts just queue up until you respond).
If approved, publishes that post to Instagram via the Graph API.

Run by: .github/workflows/publish.yml (every ~20 minutes)
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
DRAFTS_FILE = "drafts.json"


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE) as f:
            return json.load(f)
    return {"category_index": 0, "telegram_offset": 0}


def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def load_drafts():
    if os.path.exists(DRAFTS_FILE):
        with open(DRAFTS_FILE) as f:
            return json.load(f)
    return []


def save_drafts(drafts):
    with open(DRAFTS_FILE, "w") as f:
        json.dump(drafts, f, indent=2)


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
        break

    publish_resp.raise_for_status()
    return publish_resp.json()


def cleanup_draft_image(draft):
    path = draft.get("image_path", "")
    if path and os.path.exists(path):
        os.remove(path)


def main():
    drafts = load_drafts()
    pending = [d for d in drafts if d.get("status") == "pending"]
    if not pending:
        return  # nothing to do

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

    if decision is None:
        return  # no new reply yet, leave everything pending

    # act on the oldest pending draft
    oldest = pending[0]

    if decision == "approve":
        result = publish_to_instagram(oldest["image_url"], oldest["caption"], oldest["hashtags"])
        oldest["status"] = "published"
        notify(f"✅ Published to Instagram! Media ID: {result.get('id')}")
        cleanup_draft_image(oldest)
    elif decision == "skip":
        oldest["status"] = "skipped"
        notify("🗑️ Draft skipped.")
        cleanup_draft_image(oldest)

    save_drafts(drafts)


if __name__ == "__main__":
    main()