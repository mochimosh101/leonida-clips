# Rica Shorts: styles, openings, A/B log

Mochi (Nov 25): Rica should talk less, and the openings must not all look the same ("feels scripted").

## Two styles (A/B for one week: Nov 26 – Dec 2, then keep the winner)
- **talk**: every scene is a speaking clip (the old style).
- **quiet**: 1 spoken hook (8 words or fewer, first ~2 s) -> trade scenes play with Rica IDLE (no voice):
  `{"quiet": true, "clip": "ricotrader/clips/idle-*.mp4", "dur": 4-6}` with the chart, fills and live P&L card
  -> 1-2 short spoken lines (10 words or fewer) only at the biggest P&L moments -> 1 spoken ending line.
  Idle clips (same locked look): idle-phone, idle-couch, idle-coffee. Add a new idle variant some nights
  (stretching, texting, lying back, eating a snack, spinning the chair) so they don't repeat; never use the
  same idle clip twice in a row inside one Short.
Alternate styles night by night using the last entry in style-log.json. Put `"style"` and `"opening"` in the episode JSON.

## Openings (pick one NOT used in the last 5 entries of style-log.json)
Each opening = the first clip's action (Grok prompt) + the first screen + the line pattern. Always tie it to that day's real trades.
1. mid-reaction: clip starts with her already reacting (hands on head / covers mouth / fist pump), then the line. Screen: straight onto the day's biggest trade with its live P&L card already moving (no from_focus zoom).
2. phone-first: she's looking at her phone, then turns her eyes to camera and says the line. Screen: whole day with only the DAY P&L card drawing.
3. lean-in: she leans close to the camera and says it low, like a secret. Screen: tight zoom on the key exit fill.
4. sit-down: she drops into her chair into frame and blurts the line. Screen: chart replay racing from 6:30 to the key moment.
5. laugh-or-groan: she laughs (green day) or groans (red day) at the screen, then the line. Screen: classic whole-chart -> zoom.
6. silent-open: no words at first — idle/reaction clip under a big pop number for ~1.5 s, then the hook line in scene 2.
7. question: she asks the viewer a question about that day's trade ("would you have held this?").
8. side-glance: she glances off to the side as if someone asked her, then answers to camera.
Line patterns to rotate: number-first, timestamp-first, confession ("I messed up"), question, "watch this".
Never reuse the exact Grok prompt wording from the last Short: vary posture, expression and first words.

## Log
style-log.json: list of {"date", "file", "style", "opening", "video_id"} appended when a Short is queued
(video_id filled after posting). After Dec 2 compare views per style (YouTube stats) and keep the winner.

## Never look glitched or fake (Mochi, Nov 25)
- No reaction punch-ins (tinted zoom + word): they made her look like a different woman. Off unless "reactions": true (don't).
- Big result number only appears when that trade's exit fills; it must equal the trade's real P&L; the ending number must equal the day's last total.
- One "Order filled" alert at a time; P&L cards appear without cross-fades; outro stays on the chart (focus [440,230,1440,880]), never the full page.
- Cuts land where her pose matches the shared start pose (render picks the cut), no dissolves.
- ricotrader/qa.py runs before every upload (main.py) and blocks it on: non say-/idle- clips, look drift, webcam jumps, number mismatches. Run it on every preview too and look at <video>.qa.png.

## Never open a cut on the same smile (Mochi, Nov 26)
Every Grok clip starts from the same base photo (Rica smiling), so frame 0 of every clip looks identical.
- The renderer now starts each clip mid-motion (render.auto_start: the pose furthest from the base photo, before her first word).
  Leave "clip_from" out of the episode so it is picked automatically.
- Speaking clips need room for that: every say prompt starts with ~2 s of a distinct action and a NON-smiling expression
  ("Right away she drops the smile and <action> ... after about two seconds she says exactly: ...").
  Vary the action each scene (leaning in worried, slumped with arms crossed, rubbing her forehead, eyes on the phone, sipping coffee...).
- qa.py blocks the upload if any cut opens on the base photo or two cuts open on the same pose. Still look at the
  first webcam frame of every scene before posting.
- grok.com (small Brave window): there is no "Add Prompt" menu; type the prompt in "Ask Grok anything" and click the button with aria-label "Make video".
