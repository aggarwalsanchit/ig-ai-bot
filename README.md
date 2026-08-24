# Instagram AI Auto-Poster (with Telegram approval)

Generates a daily "AI tool that solves a real problem" post using Gemini,
sends you a preview on Telegram, and publishes to Instagram only after you
reply **APPROVE**.

Everything here runs on free tiers: GitHub Actions, Gemini API, Imgur, Telegram.

## How it works

1. **`generate.yml`** runs once a day → calls Gemini for an idea → makes a
   simple image card → uploads it to Imgur → sends you a Telegram preview →
   saves `draft.json` to the repo.
2. **`publish.yml`** runs every 20 minutes → checks if you replied
   `APPROVE` or `SKIP` on Telegram → if approved, publishes to Instagram via
   the Graph API.

You only need your phone to reply on Telegram — no PC required once it's set up.

## One-time setup

### 1. Get a Gemini API key (free)
- Go to https://aistudio.google.com/apikey and create a key.

### 2. Get an Imgur Client ID (free, for image hosting)
- Register an app at https://api.imgur.com/oauth2/addclient (choose
  "Anonymous usage without user authorization").
- Copy the **Client ID**.

### 3. Create a Telegram bot
- Message **@BotFather** on Telegram → `/newbot` → follow prompts → copy the
  **bot token**.
- Send your new bot any message, then visit:
  `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
  and copy your **chat id** from the response.

### 4. Set up Instagram Graph API access
- Your Instagram account must be a **Business or Creator account**, linked
  to a **Facebook Page** (do this in the Instagram app: Settings → Account
  type).
- Go to https://developers.facebook.com/apps → create an app (type:
  "Business") → add the **Instagram Graph API** product.
- Under Tools → Graph API Explorer, generate a **User Access Token** with
  these permissions: `instagram_basic`, `instagram_content_publish`,
  `pages_show_list`, `pages_read_engagement`.
- Exchange it for a **long-lived token** (~60 days) using the
  [token debug/exchange endpoint](https://developers.facebook.com/docs/facebook-login/guides/access-tokens/get-long-lived).
- Find your **Instagram Business Account ID** by calling:
  `GET /me/accounts` then `GET /<PAGE_ID>?fields=instagram_business_account`.
- ⚠️ You'll need to refresh this token roughly every 60 days (a calendar
  reminder is enough for now — we can automate this later).

### 5. Push this repo to GitHub and add secrets
- Create a new repo on GitHub, push these files.
- Go to **Settings → Secrets and variables → Actions** and add:
  - `GEMINI_API_KEY`
  - `IMGUR_CLIENT_ID`
  - `TELEGRAM_BOT_TOKEN`
  - `TELEGRAM_CHAT_ID`
  - `IG_USER_ID`
  - `IG_ACCESS_TOKEN`

### 6. Test it
- Go to the **Actions** tab → run `Generate daily post idea` manually
  (workflow_dispatch) → you should get a Telegram preview within a minute.
- Reply `APPROVE` → within 20 minutes `Check approval and publish` will post
  it to Instagram.

## Adjusting the schedule
Edit the `cron` line in `.github/workflows/generate.yml`. Cron times are in
UTC — the current setting (`30 3 * * *`) is 9:00 AM IST. Use
https://crontab.guru to adjust.

## Next steps (once this is working)
- Swap the single-image generator for a carousel (multiple slides).
- Add Reels support (needs a video file + `media_type=REELS` in the Graph
  API call).
- Let you type a custom topic in Telegram instead of always auto-rotating
  categories.
