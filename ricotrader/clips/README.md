# Rica's realistic webcam clips

Locked look (Mochi, Nov 22): black sports bra + open lilac hoodie (`rica-grok-look.jpg`, `walkaway-grok.mp4`).

Clips are made on **grok.com** (Mochi's Grok plan, no extra charge), not the paid API:
1. Claude (Claude in Chrome, Mochi's Brave) generates the clip on grok.com/imagine from the locked look.
2. It downloads it as `rica-<name>.mp4` into Downloads.
3. `scripts/rica_uploader.py --watch` on Mochi's PC sends it to `ricotrader/clips/<name>.mp4` here.

`make_clips.py` (xAI API) is OFF: it does nothing unless RICA_ALLOW_PAID_API=yes. Mochi said no API charges.
Realistic AI host: turn YouTube's AI label ON and keep the "AI host · real trades" tag.
