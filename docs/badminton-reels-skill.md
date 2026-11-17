---
name: badminton-reels
description: Generate local badminton videos: original narrated reports, full-rally highlights, shot collections, or explicitly requested rallies; retrieve real video URLs.
---

# Local badminton-reels playbook

This is a private local MCP, enabled explicitly by the administrator. Never use
the historical lab URL. Call the registered badminton-reels tools directly.

1. `list_matches`: use its exact names. This catalog differs from badminton-db.
2. `generate_reel` returns a job_id immediately. Save it; do not resubmit while running.
3. Poll `get_reel_status` with that job_id. If still running, report progress and
   retain the job_id; retrieve it later. Do not invent completion or video links.
4. On success call `get_reel_result`. Embed the exact returned video_url using
   `![羽球精華](video_url)` and report selected rallies, duration and relevant warnings.
   For plan_only=true, return the plan; no video exists yet.
5. On failure explain error_code. `resume_reel` resumes failed NEW modes after
   the provider/config problem is fixed; it does not resume original news_report.

Keep options independent:

| reel_type | Purpose |
| --- | --- |
| news_report | Original multi-agent narrated report, original defaults/timing/anchor behavior |
| match_recap | Prefer representation across games, subject to budget |
| highlights | Rank exciting rallies, without requiring every game |
| shot_collection | Strict shot_types + optional hitter focus_player; include complete source rallies even if hitter loses |
| rally_collection | Exact rally_ids required; complete source clips, chronological order |

For NEW modes, choose narration=continuous for commentary during play,
brief for short context, none for no generated voice. Use continuous when the
user requests running commentary. Speech speed is separately controlled by
speech_speed=0.5–2.0 (default1.2). timing_mode=original keeps video at1x;
fit_narration adjusts video0.5–2x to measured speech without truncating the source.
These controls do not change the original news_report path.

style describes tone (professional, humorous, dramatic, educational or free text),
not editing purpose. New-mode duration_target_sec is30–600; default90.
Original news_report remains90 seconds via MCP (CLI180), humorous, zh-TW,
max_highlights8 and enable_anchor=true. max_highlights is clamped1–12.

Example request for Lee smashes with commentary:
{"match_name":"<exact catalog name>","reel_type":"shot_collection",
 "shot_types":["殺球"],"focus_player":"LEE Zii Jia","narration":"continuous",
 "style":"professional","speech_speed":1.2,"timing_mode":"fit_narration",
 "duration_target_sec":180,"enable_anchor":false}

Use sets to restrict games; rally_ids must be actual segment IDs, not shot-row
indices. Strict filters may return fewer clips or an error instead of unrelated
footage. plan_only=true downloads/measures candidate clips but skips GPT/TTS.
HF source clips often have no sound; none may yield a silent output. No ambient
sound is fabricated. Commentary is annotation-based, approximately synchronized;
its evidence references are checked, its prose is not independently fact-checked.
Scores/point winners come from verified score transitions and shot annotations.
No computer vision or unobserved shot speed/direction claims are available.
API costs are not yet reported by this service to the gateway usage ledger.
