import os
import sys
import json
import time
import signal
import hashlib
import logging
import fnmatch
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("root_claw.log")
    ]
)
logger = logging.getLogger("root_claw")

PROMPTS_DIR = os.path.join(os.path.dirname(__file__), "prompts")
KB_DIR = os.path.join(os.path.dirname(__file__), "kb")


# ---------------------------------------------------------------------------
# Prompt loader
# ---------------------------------------------------------------------------

def load_prompt(name: str) -> str:
    path = os.path.join(PROMPTS_DIR, name)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    raise FileNotFoundError(f"Prompt file not found: {path}")


def render_prompt(name: str, **kwargs) -> str:
    template = load_prompt(name)
    return template.format(**kwargs)


# ---------------------------------------------------------------------------
# KB loader
# ---------------------------------------------------------------------------

def load_kb(kb_names: List[str]) -> str:
    """Load and concatenate KB files from kb/ subdirectories matching names."""
    if not kb_names:
        return ""
    sections = []
    for name in kb_names:
        kb_path = os.path.join(KB_DIR, name)
        if not os.path.isdir(kb_path):
            logger.warning(f"KB directory not found: {kb_path}")
            continue
        for fname in sorted(os.listdir(kb_path)):
            fpath = os.path.join(kb_path, fname)
            if os.path.isfile(fpath) and fname.endswith((".md", ".txt")):
                with open(fpath, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read().strip()
                if content:
                    sections.append(f"[KB:{name}/{fname}]\n{content}")
    return "\n\n".join(sections)


# ---------------------------------------------------------------------------
# Config dataclasses
# ---------------------------------------------------------------------------

@dataclass
class ModelConfig:
    model: str
    fallback_models: List[str] = field(default_factory=list)
    validation_model: Optional[str] = None
    validation_fallback_models: List[str] = field(default_factory=list)
    notes: str = ""
    api_key: Optional[str] = None


@dataclass
class OutputConfig:
    format: str = "md"              # md | json | both
    mode: str = "full"              # full | vuln_only | flow | minimal
    scope: str = "all"              # all | vuln_only_files
    per_file: bool = True           # True = one output per file, False = aggregate
    mirror_structure: bool = False  # False = flat in output/run_dir/, True = mirrors source tree (wave 3)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OutputConfig":
        return cls(
            format=data.get("format", "md"),
            mode=data.get("mode", "full"),
            scope=data.get("scope", "all"),
            per_file=data.get("per_file", True),
            mirror_structure=data.get("mirror_structure", False),
        )


@dataclass
class Config:
    extensions: List[str]
    ignore: List[str] = field(default_factory=list)
    ignore_file: str = ""
    accuracy_intensity: int = 1
    git_repo: str = ""
    provider: Optional[str] = None          # "ollama" | "openrouter" | explicit URL
    ollama_config: Optional[ModelConfig] = None
    openrouter_config: Optional[ModelConfig] = None
    output: OutputConfig = field(default_factory=OutputConfig)
    kb: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        ollama_data = data.get("ollama_config")
        openrouter_data = data.get("openrouter_config")

        ollama_cfg = None
        if ollama_data:
            ollama_cfg = ModelConfig(
                model=ollama_data.get("model", ""),
                fallback_models=ollama_data.get("fallback_models", []),
                validation_model=ollama_data.get("validation_model"),
                validation_fallback_models=ollama_data.get("validation_fallback_models", []),
                notes=ollama_data.get("notes", ""),
            )

        openrouter_cfg = None
        if openrouter_data:
            openrouter_cfg = ModelConfig(
                model=openrouter_data.get("model", ""),
                fallback_models=openrouter_data.get("fallback_models", []),
                validation_model=openrouter_data.get("validation_model"),
                validation_fallback_models=openrouter_data.get("validation_fallback_models", []),
                notes=openrouter_data.get("notes", ""),
                api_key=openrouter_data.get("OPENROUTER_API_KEY"),
            )

        output_cfg = OutputConfig.from_dict(data.get("output", {}))

        return cls(
            extensions=data.get("extensions", []),
            ignore=data.get("ignore", []),
            ignore_file=data.get("ignore_file", ""),
            accuracy_intensity=data.get("accuracy_intensity", 1),
            git_repo=data.get("git_repo", ""),
            provider=data.get("provider"),
            ollama_config=ollama_cfg,
            openrouter_config=openrouter_cfg,
            output=output_cfg,
            kb=data.get("kb", []),
        )

    def active_model_config(self) -> Optional[ModelConfig]:
        """Return the ModelConfig for the active provider."""
        p = self._resolve_provider()
        if p == "openrouter":
            return self.openrouter_config
        return self.ollama_config

    def _resolve_provider(self) -> str:
        if self.provider:
            if self.provider == "openrouter" or self.provider.startswith("https://openrouter"):
                return "openrouter"
            return "ollama"
        if self.openrouter_config:
            return "openrouter"
        return "ollama"


# ---------------------------------------------------------------------------
# LLM clients
# ---------------------------------------------------------------------------

class OllamaClient:
    def __init__(self, config: ModelConfig, host: str = "http://localhost:11434", timeout: int = 180):
        self.config = config
        try:
            from ollama import Client
            self.client = Client(host=host, timeout=float(timeout))
        except ImportError:
            logger.error("Ollama library not found. Install with 'pip install ollama'.")
            sys.exit(1)

    def generate(self, prompt: str, system_prompt: str = "", use_validation: bool = False) -> str:
        primary = self.config.validation_model if use_validation and self.config.validation_model else self.config.model
        fallbacks = self.config.validation_fallback_models if use_validation else self.config.fallback_models
        models_to_try = [m for m in [primary] + fallbacks if m]

        last_error = None
        for model in models_to_try:
            try:
                logger.info(f"Ollama model: {model}")
                response = self.client.chat(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    options={"num_ctx": 4096}
                )
                return response["message"]["content"]
            except Exception as e:
                logger.warning(f"Ollama model {model} failed: {e}")
                last_error = e
        raise Exception(f"All Ollama models failed. Last error: {last_error}")


class OpenRouterClient:
    def __init__(self, config: ModelConfig, timeout: int = 180):
        self.config = config
        self.timeout = timeout
        if not config.api_key:
            logger.error("OpenRouter API key missing in openrouter_config.OPENROUTER_API_KEY")
            sys.exit(1)
        try:
            import requests
            self._requests = requests
        except ImportError:
            logger.error("requests library not found. Install with 'pip install requests'.")
            sys.exit(1)

    def _call(self, model: str, prompt: str, system_prompt: str) -> str:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt}
            ]
        }
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json"
        }
        resp = self._requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=self.timeout
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def generate(self, prompt: str, system_prompt: str = "", use_validation: bool = False) -> str:
        primary = self.config.validation_model if use_validation and self.config.validation_model else self.config.model
        fallbacks = self.config.validation_fallback_models if use_validation else self.config.fallback_models
        models_to_try = [m for m in [primary] + fallbacks if m]

        last_error = None
        for model in models_to_try:
            try:
                logger.info(f"OpenRouter model: {model}")
                return self._call(model, prompt, system_prompt)
            except Exception as e:
                logger.warning(f"OpenRouter model {model} failed: {e}")
                last_error = e
        raise Exception(f"All OpenRouter models failed. Last error: {last_error}")


