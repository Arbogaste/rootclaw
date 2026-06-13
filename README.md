# Root Claw

Root Claw is a multi-mode directory analysis tool powered by local or cloud LLMs via Ollama or OpenRouter.

**Modes:**
- **`scan`** — recursive source code audit: security, vulnerabilities, architectural review
- **`images`** — recursive image/video analysis via vision LLMs; two sub-modes: cluster tagging or per-file forensic reports
- **`simulate`** — step-by-step execution simulation for a specific function/scenario

## Features

### Code Scan Mode
* **Resilient Execution**: Native timeout management for LLM requests to prevent indefinite hangs, with automatic fallback across a model chain.
* **Dynamic Configuration**: Hot-reloading of `config.json` between file analyses, allowing on-the-fly adjustment of models, notes, and ignore patterns.
* **Automated Ingestion**: Optional support for cloning remote Git repositories directly via configuration for immediate analysis.
* **Recursive Mapping**: Scans a directory and all subdirectories for specific file extensions.
* **Smart Chunking**: Automatically splits large files into overlapping chunks on line boundaries to fit model context windows while maintaining continuity.
* **Context Retention**: Passes summaries of previous findings to subsequent chunks to ensure the model understands the file state as it moves forward.
* **Accuracy Levels**: Adjustable intensity (1 to 3) that controls chunk size and enables additional validation passes for high-precision results.
* **Fallback Logic**: Configurable primary and fallback model chains for both Ollama and OpenRouter to ensure execution completes even if a specific model fails.
* **Non-Destructive Outputs**: Generates analysis reports alongside the original files without modifying the source code. Own output files are always excluded from re-scanning.
* **Knowledge Base Injection**: Place `.md` or `.txt` files under `kb/<name>/` and reference them in config to inject domain knowledge (OWASP, past audits, etc.) into the system prompt.
* **Flexible Output**: Control output format, verbosity, scope, and aggregation per run via the `output` config block.

### Image Mode (`image_claw`) — `image_mode: "tag"` (default)
* **Vision LLM Tagging**: Each image is tagged by a vision model (Ollama or OpenRouter) using a configurable prompt.
* **Progressive Clustering**: Tags accumulate across all images; once a threshold is reached, the top-N tags become cluster labels and all images are sorted automatically.
* **Move or Copy**: Configurable — move files (default) or copy, preserving originals.
* **Recursive + Multi-directory**: Scans subdirectories recursively. Accepts multiple comma-separated input paths.
* **Resume-safe**: State persisted in `image_state.json` — interrupt and restart without re-tagging already processed images.
* **Prompt-driven**: Tag prompt lives in `prompts/image_tag.txt` — edit without touching Python.

### Image Mode — `image_mode: "analyze"`
* **Per-file Forensic Reports**: Instead of clustering, produces one structured `.md` document per image or video file.
* **MP4 / Video Support**: For each video file (`.mp4`, `.mov`, `.avi`), extracts N evenly-spaced frames (default `5`, configurable as `video_frames`) and analyzes each frame individually via the vision LLM.
* **Timestamped Frame Labels**: Each frame report is labeled with its timestamp in seconds (e.g. `Frame 2 [12.4s]`) and merged into a single document per video.
* **Audio Transcription**: Set `audio_extensions` in config to enable `.mp3` / `.wav` / `.m4a` processing. Transcribes via Whisper (local) or OpenRouter STT and writes one transcript `.md` per file. Disabled by default — zero impact if not configured.
* **Resume-safe**: State tracked in `image_state.json` under an `analyzed` key — already-processed files are skipped on restart.
* **Separate Prompt Files**: Uses `prompts/image_analysis.txt` for still images and `prompts/video_frame_analysis.txt` for video frames (both editable without touching Python).

### Common
* **Customizable Prompts**: All prompts live in `prompts/` as plain text files.
* **Multi-Provider Support**: Switch between Ollama (local) and OpenRouter (cloud) via the `provider` field.

## Installation

### Ollama

```bash
pip install ollama
```

