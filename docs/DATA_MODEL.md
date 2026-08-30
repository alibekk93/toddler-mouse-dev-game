# Data Model

## 1. Principles

- **Plain files, human-readable manifest.** The parent can open the folder, see `cat_01.png`, copy the whole thing to a USB stick, and it works on another machine.
- **The manifest is the index; the disk is the truth.** If they disagree, the disk wins and the manifest is repaired.
- **Never destructive.** Deleting an image in the UI moves the file to `_trash/`, it does not unlink it.
- **Relative paths only.** No absolute paths anywhere in the JSON, ever — that is what breaks portability.

## 2. Folder layout

```
library/
├── library.json            # manifest (see §3)
├── library.json.bak        # previous good version, rotated on every write
├── settings.json           # see §5
├── images/
│   ├── 7f3a1c2e.png        # normalised, content-addressed by hash prefix
│   └── ...
├── thumbs/
│   └── 7f3a1c2e.jpg        # 256px, generated on import
├── audio/
│   ├── questions/
│   │   └── 9b2d4f10.wav
│   ├── praise/
│   │   └── 3c8e7a55.wav
│   └── retry/
│       └── e1f09b23.wav
├── stats/
│   └── 2026-08-30.jsonl    # one JSON object per round, append-only
└── _trash/
    └── ...                 # deleted items, same subfolder structure
```

Resolution order for the library path:

1. `--library PATH` CLI flag (this is what you'll actually use: `--library ../library`).
2. `last_library` recorded in the app config.
3. Fallback default `%LOCALAPPDATA%/BuskaGame/library/`, created empty on first run.

In this setup the real library is `buska-game/library/`, a sibling of the repo — deliberately outside version control, since it contains family photos and voice recordings. `toddler-mouse-dev-game/testlib/` is a throwaway library for development and is gitignored.

## 3. `library.json`

```jsonc
{
  "schema_version": 1,
  "updated_at": "2026-08-30T14:02:11Z",
  "images": [
    {
      "id": "7f3a1c2e",              // 8-hex prefix of sha256 of normalised bytes
      "file": "images/7f3a1c2e.png",  // relative to library root
      "thumb": "thumbs/7f3a1c2e.jpg",
      "tags": ["cat", "animal"],      // lowercase, trimmed, deduped
      "category": "animals",          // optional, free string
      "label": "orange tabby",        // optional, parent-facing only
      "enabled": true,
      "source": "clipboard",          // clipboard | file | drop
      "added_at": "2026-08-30T13:55:02Z",
      "width": 1024,
      "height": 768
    }
  ],
  "sounds": [
    {
      "id": "9b2d4f10",
      "kind": "question",             // question | praise | retry
      "file": "audio/questions/9b2d4f10.wav",
      "target_tag": "cat",            // REQUIRED for kind=question, absent otherwise
      "label": "Where is the cat?",   // parent-facing only
      "duration_ms": 1840,
      "enabled": true,
      "added_at": "2026-08-30T13:57:40Z"
    }
  ]
}
```

### Rules

- `id` is the first 8 hex chars of the sha256 of the file's normalised bytes. Collisions extend to 12 chars. This gives free duplicate detection: same picture pasted twice → same id → offer to merge tags.
- `tags` are opaque strings. The app never interprets them. `cat`, `red`, `7`, `letter_b`, `toyota` are all the same to the engine.
- A `question` sound whose `target_tag` matches no enabled image is **valid but unusable** — surfaced as a warning, never an error.
- An image with no tags is valid but never appears as a correct answer. It may still appear as a distractor.
- `praise` and `retry` sounds have no `target_tag`; the game picks one at random.

## 4. Validation and repair

Run on startup and on demand from parent mode. Every check yields a warning with a concrete fix action, never a crash.

| Check | Action |
| --- | --- |
| Manifest entry with no file on disk | Mark `broken: true`, exclude from play, offer Locate / Remove |
| File on disk with no manifest entry | Offer to adopt it into the staging tray for tagging |
| `library.json` unparseable | Restore from `.bak`; if that fails, rebuild by scanning disk (files adopted untagged) |
| Tag with a question but zero images | Warn: "record exists, no pictures yet" |
| Tag with images but no question | Warn: "pictures exist, no question recorded" |
| Fewer than `option_count` enabled images total | Block Play with the reason |
| Duplicate image hash | Offer merge |

Write protocol for `library.json`: write to `library.json.tmp`, fsync, rotate current → `.bak`, atomic rename tmp → live. A power cut mid-save must never lose the library.

## 5. `settings.json`

Flat key/value matching `SPEC.md` §3.4, plus `schema_version`. Unknown keys are preserved on write (forward compatibility), missing keys fall back to defaults. Never crash on a settings file from a newer version — load what you understand, keep the rest.

## 6. `stats/*.jsonl`

One line per completed round, append-only, one file per day:

```json
{"ts":"2026-08-30T14:03:22Z","target_tag":"cat","n":3,"correct_id":"7f3a1c2e","shown":["7f3a1c2e","a91b0e4d","c3d7f228"],"first_click_correct":true,"misses":0,"ms_to_first_click":3120,"replays":0,"hinted":false}
```

Append-only JSONL means a corrupt final line costs one round, not the file. The Progress screen aggregates these lazily; nothing else reads them.

## 7. Media normalisation on import

**Images** — Pillow:
1. Apply EXIF orientation, then strip all EXIF (phone photos carry GPS coordinates; this library may get shared).
2. Convert to RGB (or RGBA if genuinely transparent). Flatten animated GIFs to frame 1.
3. Downscale so the long edge is ≤ 1600px, Lanczos. Nobody needs 4000px of cat on a 1080p screen.
4. Save as PNG if the source had transparency, otherwise JPEG q=88.
5. Generate a 256px thumbnail.
6. Reject anything over 50MB or with pathological dimensions before decoding — a malformed image should not take down the parent UI.

**Audio** — on record or import:
1. Mono, 48 kHz, 16-bit PCM WAV. Uncompressed and boring on purpose: instant playback, no codec dependency, trivially editable.
2. Trim leading/trailing silence below −45 dBFS, leaving 80ms of padding.
3. Peak-normalise to −3 dBFS so no recording is much louder than another.
4. Cap length at 10s; a question longer than that is a different problem.