# ---------------------------------------------------------------------------
# RootClaw
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Profile detection
# ---------------------------------------------------------------------------

_EXT_TO_PROFILE: Dict[str, str] = {
    ".sol": "sol",
    ".rs": "rust",
    ".ts": "ts", ".tsx": "ts",
    ".js": "ts", ".jsx": "ts",
    ".py": "py", ".java": "java",
}
_PROFILE_TO_EXTENSIONS: Dict[str, List[str]] = {
    "sol":  [".sol"],
    "rust": [".rs"],
    "ts":   [".ts", ".tsx", ".js", ".jsx"],
    "py":   [".py"],
    "java": [".java"],
}
_IGNORE_DIRS = {"node_modules", ".git", "target", "dist", "build", "__pycache__", ".venv"}


def detect_dominant_extension(target_dir: str) -> Dict[str, Any]:
    """Count file extensions in target_dir. Returns ALL present profiles, not just dominant.

    Every language found (even 1 file) is included in extensions — user gets full picture.
    Only extensions in _EXT_TO_PROFILE are considered (source code, not binaries).

    Returns dict:
      profile:    str  — dominant profile name for display only
      extensions: list — ALL extensions present in the repo
      counts:     dict — raw counts per profile
      total:      int  — total relevant files found
    """
    ext_counts: Dict[str, int] = {}   # per raw extension (e.g. ".sol": 12)
    profile_counts: Dict[str, int] = {}  # per profile (e.g. "sol": 12)

    for root, dirs, files in os.walk(target_dir):
        dirs[:] = [d for d in dirs if d not in _IGNORE_DIRS]
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext in _EXT_TO_PROFILE:
                ext_counts[ext] = ext_counts.get(ext, 0) + 1
                profile = _EXT_TO_PROFILE[ext]
                profile_counts[profile] = profile_counts.get(profile, 0) + 1

    total = sum(ext_counts.values())
    if total == 0:
        return {"profile": "unknown", "extensions": [], "counts": {}, "total": 0}

    dominant = max(profile_counts, key=profile_counts.get)
    # Include ALL extensions that appear at least once
    extensions = sorted(ext_counts.keys())

    return {
        "profile": dominant,
        "extensions": extensions,
        "counts": profile_counts,
        "total": total,
    }


