# Leonida Clips auto-clipper

Posts GTA 6 Shorts to YouTube with no one touching it. Three times a day, GitHub Actions:

1. Finds the most-viewed GTA VI Twitch clips from the last 24 hours (skips ones already posted).
2. Downloads the best one and transcribes it (faster-whisper).
3. Asks Claude to write Rico Neon's hook line, closing verdict, banner text, title, description and tags.
4. Voices Rico (free Edge TTS, or ElevenLabs if you add a key).
5. Renders a 1080x1920 Short: blurred fill, zoomed gameplay, word-by-word pink captions, Rico's avatar during his lines, streamer credit, game audio ducked under Rico.
6. Uploads it to the channel with the streamer credited and linked in the description.
7. Records the clip in `state/posted.json` so it never posts twice.

Settings live in `config.yaml` (posts per run, minimum views, streamer allow/block lists, voice, privacy).

## One-time setup (about 45 minutes, only you can do these)

Each step makes a key; paste each into the GitHub repo under **Settings > Secrets and variables > Actions > New repository secret**.

1. **YouTube channel.** Create the Google account and channel (see the launch kit doc). Verify it with your phone.
2. **GitHub repo.** Create an empty private repo (e.g. `leonida-clips`) and push this folder to it, or ask Claude to push it once the repo exists.
3. **Twitch keys** (free, 2 min). dev.twitch.tv/console > Register Your Application. Name: anything. OAuth redirect: `http://localhost`. Category: Application Integration. Copy the Client ID, then New Secret.
   Secrets: `TWITCH_CLIENT_ID`, `TWITCH_CLIENT_SECRET`
4. **Claude key.** console.anthropic.com > API Keys > Create key. Cost is a few cents a day at 3 Shorts/day.
   Secret: `ANTHROPIC_API_KEY`
5. **YouTube upload access** (15 min).
   - console.cloud.google.com > create a project > APIs & Services > Library > enable **YouTube Data API v3**.
   - OAuth consent screen: External, add the channel's Gmail as a test user, then **Publish app** (otherwise the token expires every 7 days).
   - Credentials > Create credentials > OAuth client ID > **Desktop app** > download the JSON.
   - On your computer: `pip install google-auth-oauthlib` then `python scripts/get_youtube_token.py client_secret.json`, sign in with the channel account.
   Secrets: `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, `YOUTUBE_REFRESH_TOKEN`
6. **Optional: Rico's avatar.** Save a transparent PNG as `assets/rico.png` (prompt is in the launch kit doc).
7. **Optional: better voice.** ElevenLabs key as `ELEVENLABS_API_KEY`, set `voice_engine: elevenlabs` and the voice id in `config.yaml`.

Then open the repo's **Actions** tab > Auto-clip GTA 6 Shorts > **Run workflow** with "dry run" ticked. The finished Short appears as a downloadable artifact on the run page. If it looks good, the schedule takes over.

## Two limits to know

- **Uploads start private.** YouTube forces videos uploaded through a new, unaudited Google Cloud project to private. Until the free audit is approved (apply at support.google.com/youtube/contact/yt_api_form, usually a few weeks), either flip each video to public in YouTube Studio, or keep the bot as the maker and upload the artifacts yourself. Once approved, set `privacy_status: public`.
- **Copyright.** The bot credits and links every streamer, and Rico's commentary makes each Short transformative, but a streamer can still claim a clip. For the safest channel, fill `broadcaster_allowlist` with streamers who allow clipping and set `allow_any_broadcaster: false`.
