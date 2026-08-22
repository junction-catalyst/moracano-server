- Title: Drop ASR (Whisper) from the speech analysis pipeline
- Status: Accepted
- Date: 2026-08-22
- Context: The original architecture (Dialect Audio → ASR / Prosody Analyzer / Voice Embedding →
  Dialect Root Generation) used ASR to get a transcript and word-level timestamps, which syllable
  segmentation then depended on. Two problems: (1) general-purpose ASR tends to "correct" dialect
  pronunciation back to standard Korean, which would corrupt the very signal the product is trying to
  capture, and (2) it adds a full model call (latency, API dependency, cost) to every recording.
- Options:
  1. Keep ASR (Whisper API) for transcript + word timestamps, feed into syllable segmentation.
  2. Drop ASR entirely; segment syllables acoustically (energy/pitch onset detection) and align them
     to the already-known prompt sentence text (chosen upstream by the recommendation block), instead
     of transcribing what the user actually said.
- Decision: Option 2. The prompt sentence text is already known before recording starts (it's picked by
  the word/example-sentence recommendation block), so there is no need to ask the user's own speech
  what it said — we only need *where* each syllable falls in time, which acoustic onset detection gives
  without transcription. This also matches the product's own framing that dialect lives in sound
  (pitch/duration/rhythm), not text.
- Consequences:
  - No dependency on any ASR provider (no API key, no per-call latency/cost, one fewer network hop).
  - The visualization/haptic layer ("뭐 라 카 노" style) renders the *prompt* text against detected
    syllable boundaries, not a transcript of what was actually said — if a user skips/adds syllables
    relative to the prompt, the mapping can misalign. Acceptable for the hackathon MVP; a future
    version could re-add ASR as a validation-only signal (not for timing) if this becomes a real issue.
  - "Regional vocabulary" as a Dialect Root analysis element (from the original architecture) is
    dropped along with ASR; regional-word detection would need a transcript to match against a
    dialect-standard word lookup. If reinstated later, it should be scoped as a separate, optional
    signal — not a blocker for the core pitch/duration/rhythm pipeline.