class RootClaw:
    def __init__(self, target_dir: str, config_path: str):
        self.target_dir = os.path.abspath(target_dir)
        self.config_path = os.path.abspath(config_path)
        self.start_time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.config = self._load_config(self.config_path)

        # Auto-detect extensions when none configured — no regression if extensions set
        if not self.config.extensions:
            detected = detect_dominant_extension(self.target_dir)
            self.config.extensions = detected["extensions"]
            logger.info(
                "Auto-detected profile '%s' from %s files: %s",
                detected["profile"], detected["total"], detected["counts"],
            )
            if not self.config.extensions:
                logger.error("No recognized source files in %s", self.target_dir)
                sys.exit(1)

        self._init_llm()

        dir_name = os.path.basename(self.target_dir.rstrip(os.sep)) or "root"
        # Stable run_tag: target hash + dir name → same target always resumes same dir.
        # Use only first 8 chars of hash to keep paths short.
        target_hash = hashlib.sha1(self.target_dir.encode()).hexdigest()[:8]
        self.run_tag = f"{dir_name}_{target_hash}"

        # All outputs go into output/<run_tag>/ relative to cwd
        self.output_dir = os.path.join(os.getcwd(), "output", self.run_tag)
        os.makedirs(self.output_dir, exist_ok=True)

        # files_rc.json stamped with start_time so each invocation logs its own run
        self.files_json_path = os.path.join(self.output_dir, f"{self.start_time_str}_files_rc.json")
        self.analyzed_txt_path = os.path.join(self.output_dir, f"{self.run_tag}_analyzed_rc.txt")
        self.ignore_patterns = self._load_ignore_patterns()

        # Aggregate output collector (used when per_file=False)
        self._aggregate_results: List[Dict[str, Any]] = []

    def _init_llm(self):
        provider = self.config._resolve_provider()
        cfg = self.config.active_model_config()
        if not cfg:
            logger.error("No model config found (ollama_config or openrouter_config required).")
            sys.exit(1)

        if provider == "openrouter":
            self.llm = OpenRouterClient(cfg)
        else:
            host = self.config.provider if self.config.provider and self.config.provider.startswith("http") else "http://localhost:11434"
            self.llm = OllamaClient(cfg, host=host)

        logger.info(f"Provider: {provider}, model: {cfg.model}")

    def _load_config(self, path: str) -> Config:
        try:
            with open(path, "r") as f:
                data = json.load(f)
            return Config.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load config from {path}: {e}")
            sys.exit(1)

    def _load_ignore_patterns(self) -> List[str]:
        patterns = self.config.ignore[:]
        if self.config.ignore_file and os.path.exists(self.config.ignore_file):
            with open(self.config.ignore_file, "r") as f:
                patterns.extend([l.strip() for l in f if l.strip() and not l.startswith("#")])
        # Always ignore rootclaw own output files
        patterns.extend(["*_rc.md", "*_rc.json", "*_rc.txt"])
        return patterns

    def should_ignore(self, path: str) -> bool:
        rel_path = os.path.relpath(path, self.target_dir)
        filename = os.path.basename(path)

        if not any(path.endswith(ext) for ext in self.config.extensions):
            return True

        for pattern in self.ignore_patterns:
            if fnmatch.fnmatch(filename, pattern) or fnmatch.fnmatch(rel_path, pattern):
                return True
        return False

    def scan_files(self) -> List[str]:
        logger.info(f"Scanning: {self.target_dir}")
        file_list = []
        for root, dirs, files in os.walk(self.target_dir):
            for file in files:
                full_path = os.path.join(root, file)
                if not self.should_ignore(full_path):
                    file_list.append(full_path)
        logger.info(f"Found {len(file_list)} files.")
        return file_list

    def _handle_git_clone(self):
        if not self.config.git_repo:
            return
        repo_name = self.config.git_repo.split("/")[-1].replace(".git", "")
        clone_target = os.path.join(self.target_dir, f"repo_{repo_name}_{self.start_time_str}")
        logger.info(f"Cloning {self.config.git_repo} into {clone_target}")
        try:
            import subprocess
            subprocess.run(["git", "clone", self.config.git_repo, clone_target], check=True, capture_output=True)
            self.target_dir = clone_target
            logger.info("Clone successful.")
        except Exception as e:
            logger.error(f"Clone failed: {e}")

    def chunk_content(self, content: str, max_chars: int = 4000) -> List[str]:
        if len(content) <= max_chars:
            return [content]

        chunks = []
        lines = content.splitlines(keepends=True)
        current = []
        current_len = 0
        overlap_lines = []

        for line in lines:
            current.append(line)
            current_len += len(line)
            if current_len >= max_chars:
                chunk_text = "".join(current)
                chunks.append(chunk_text)
                # keep last ~200 chars worth of lines as overlap
                overlap_lines = []
                overlap_len = 0
                for l in reversed(current):
                    overlap_lines.insert(0, l)
                    overlap_len += len(l)
                    if overlap_len >= 200:
                        break
                current = overlap_lines[:]
                current_len = sum(len(l) for l in current)

        if current:
            chunks.append("".join(current))
        return chunks

    def _build_system_prompt(self, intensity: int) -> str:
        if intensity >= 3:
            return load_prompt("system_deep.txt").strip()
        return load_prompt("system_default.txt").strip()

    def _kb_context(self) -> str:
        return load_kb(self.config.kb)

    def analyze_file(self, file_path: str) -> Optional[Dict[str, Any]]:
        logger.info(f"Analyzing: {file_path}")
        notes = self.config.active_model_config().notes

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            intensity = self.config.accuracy_intensity
            max_chars = 6000 if intensity == 1 else (4000 if intensity == 2 else 2500)
            chunks = self.chunk_content(content, max_chars=max_chars)

            kb_context = self._kb_context()
            system_prompt = self._build_system_prompt(intensity)
            if kb_context:
                system_prompt += f"\n\nKnowledge Base:\n{kb_context}"

            filename = os.path.basename(file_path)
            extension = os.path.splitext(file_path)[1]

            chunk_results = []
            previous_summary = "None (first chunk)"

            for i, chunk in enumerate(chunks):
                logger.info(f"  [{i+1}/{len(chunks)}] chunk...")

                prompt = render_prompt(
                    "chunk_analysis.txt",
                    filename=filename,
                    extension=extension,
                    notes=notes,
                    previous_summary=previous_summary,
                    chunk_index=i + 1,
                    chunk_total=len(chunks),
                    chunk_content=chunk,
                )

                result = self.llm.generate(prompt, system_prompt)

                if intensity >= 2:
                    val_prompt = render_prompt("chunk_validation.txt", analysis=result)
                    val_system = load_prompt("system_validation.txt").strip()
                    result = self.llm.generate(val_prompt, val_system, use_validation=True)

                chunk_results.append(result)

                if i < len(chunks) - 1:
                    sum_prompt = render_prompt("chunk_summary.txt", analysis=result)
                    previous_summary = self.llm.generate(sum_prompt, "Brief summary of code state.")

            final_md = "\n\n---\n\n".join(chunk_results)

            logger.info(f"  Merging results for {filename}")
            merge_prompt = render_prompt("merge.txt", filename=filename, chunks=final_md)
            merge_system = load_prompt("system_merge.txt").strip()
            final_md = self.llm.generate(merge_prompt, merge_system)

            result_data = {
                "file": os.path.relpath(file_path, self.target_dir),
                "analysis": final_md,
            }

            self._write_file_output(file_path, final_md, result_data)
            return result_data

        except Exception as e:
            logger.error(f"Failed to analyze {file_path}: {e}")
            return None

    def _has_vulnerabilities(self, analysis: str) -> bool:
        """Heuristic: check if analysis text mentions vulnerability findings."""
        vuln_keywords = ["vulnerabilit", "vuln", "cve", "exploit", "injection", "overflow",
                         "unsafe", "insecure", "attack", "malicious", "risk", "flaw", "bypass"]
        lower = analysis.lower()
        return any(kw in lower for kw in vuln_keywords)

    def _output_path_for(self, file_path: str) -> str:
        """Return the output directory for a given source file."""
        out = self.config.output
        if out.mirror_structure:
            # Wave 3: replicate source tree under output_dir
            rel_dir = os.path.dirname(os.path.relpath(file_path, self.target_dir))
            dest = os.path.join(self.output_dir, rel_dir)
            os.makedirs(dest, exist_ok=True)
            return dest
        return self.output_dir

    def _write_file_output(self, file_path: str, final_md: str, result_data: Dict[str, Any]):
        out = self.config.output
        file_base = os.path.basename(file_path).replace(".", "_")
        ts = self.start_time_str

        # scope: vuln_only_files — skip writing if no vulns found
        if out.scope == "vuln_only_files" and not self._has_vulnerabilities(final_md):
            logger.info(f"  Skipping output (no vulnerabilities, scope=vuln_only_files)")
            return

        if not out.per_file:
            self._aggregate_results.append(result_data)
            return

        dest_dir = self._output_path_for(file_path)

        if out.format in ("md", "both"):
            md_path = os.path.join(dest_dir, f"{ts}_{file_base}_rc.md")
            with open(md_path, "w") as f:
                f.write(self._apply_mode_filter(final_md, out.mode))

        if out.format in ("json", "both"):
            json_path = os.path.join(dest_dir, f"{ts}_{file_base}_rc.json")
            with open(json_path, "w") as f:
                json.dump(result_data, f, indent=4)

        with open(self.analyzed_txt_path, "a") as f:
            f.write(f"{os.path.relpath(file_path, self.target_dir)}\n")

    def _apply_mode_filter(self, analysis: str, mode: str) -> str:
        """Apply output verbosity mode. For now vuln_only prepends a filter instruction header."""
        if mode == "minimal":
            return f"<!-- mode:minimal -->\n{analysis}"
        if mode == "vuln_only":
            return f"<!-- mode:vuln_only — vulnerabilities section only -->\n{analysis}"
        if mode == "flow":
            return f"<!-- mode:flow — architectural flow description -->\n{analysis}"
        return analysis

    def _write_aggregate_output(self):
        if not self._aggregate_results:
            return
        out = self.config.output
        ts = self.start_time_str

        if out.format in ("md", "both"):
            md_path = os.path.join(self.output_dir, f"{self.run_tag}_aggregate_rc.md")
            with open(md_path, "w") as f:
                for r in self._aggregate_results:
                    f.write(f"# {r['file']}\n\n")
                    f.write(self._apply_mode_filter(r["analysis"], out.mode))
                    f.write("\n\n---\n\n")

        if out.format in ("json", "both"):
            json_path = os.path.join(self.output_dir, f"{self.run_tag}_aggregate_rc.json")
            with open(json_path, "w") as f:
                json.dump(self._aggregate_results, f, indent=4)

        with open(self.analyzed_txt_path, "a") as f:
            for r in self._aggregate_results:
                f.write(f"{r['file']}\n")

    def _checkpoint_path(self) -> str:
        return os.path.join(self.output_dir, f"{self.run_tag}_checkpoint.txt")

    def _load_checkpoint(self) -> set:
        """Return set of relative file paths already analyzed in this run."""
        path = self._checkpoint_path()
        if not os.path.exists(path):
            return set()
        with open(path, "r") as f:
            return {line.strip() for line in f if line.strip()}

    def _save_checkpoint(self, file_path: str):
        rel = os.path.relpath(file_path, self.target_dir)
        with open(self._checkpoint_path(), "a") as f:
            f.write(rel + "\n")

    def run(self, fresh: bool = False):
        start_ts = time.time()
        self._handle_git_clone()
        file_list = self.scan_files()

        if fresh and os.path.exists(self._checkpoint_path()):
            os.remove(self._checkpoint_path())
            logger.info("--fresh: checkpoint cleared, full rescan.")

        done = self._load_checkpoint()
        if done:
            logger.info(f"Resuming: {len(done)} files already done (checkpoint found).")

        state = {
            "start_time": datetime.now().isoformat(),
            "target_dir": self.target_dir,
            "files_to_analyze": [os.path.relpath(p, self.target_dir) for p in file_list],
            "config": asdict(self.config),
        }
        with open(self.files_json_path, "w") as f:
            json.dump(state, f, indent=4)

        skipped = 0

        # Save state on SIGINT/SIGTERM
        def _graceful_exit(signum, frame):
            logger.info(f"Signal {signum} received — saving state and exiting.")
            state["end_time"] = datetime.now().isoformat()
            state["duration_seconds"] = time.time() - start_ts
            state["interrupted"] = True
            with open(self.files_json_path, "w") as f:
                json.dump(state, f, indent=4)
            logger.info(f"Checkpoint saved at {self._checkpoint_path()} — re-run same command to resume.")
            sys.exit(0)

        signal.signal(signal.SIGINT, _graceful_exit)
        signal.signal(signal.SIGTERM, _graceful_exit)

        for i, file_path in enumerate(file_list):
            rel = os.path.relpath(file_path, self.target_dir)
            if rel in done:
                logger.info(f"Progress: {i+1}/{len(file_list)} | SKIP (already done): {rel}")
                skipped += 1
                continue

            logger.info(f"Progress: {i+1}/{len(file_list)} | Reloading config...")
            self.config = self._load_config(self.config_path)
            self._init_llm()
            self.ignore_patterns = self._load_ignore_patterns()

            self.analyze_file(file_path)
            self._save_checkpoint(file_path)

        if skipped:
            logger.info(f"Resumed run: skipped {skipped} already-analyzed files.")

        if not self.config.output.per_file:
            self._write_aggregate_output()

        state["end_time"] = datetime.now().isoformat()
        state["duration_seconds"] = time.time() - start_ts
        with open(self.files_json_path, "w") as f:
            json.dump(state, f, indent=4)

        logger.info(f"Done. Results in {self.output_dir}")