You must have [Ollama](https://ollama.ai) installed and running locally.

### OpenRouter

```bash
pip install requests
```

## Usage

```bash
# Code audit
python3 root_claw.py scan <directory> <config.json>
python3 root_claw.py <directory> <config.json>          # legacy, same as scan

# Image tagging and clustering
python3 root_claw.py images <directory> <config_images.json>
python3 root_claw.py images <directory> <config_images.json> <output_dir>
python3 root_claw.py images <dir1,dir2,dir3> <config_images.json> <output_dir>

# Execution simulation
python3 root_claw.py simulate <file> <config.json> <function_name> <goal>
```

`examples/` is a sample directory structure for testing the scan mode:

```
examples/
  Test.java
  Tests/
    ReTest.java
    safe.sol
    big.sol
    subscript/
      script3.php
      subsubscript/
        script4.js
```

## Configuration

```json
{
    "extensions": [".java", ".py", ".sol"],
    "ignore": ["Avoid.java", "avoid.sol"],
    "ignore_file": ".gitignore",
    "accuracy_intensity": 1,
    "provider": "ollama",
    "ollama_config": {
        "model": "qwen2.5-coder:7b",
        "fallback_models": ["phi4:latest"],
        "validation_model": "phi4:latest",
        "notes": "Project focused on security analysis and business logic consistency."
    },
    "openrouter_config": {
        "model": "openai/gpt-4o",
        "fallback_models": ["anthropic/claude-3-5-sonnet"],
        "validation_model": "anthropic/claude-3-5-sonnet",
        "OPENROUTER_API_KEY": "your_openrouter_api_key",
        "notes": "Project focused on security analysis."
    },
    "output": {
        "format": "md",
        "mode": "full",
        "scope": "all",
        "per_file": true
    },
    "kb": ["webapp", "blockchain"],
    "git_repo": "https://github.com/example/project.git"
}
```

### `provider`

Determines which LLM backend to use.

| Value | Behavior |
|---|---|
| `"ollama"` or Ollama URL | Uses `ollama_config` |
| `"openrouter"` or OpenRouter URL | Uses `openrouter_config` |
| omitted | Uses whichever config block is present (`openrouter_config` takes priority) |

### `accuracy_intensity`

| Value | Behavior |
|---|---|
| `1` | Fast. Large chunks, no validation pass. |
| `2` | Balanced. Medium chunks, validation pass on each chunk. |
| `3` | High precision. Small chunks, deep system prompt, validation pass. |

### `output`

| Field | Values | Description |
|---|---|---|
| `format` | `md` \| `json` \| `both` | Output file format |
| `mode` | `full` \| `vuln_only` \| `flow` \| `minimal` | Verbosity/focus of the report |
| `scope` | `all` \| `vuln_only_files` | Skip output for files with no vulnerability findings |
| `per_file` | `true` \| `false` | `false` aggregates all results into a single output file |
| `mirror_structure` | `false` \| `true` | `true` replicates the source directory tree under `output/` instead of flat layout |

### `kb`

List of subdirectory names under `kb/`. All `.md` and `.txt` files in those directories are concatenated and injected into the system prompt.

```
kb/
  webapp/
    owasp_top10.md
  blockchain/
    past_audit.txt
```

### `prompts/`

All prompt templates used during analysis. Edit these to customize behavior without modifying Python code.

**Scan mode prompts:**

| File | Purpose |
|---|---|
| `system_default.txt` | System prompt for intensity 1–2 |
| `system_deep.txt` | System prompt for intensity 3 |
| `system_validation.txt` | System prompt for validation pass |
| `system_merge.txt` | System prompt for final merge |
| `chunk_analysis.txt` | Main analysis prompt per chunk |
| `chunk_validation.txt` | Validation critique prompt |
| `chunk_summary.txt` | Rolling context summary prompt |
| `merge.txt` | Final consolidation prompt |

**Image mode prompts:**

| File | Purpose |
|---|---|
| `image_tag.txt` | Tag prompt for `image_mode: "tag"` — used for every image |
| `image_analysis.txt` | Analysis prompt for `image_mode: "analyze"` — used for still images |
| `video_frame_analysis.txt` | Per-frame prompt for video analysis; supports `{frame_index}` and `{total_frames}` placeholders |

---

## Image Mode

Image mode (`image_claw`) processes images and videos via a vision LLM. It runs separately from the code scan and uses its own config file. Two sub-modes are available, controlled by `"image_mode"` in the config.

### Quick start

```bash
# Install vision-capable model (local)
ollama pull gemma4:e2b

# Tag + cluster mode (default)
python3 root_claw.py images /path/to/photos config_images.json /path/to/output

# Forensic analysis mode (images + video)
python3 root_claw.py images /path/to/media config_images_analyze.json /path/to/output
```

---

### Sub-mode: `tag` (default)

Tags every image and organizes them into cluster folders by dominant tag.

#### How clustering works

1. Every image is tagged (5–8 comma-separated lowercase tags).
2. Tags accumulate in a frequency counter across all images.
3. When `cluster_threshold` images have been tagged, the top `n_clusters` tags become cluster labels.
4. All previously tagged images are retroactively sorted into the matching cluster folder.
5. Every subsequent image is assigned to its dominant cluster on arrival.

Files are **moved** by default (`"image_action": "move"`). Set to `"copy"` to keep originals in place.

#### `config_images.json`

```json
{
    "image_mode": "tag",
    "image_extensions": [".jpg", ".jpeg", ".png", ".webp"],
    "n_clusters": 10,
    "cluster_threshold": 100,
    "image_action": "move",
    "output_json": false,
    "prompt": "image_tag.txt",
    "provider": "ollama",
    "ollama_config": {
        "model": "gemma4:e2b",
        "fallback_models": []
    },
    "openrouter_config": {
        "model": "openai/gpt-4o",
        "fallback_models": [],
        "OPENROUTER_API_KEY": "your_key"
    }
}
```

| Field | Default | Description |
|---|---|---|
| `image_mode` | `"tag"` | Sub-mode: `"tag"` or `"analyze"` |
| `image_extensions` | jpg/jpeg/png/webp | Image file types to process |
| `n_clusters` | `10` | Number of cluster folders to create |
| `cluster_threshold` | `100` | Images to tag before clustering begins |
| `image_action` | `"move"` | `"move"` (destructive) or `"copy"` (safe) |
| `output_json` | `false` | Write `image_results_[ts].json` with full tag/cluster report |
| `prompt` | `"image_tag.txt"` | Filename in `prompts/` to use for tagging |
| `provider` | `"ollama"` | `"ollama"` or `"openrouter"` |

---

### Sub-mode: `analyze`

Produces one structured `.md` report per file. Supports both still images and video files (`.mp4`, `.mov`, `.avi`). No clustering or file moving — output documents are written to the output directory.

#### How video analysis works

1. For each video, `N` frames are extracted at evenly-spaced intervals across the full duration (default `video_frames: 5`).
2. Each frame is analyzed individually by the vision LLM using `prompts/video_frame_analysis.txt`.
3. Results are merged into a single `.md` file: `[timestamp]_[videoname]_analysis.md`.
4. Each frame section is labeled with its timestamp in seconds (e.g. `## Frame 2 [12.4s]`).

For still images, `prompts/image_analysis.txt` is used and the full response is written as-is.

#### `config_images_analyze.json`

```json
{
    "image_mode": "analyze",
    "image_extensions": [".jpg", ".jpeg", ".png", ".webp"],
    "video_extensions": [".mp4", ".mov", ".avi"],
    "video_frames": 5,
    "image_action": "copy",
    "provider": "ollama",
    "ollama_config": {
        "model": "gemma4:e2b",
        "fallback_models": []
    },
    "openrouter_config": {
        "model": "openai/gpt-4o",
        "fallback_models": [],
        "OPENROUTER_API_KEY": "your_key"
    }
}
```

| Field | Default | Description |
|---|---|---|
| `image_mode` | `"tag"` | Must be `"analyze"` to activate this sub-mode |
| `video_extensions` | mp4/mov/avi | Video file types to process |
| `video_frames` | `5` | Number of frames to extract and analyze per video |
| `image_action` | `"move"` | `"move"` or `"copy"` — only affects image files in analyze mode |
| `provider` | `"ollama"` | `"ollama"` or `"openrouter"` |

#### Output structure (analyze mode)

```
output_dir/
  image_state.json                       ← resume state
  20260601_120000_photo1_analysis.md     ← still image report
  20260601_120001_clip1_analysis.md      ← video report (all frames merged)
  20260601_120002_interview_analysis.md  ← audio transcript
```

Video report structure:

```markdown
# Video analysis: clip1.mp4
Frames analyzed: 5

## Frame 1 [3.2s]
...

## Frame 2 [12.4s]
...
```

Audio transcript structure:

```markdown
# Audio transcript: interview.mp3

Hello and welcome to the show...
```

---

### Audio Transcription (`image_mode: "analyze"` only)

Audio transcription is **opt-in**: it activates only when `audio_extensions` is present in the config. No config key = no change in behaviour.

Supported backends:

| `provider` | Backend | Requirement |
|---|---|---|
| `"whisper"` (default) | `openai-whisper` Python library, runs locally | `pip install openai-whisper` |
| `"openrouter"` | OpenRouter audio transcription REST endpoint | API key + model |

#### Config — Whisper (local)

```json
{
    "image_mode": "analyze",
    "audio_extensions": [".mp3", ".wav", ".m4a"],
    "audio_config": {
        "provider": "whisper",
        "whisper_model": "base"
    }
}
```

#### Config — OpenRouter STT (cloud)

```json
{
    "image_mode": "analyze",
    "audio_extensions": [".mp3", ".wav", ".m4a"],
    "audio_config": {
        "provider": "openrouter",
        "model": "openai/whisper-large-v3",
        "OPENROUTER_API_KEY": "your_key"
    }
}
```

| Field | Default | Description |
|---|---|---|
| `audio_extensions` | *(absent = disabled)* | File extensions to treat as audio; omit to disable entirely |
| `audio_config.provider` | `"whisper"` | `"whisper"` (local) or `"openrouter"` (cloud) |
| `audio_config.whisper_model` | `"base"` | Whisper model size: `tiny`, `base`, `small`, `medium`, `large` |
| `audio_config.model` | `"openai/whisper-large-v3"` | OpenRouter model ID (only for `provider: "openrouter"`) |
| `audio_config.OPENROUTER_API_KEY` | `""` | Required when using OpenRouter |

> **Note:** Audio is silently skipped in `image_mode: "tag"`. The LLM vision config (`ollama_config` / `openrouter_config`) is not used for audio — only `audio_config` is.

### Customizing the tag prompt

Edit `prompts/image_tag.txt` to change what the model focuses on — no Python changes needed.

Default prompt focuses on: subjects, scene type, action, mood, setting, visual style.

Examples of domain-specific prompts:

```
# Fashion
List 5-8 tags: clothing style, garment type, color palette, occasion, body coverage. Comma-separated lowercase only.

# Art / illustration
List 5-8 tags: art style, medium, mood, color palette, subject, composition. Comma-separated lowercase only.

# Product photos
List 5-8 tags: product category, color, background, shot angle, lighting. Comma-separated lowercase only.
```

### Output structure

```
output_dir/
  image_state.json              ← resume state (tagged images + cluster assignments)
  image_results_[ts].json       ← full report (only if output_json: true)
  woman/                        ← cluster folder (named after dominant tag)
    photo1.jpg
    photo3.png
  sitting/
    photo2.jpg
  indoor/
    ...
```

`image_results_[ts].json` structure:

```json
{
  "clusters": ["woman", "sitting", "indoor", ...],
  "cluster_counts": {"woman": 42, "sitting": 31, ...},
  "tag_frequency": {"woman": 98, "sitting": 74, "indoor": 61, ...},
  "total_tagged": 110,
  "images": [
    {
      "path": "/abs/path/to/photo.jpg",
      "name": "photo.jpg",
      "tags": ["woman", "sitting", "jeans"],
      "cluster": "woman"
    }
  ]
}

### Multi-directory input

Pass multiple directories as a comma-separated string:

```bash
python3 root_claw.py images /photos/batch1,/photos/batch2,/archive/old config_images.json /sorted
```

All directories are scanned recursively. Duplicate filenames across directories are handled safely (state key = absolute path).

### Recommended vision models (Ollama)

| Model | Size | Notes |
|---|---|---|
| `gemma4:e2b` | 7 GB | Best instruction following, slow |
| `gemma3:4b` | 3 GB | Good balance, faster |
| `moondream:latest` | 1.7 GB | Fast but limited prompt compliance |

---

## Output Structure (scan mode)

All scan output is written to `output/[timestamp]_[dir]/` relative to where the script is launched. The source directory is never modified.

* `[timestamp]_[filename]_rc.md` (or `.json`): Per-file analysis report.
* `[timestamp]_[dir]_files_rc.json`: Manifest of all scanned files and run metadata.
* `[timestamp]_[dir]_analyzed_rc.txt`: List of successfully processed files.

With `per_file: false`, a single `[timestamp]_[dir]_aggregate_rc.md` (or `.json`) is written instead. With `mirror_structure: true`, the output directory replicates the source tree layout.

## Technical Details

Root Claw implements a multi-pass approach for higher accuracy levels. At level 2 or 3, a validation model critiques each chunk's analysis before the final merge, reducing hallucinations and logical gaps.

Chunking respects line boundaries — no line is ever split mid-content. A rolling 200-character overlap between chunks preserves context continuity.

The tool always excludes its own output files (`*_rc.md`, `*_rc.json`, `*_rc.txt`) from re-scanning.

## Model Quality Disclaimer

The quality of the final analysis is strictly dependent on the capabilities of the selected LLMs. Run a test on a single known-vulnerable file before starting a full audit. Weak or non-coding-optimized models will produce superficial findings and hallucinations.

## License

MIT
