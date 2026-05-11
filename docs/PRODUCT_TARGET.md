# LumaSift Product Target

## Final Product Shape

LumaSift is a local-first multimodal photo curation and editing-decision application for street, documentary, humanistic, and travel photography.

It is designed around this user workflow:

1. Point LumaSift at a local photo folder, such as `D:\DCIM`.
2. Process a small sample first, then scale to hundreds or thousands of photos.
3. Generate local previews, thumbnails, metadata, and cheap ranking proxies.
4. Send only high-value candidates or explicitly selected photos to a vision model.
5. Rank photos by story and editing value, not by sterile technical perfection.
6. Multi-select photos worth editing.
7. Generate concrete Lightroom/Capture One style editing guidance.
8. Export reports, contact sheets, and editing plans.

## Core Logic Chain

```text
Local folder
  -> manifest / file identity / preview cache
  -> local cheap pass
  -> Top-N candidate selection
  -> Qwen vision analysis
  -> story-first ranking
  -> user multi-select
  -> detailed editing parameters
  -> CSV / JSON / Markdown / contact sheet
```

## Main Scoring Dimensions

Primary dimensions:

- storytelling potential
- human/documentary value
- decisive moment
- emotional impact
- visual tension
- subject relationship
- editing potential

Secondary dimensions:

- technical readability
- exposure recoverability
- sharpness risk
- noise/grain suitability

Technical flaws should not automatically bury a photo. Motion blur, grain, deep shadows, or imperfect exposure may be positive when they strengthen street or documentary feeling.

## Qwen Usage Policy

Qwen analysis is mandatory for high-value candidates and selected photos.

The default cost-controlled strategy:

- process all photos locally;
- send only Top-N previews to Qwen;
- cache every model response;
- never send original RAW files;
- send only downscaled JPEG previews;
- retry and rotate keys on transient failures;
- keep local reports useful even when the API fails.

## Productization Direction

The product should not become a cloud RAW-upload SaaS. RAW files are too large, private, and expensive to upload at scale.

Preferred product architecture:

```text
Local FastAPI service
  + Python core pipeline
  + SQLite state/cache
  + React local Web UI
  + optional desktop shell later
```

The browser UI runs against `localhost`. Photos stay on the user's device. Only selected previews are sent to the configured vision model when enabled.

## Resume / Interview Value

The project should demonstrate:

- local-first architecture for privacy-sensitive, large-file AI workflows;
- RAW/JPEG/PNG ingestion;
- resumable batch processing;
- structured multimodal scoring;
- model response caching and cost control;
- human-in-the-loop selection;
- evaluation-ready ranking outputs;
- concrete editing parameter generation;
- future UI/product path.

The strongest resume framing:

> Built a local-first multimodal AI photo curation system for story-driven street/documentary workflows, combining RAW preprocessing, cost-controlled Top-N vision-model review, structured scoring, response caching, resumable batch processing, human-in-the-loop selection, and editing-parameter generation.