def simulate(file_path: str, config_path: str, target_function: str, goal: str):
    """Step-by-step execution simulation for a specific function/scenario."""
    import tempfile, os

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    with open(config_path, "r") as f:
        data = json.load(f)
    cfg = Config.from_dict(data)

    if cfg._resolve_provider() == "openrouter":
        llm = OpenRouterClient(cfg.openrouter_config)
    else:
        host = cfg.provider if cfg.provider and cfg.provider.startswith("http") else "http://localhost:11434"
        llm = OllamaClient(cfg.ollama_config, host=host)

    prompt = render_prompt(
        "simulate.txt",
        filename=os.path.basename(file_path),
        target=target_function,
        goal=goal,
        chunk_content=content[:6000],
    )
    system = "You are a security researcher simulating code execution to validate an exploit hypothesis. Be precise and use exact variable names."
    result = llm.generate(prompt, system)

    out_path = f"simulate_{os.path.basename(file_path)}_{target_function[:20]}.md"
    with open(out_path, "w") as f:
        f.write(f"# Simulation: {target_function}\n\nGoal: {goal}\n\n---\n\n{result}")
    print(f"Simulation written: {out_path}")
    print(result)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python3 root_claw.py scan <dir> <config_file>")
        print("  python3 root_claw.py images <dir> <config_images.json> [output_dir]")
        print("  python3 root_claw.py simulate <file> <config_file> <function> <goal>")
        sys.exit(1)

    mode = sys.argv[1]

    if mode == "simulate":
        if len(sys.argv) < 6:
            print("Usage: python3 root_claw.py simulate <file> <config> <function> <goal>")
            sys.exit(1)
        simulate(sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5])

    elif mode == "images":
        if len(sys.argv) < 4:
            print("Usage: python3 root_claw.py images <dir> <config_images.json> [output_dir]")
            sys.exit(1)
        from image_claw import ImageClaw
        out = sys.argv[4] if len(sys.argv) > 4 else None
        ImageClaw(sys.argv[2], sys.argv[3], out).run()

    else:
        # legacy: root_claw.py <dir> <config> or root_claw.py scan <dir> <config> [--fresh]
        if mode == "scan":
            target, config = sys.argv[2], sys.argv[3]
            fresh = "--fresh" in sys.argv[4:]
        elif len(sys.argv) >= 3:
            target, config = sys.argv[1], sys.argv[2]
            fresh = "--fresh" in sys.argv[3:]
        else:
            print("Usage: python3 root_claw.py scan <dir> <config_file> [--fresh]")
            sys.exit(1)
        app = RootClaw(target, config)
        app.run(fresh=fresh)
