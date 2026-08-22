- Title: Drop the voice embedding model; use prosody features for similarity and root direction
- Status: Accepted
- Date: 2026-08-22
- Context: The original architecture used a pretrained speaker/voice embedding model (e.g. SpeechBrain
  ECAPA-TDNN or wav2vec2 XLS-R, used zero-shot as a feature extractor) to power two downstream features:
  "Similar Voices" matching and the PCA-based root-direction visualization. This is the only remaining
  deep-learning dependency after ADR 0001 dropped ASR — it requires loading a pretrained model, adds
  inference latency, and introduces a second external dependency (model weights, runtime) for a 3-day
  build.
- Options:
  1. Keep a pretrained voice embedding model as the feature vector for similarity/PCA.
  2. Drop it; use the prosody feature vector already computed by the Prosody Analyzer (avg pitch, pitch
     std, avg syllable duration, duration std) as the input to both Similar Voices and PCA instead.
- Decision: Option 2. The prosody feature vector already exists as a byproduct of the core pipeline
  (no extra computation), and both downstream features (Similar Voices, root direction) only need *some*
  numeric fingerprint to compare — they don't strictly require full speaker-identity embeddings.
- Consequences:
  - Zero deep-learning models remain in the pipeline; everything is classical signal processing
    (pitch/duration extraction) + statistics (a PCA transform fit once on the AI-Hub reference corpus)
    + threshold rules. This removes model-loading/inference risk entirely for the hackathon build.
  - "Similar Voices" now reflects similarity in *intonation/rhythm pattern*, not vocal timbre — two
    people with very different voices but similar pitch contours will be matched as "similar." Product
    copy should say "말투/억양이 비슷해요" rather than implying the voices themselves sound alike.
  - If a richer voice fingerprint is wanted later (post-hackathon), a pretrained embedding model can be
    reintroduced as an additional feature concatenated onto the existing prosody vector, without
    changing the PCA-fitting or Similar-Voices-matching logic (both just take a feature vector as input).
