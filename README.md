# Root Claw

Root Claw is a tool designed to recursively scan and analyze source code files in a directory using Large Language Models via Ollama or OpenRouter. It is intended for codebase audits, vulnerability research, and architectural reviews where local execution and context awareness are required.

## Features

* **Resilient Execution**: Native timeout management for LLM requests to prevent indefinite hangs, with automatic fallback across a model chain.
* **Dynamic Configuration**: Hot-reloading of `config.json` between file analyses, allowing on-the-fly adjustment of models, notes, and ignore patterns.
* **Automated Ingestion**: Optional support for cloning remote Git repositories directly via configuration for immediate analysis.
* **Recursive Mapping**: Scans a directory and all subdirectories for specific file extensions.
* **Smart Chunking**: Automatically splits large files into overlapping chunks to fit model context windows while maintaining continuity.
* **Context Retention**: Passes summaries of previous findings to subsequent chunks to ensure the model understands the file state as it moves forward.
* **Accuracy Levels**: Adjustable intensity (1 to 3) that controls chunk size and enables additional validation passes for high-precision results.
* **Fallback Logic**: Configurable primary and fallback model chains to ensure execution completes even if a specific model fails or reaches resource limits.
* **Non-Destructive Outputs**: Generates analysis reports in Markdown alongside the original files without modifying the source code.

## Installation

The tool requires Python 3.8+ and the `ollama` Python library.

```bash
pip install ollama
```

You must have [Ollama](https://ollama.ai) installed and running locally.

## Usage

Run the script by providing a target directory and a configuration file:

```bash
python3 root_claw.py [directory_to_analyze] [config.json]
```

## Configuration

A JSON configuration file is required. Example `config.json`:

```json
{
    "extensions": [".java", ".py", ".sol"],
    "ignore": ["Avoid.java", "avoid.sol"],
    "ollama_config": {
        "model": "qwen2.5-coder:7b",
        "fallback_models": ["phi4:latest"],
        "validation_model": "phi4:latest",
        // OPTIONAL
        "notes": "Project focused on security analysis and business logic consistency."
    },
    // OPTIONALS
    "accuracy_intensity": 2, // (1 = Fast by default, 2 = Balanced, 3 = High precision)
    "ignore_file": ".gitignore",
    "git_repo": "https://github.com/example/project.git"
}
```

* **extensions**: List of file extensions to include.
* **ignore**: List of patterns to skip.
* **accuracy_intensity**: 1 (Fast), 2 (Balanced), 3 (High precision).
* **ollama_config**: Model selection and project-wide context notes.

## Output Structure

For every file analyzed, Root Claw generates a Markdown file with the prefix `[timestamp]_[filename]_rc.md`. Additionally, it produces:

* `[timestamp]_[dir]_files_rc.json`: A manifest of all scanned files and audit metadata.
* `[timestamp]_[dir]_analyzed_rc.txt`: A simple list of files successfully processed for quick progress tracking.

## Technical Details

Root Claw implements a multi-pass approach for higher accuracy levels. At level 2 or 3, a second "Validation Model" is invoked to critique the initial analysis of each chunk, correcting potential hallucinations or logical gaps before the final merge. 

The tool uses a recursive context passing mechanism where a two-sentence summary of the current chunk is generated and fed into the prompt of the following chunk, providing a rolling context window.

## Model Quality Disclaimer

The quality of the final analysis is strictly dependent on the capabilities of the Large Language Models selected in the configuration. It is highly recommended to perform a test run on a single, known-vulnerable file to verify the model's reasoning capabilities before starting a full-scale audit. Using weak or non-coding optimized models will result in superficial findings and potential hallucinations.

## License

MIT
