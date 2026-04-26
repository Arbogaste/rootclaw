# Root Claw

Root Claw is a tool designed to recursively scan and analyze source code files in a directory using Large Language Models via Ollama or OpenRouter. It is intended for codebase audits, vulnerability research, and architectural reviews where local execution and context awareness are required.

## Features

* **Resilient Execution**: Native timeout management for LLM requests to prevent indefinite hangs, with automatic fallback across a model chain.
* **Dynamic Configuration**: Hot-reloading of `config.json` between file analyses, allowing on-the-fly adjustment of models, notes, and ignore patterns.
* **Automated Ingestion**: Optional support for cloning remote Git repositories directly via configuration for immediate analysis.
* **Recursive Mapping**: Scans a directory and all subdirectories for specific file extensions.
* **Smart Chunking**: Automatically splits large files into overlapping chunks on line boundaries to fit model context windows while maintaining continuity.
* **Context Retention**: Passes summaries of previous findings to subsequent chunks to ensure the model understands the file state as it moves forward.
* **Accuracy Levels**: Adjustable intensity (1 to 3) that controls chunk size and enables additional validation passes for high-precision results.
* **Fallback Logic**: Configurable primary and fallback model chains for both Ollama and OpenRouter to ensure execution completes even if a specific model fails.
* **Non-Destructive Outputs**: Generates analysis reports alongside the original files without modifying the source code. Own output files are always excluded from re-scanning.
* **Customizable Prompts**: All prompts live in `prompts/` as plain text files. Edit or replace them without touching Python code.
* **Knowledge Base Injection**: Place `.md` or `.txt` files under `kb/<name>/` and reference them in config to inject domain knowledge (OWASP, past audits, etc.) into the system prompt.
* **Flexible Output**: Control output format, verbosity, scope, and aggregation per run via the `output` config block.
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
python3 root_claw.py [directory_to_analyze] [config.json]
```

`examples/` is a sample directory structure for testing:

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

## Output Structure

All output is written to `output/[timestamp]_[dir]/` relative to where the script is launched. The source directory is never modified.

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
