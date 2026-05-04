Generate a `cat_story` script JSON for the Vibrava pipeline based on: $ARGUMENTS

## TikTok Style Guidelines

Write for short-form vertical video. The goal is to feel native to TikTok — not like a YouTube video or blog post read aloud.

**Tone & pacing:**
- Each sentence is 1 punchy line. No compound sentences joined with "and then... and then..."
- Conversational, slightly dry humor. The cat is the main character and always winning.
- Short sentences hit harder. Aim for 6–10 words per sentence.
- Build momentum — start calm, escalate the situation, end with a smug or chaotic payoff.
- Use relatable "POV" energy: the viewer should feel like they've lived this.

**Structure (12–16 sentences, target 20+ seconds of spoken audio):**
1. Set the scene / establish the vibe (calm)
2. Introduce the problem or catalyst
3. Build tension — 2–3 beats of escalation
4. False resolution or complication
5. Peak chaos or punchline
6. Cat wins / smug resolution — let it breathe, 2–3 closing lines

Short sentences (4–6 words) run ~1.5–2s each. Aim for enough sentences that the total spoken time clears 20 seconds.

**Echo transitions:**
Rarely, start a sentence with the last word of the previous sentence to create a rhythmic callback (e.g. "...and he just sat there" → "there. just sitting."). Use at most once per script, at a moment of emphasis or disbelief.

**Stutters:**
Occasionally have a sentence stutter for comedic effect — repeat the first word or syllable 1–2 times (e.g. "he— he just stared at me" or "i i cannot believe this"). Use sparingly (1–2 per script max), at moments of shock or disbelief.

**Avoid:**
- Filler words: "basically", "kind of", "you know"
- Passive voice
- Anything that sounds like narration for a documentary
- Capitalizing the first word of sentences
- Ending sentences with periods

## Output Format

Write the script as a JSON file matching this schema exactly. Use the Write tool to save it to `scripts/<slug>.mp4` → `scripts/<slug>.json` (the filename without `.mp4`). After writing, tell the user the filename.

```
{
  "mode": "cat_story",
  "voice_id": "EXAVITQu4vr4xnSDxMaL",
  "caption_style": "word",
  "output_filename": "<slug>.mp4",
  "resolution": [1080, 1920],
  "sentences": [
    {
      "id": "s1",
      "text": "...",
      "sound_effect": null
    }
  ]
}
```

- `output_filename`: kebab-case slug based on the topic, e.g. `monday-morning.mp4`
- `caption_style`: always `"word"` (word-by-word highlight)
- `sound_effect`: always `null` for now
- `music`: optional filename from `res/music/`, e.g. `"lofi.mp3"`. Omit if no music.
- `music_volume`: optional float, default `0.15`. Controls backing music level relative to speech.
- `music_start`: optional float, seconds into the video when music begins. Default `0.0`.
- `pause_duration`: optional float, seconds of silence after each sentence. Overrides the config default. Use ~0.5–1.2s for dramatic pauses, shorter for fast-paced scripts.
- `pause_jitter`: optional float (max `1.0`). When > 0, randomizes each gap to a value between `0.1` and this value. Adds natural rhythm — good for conversational scripts.
- `random_fallback`: optional bool, default `false`. When `true`, uses a random image if no tag match is found instead of leaving the segment blank.
- `tts_provider`: optional, `"elevenlabs"` (default) or `"tiktok"`.
- Sentence IDs: `s1`, `s2`, etc.
