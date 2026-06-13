"""
image_claw.py — image/video/audio analysis and clustering mode for rootclaw.

Modes (set via config "image_mode"):
  "tag"      (default) — tag each image, cluster by top tags
  "analyze"            — produce full analysis document per image/video/audio

MP4/video support (when image_mode = "analyze"):
  Extracts N frames from each .mp4/.mov/.avi (default 5, configurable as "video_frames").
  Each frame is analyzed individually; results are merged into one document.

Audio support (when image_mode = "analyze" and audio_extensions is set in config):
  Transcribes .mp3/.wav/.m4a via Whisper (local) or OpenRouter STT.
  Each audio file produces one transcript .md document.
  Audio is silently ignored in "tag" mode.

Scans recursively. Multiple input dirs via comma-separated string.
State persisted in <output_dir>/image_state.json — safe to resume.

Usage:
  python3 root_claw.py images <dir> config_images.json [output_dir]
  python3 root_claw.py images <dir1,dir2> config_images.json [output_dir]
"""

import base64
import json
import logging
import shutil
import sys
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger("root_claw")

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".JPG", ".JPEG", ".PNG", ".WEBP"}
VIDEO_EXTS = {".mp4", ".MP4", ".mov", ".MOV", ".avi", ".AVI"}
AUDIO_EXTS = {".mp3", ".MP3", ".wav", ".WAV", ".m4a", ".M4A"}


# ---------------------------------------------------------------------------
# Vision-capable LLM wrappers (thin layer over rootclaw clients)
# ---------------------------------------------------------------------------

class OllamaVisionClient:
    def __init__(self, model: str, fallback_models: List[str], host: str = "http://localhost:11434"):
        self.model = model
        self.fallbacks = fallback_models
        try:
            from ollama import Client
            self.client = Client(host=host, timeout=300.0)
        except ImportError:
            logger.error("ollama library not found. pip install ollama")
            sys.exit(1)

    def tag(self, prompt: str, image_path: str) -> str:
        models = [m for m in [self.model] + self.fallbacks if m]
        for model in models:
            try:
                resp = self.client.chat(
                    model=model,
                    messages=[{
                        "role": "user",
                        "content": prompt,
                        "images": [image_path],
                    }]
                )
                return resp["message"]["content"].strip()
            except Exception as e:
                logger.warning(f"Vision model {model} failed: {e}")
        raise RuntimeError(f"All vision models failed for {image_path}")


class OpenRouterVisionClient:
    def __init__(self, model: str, fallback_models: List[str], api_key: str):
        self.model = model
        self.fallbacks = fallback_models
        self.api_key = api_key
        try:
            import requests
            self._requests = requests
        except ImportError:
            logger.error("requests library not found. pip install requests")
            sys.exit(1)

    def tag(self, prompt: str, image_path: str) -> str:
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        ext = Path(image_path).suffix.lower().lstrip(".")
        mime = f"image/{'jpeg' if ext in ('jpg','jpeg') else ext}"
        data_url = f"data:{mime};base64,{b64}"

        models = [m for m in [self.model] + self.fallbacks if m]
        for model in models:
            try:
                payload = {
                    "model": model,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": data_url}},
                        ]
                    }]
                }
                resp = self._requests.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    json=payload,
                    headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                    timeout=120,
                )
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"].strip()
            except Exception as e:
                logger.warning(f"OpenRouter vision model {model} failed: {e}")
        raise RuntimeError(f"All OpenRouter vision models failed for {image_path}")


# ---------------------------------------------------------------------------
# Clustering helpers
# ---------------------------------------------------------------------------

def compute_clusters(tag_counter: Counter, n: int) -> List[str]:
    return [tag for tag, _ in tag_counter.most_common(n)]


def dominant_cluster(image_tags: List[str], clusters: List[str]) -> str:
    counts = Counter(t for t in image_tags if t in clusters)
    return counts.most_common(1)[0][0] if counts else clusters[0]


def parse_tags(raw: str) -> List[str]:
    tags = [t.strip().lower().replace(" ", "_") for t in raw.split(",") if t.strip()]
    return tags[:8]


# ---------------------------------------------------------------------------
# Audio transcription backends
# ---------------------------------------------------------------------------

class WhisperTranscriber:
    """Local transcription via openai-whisper. pip install openai-whisper"""
    def __init__(self, model_name: str = "base"):
        try:
            import whisper as _whisper
        except ImportError:
            logger.error("openai-whisper not installed. pip install openai-whisper")
            sys.exit(1)
        try:
            import torch
            device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            device = "cpu"
        logger.info(f"Loading Whisper model '{model_name}' on {device}...")
        self._model = _whisper.load_model(model_name, device=device)

    def transcribe(self, audio_path: str) -> str:
        result = self._model.transcribe(str(audio_path))
        return result["text"].strip()


class OpenRouterSTTClient:
    """Cloud transcription via OpenRouter audio transcription endpoint."""
    def __init__(self, model: str, api_key: str):
        self.model = model or "openai/whisper-large-v3"
        self.api_key = api_key
        try:
            import requests
            self._requests = requests
        except ImportError:
            logger.error("requests not installed. pip install requests")
            sys.exit(1)

    def transcribe(self, audio_path: str) -> str:
        path = Path(audio_path)
        mime = "audio/wav" if path.suffix.lower() == ".wav" else "audio/mpeg"
        with open(audio_path, "rb") as f:
            resp = self._requests.post(
                "https://openrouter.ai/api/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                files={"file": (path.name, f, mime)},
                data={"model": self.model},
                timeout=300,
            )
        resp.raise_for_status()
        return resp.json().get("text", "").strip()


# ---------------------------------------------------------------------------
# ImageClaw
# ---------------------------------------------------------------------------

class ImageClaw:
    def __init__(self, input_dirs: str, config_path: str, output_dir: Optional[str] = None):
        raw_dirs = [d.strip() for d in input_dirs.split(",") if d.strip()]
        self.input_dirs: List[Path] = [Path(d).resolve() for d in raw_dirs]
        self.config_path = Path(config_path).resolve()
        self.cfg = self._load_config()

        if output_dir:
            self.output_dir = Path(output_dir).resolve()
        else:
            self.output_dir = self.input_dirs[0].parent / "analyzed"

        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.output_dir / "image_state.json"

        self.mode: str = self.cfg.get("image_mode", "tag")  # "tag" | "analyze"
        self.exts = set(self.cfg.get("image_extensions", list(IMAGE_EXTS)))
        self.video_exts = set(self.cfg.get("video_extensions", list(VIDEO_EXTS)))
        self.n_clusters: int = self.cfg.get("n_clusters", 10)
        self.threshold: int = self.cfg.get("cluster_threshold", 100)
        self.action: str = self.cfg.get("image_action", "move")
        self.output_json: bool = self.cfg.get("output_json", False)
        self.video_frames: int = self.cfg.get("video_frames", 5)
        self.audio_exts: set = set(self.cfg.get("audio_extensions", []))

        self.llm = self._init_llm()
        self.transcriber = self._init_transcriber() if self.audio_exts else None

        prompts_dir = Path(__file__).parent / "prompts"
        if self.mode == "analyze":
            self.tag_prompt = self._load_prompt_file(prompts_dir / "image_analysis.txt")
            self.video_frame_prompt = (prompts_dir / "video_frame_analysis.txt").read_text().strip()
        else:
            prompt_name = self.cfg.get("prompt", "image_tag.txt")
            self.tag_prompt = self._load_prompt_file(prompts_dir / prompt_name)
            self.video_frame_prompt = ""

    def _load_config(self) -> dict:
        with open(self.config_path) as f:
            return json.load(f)

    def _init_llm(self):
        provider = self.cfg.get("provider", "ollama")
        if provider == "openrouter":
            oc = self.cfg.get("openrouter_config", {})
            return OpenRouterVisionClient(
                model=oc.get("model", ""),
                fallback_models=oc.get("fallback_models", []),
                api_key=oc.get("OPENROUTER_API_KEY", ""),
            )
        oc = self.cfg.get("ollama_config", {})
        host = self.cfg.get("ollama_host", "http://localhost:11434")
        return OllamaVisionClient(
            model=oc.get("model", "gemma4:e2b"),
            fallback_models=oc.get("fallback_models", []),
            host=host,
        )

    def _init_transcriber(self):
        ac = self.cfg.get("audio_config", {})
        provider = ac.get("provider", "whisper")
        if provider == "openrouter":
            return OpenRouterSTTClient(
                model=ac.get("model", "openai/whisper-large-v3"),
                api_key=ac.get("OPENROUTER_API_KEY", ""),
            )
        return WhisperTranscriber(model_name=ac.get("whisper_model", "base"))

    def _load_prompt_file(self, path: Path) -> str:
        if path.exists():
            return path.read_text().strip()
        logger.warning(f"Prompt file not found: {path}, using default.")
        return (
            "List 5-8 short tags describing what you see in this image. "
            "Reply with ONLY a comma-separated list of lowercase tags, no explanation."
        )

    # ── video frame extraction ─────────────────────────────────────────────

    def _extract_frames(self, video_path: Path, n: int) -> List[Path]:
        try:
            import cv2
        except ImportError:
            logger.error("opencv-python not installed. pip install opencv-python")
            return []

        tmp_dir = Path(tempfile.mkdtemp(prefix="rootclaw_frames_"))
        cap = cv2.VideoCapture(str(video_path))
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 25

        if total <= 0:
            cap.release()
            return []

        # Pick N evenly spaced frame indices
        if n >= total:
            indices = list(range(total))
        else:
            step = total / n
            indices = [int(step * i + step / 2) for i in range(n)]

        saved = []
        for idx in indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if not ret:
                continue
            ts = idx / fps
            frame_path = tmp_dir / f"frame_{len(saved)+1:03d}_t{ts:.1f}s.jpg"
            cv2.imwrite(str(frame_path), frame)
            saved.append(frame_path)

        cap.release()
        logger.info(f"  extracted {len(saved)} frames from {video_path.name}")
        return saved

    # ── analysis mode ──────────────────────────────────────────────────────

    def _analyze_image(self, img_path: Path) -> str:
        return self.llm.tag(self.tag_prompt, str(img_path))

    def _analyze_video(self, video_path: Path) -> str:
        frames = self._extract_frames(video_path, self.video_frames)
        if not frames:
            return f"ERROR: could not extract frames from {video_path.name}"

        parts = [f"# Video analysis: {video_path.name}",
                 f"Frames analyzed: {len(frames)}\n"]

        for i, fp in enumerate(frames, 1):
            prompt = (self.video_frame_prompt
                      .replace("{frame_index}", str(i))
                      .replace("{total_frames}", str(len(frames))))
            try:
                result = self.llm.tag(prompt, str(fp))
            except Exception as e:
                result = f"ERROR: {e}"
            ts_label = fp.stem.split("_t")[-1] if "_t" in fp.stem else f"frame {i}"
            parts.append(f"## Frame {i} [{ts_label}]\n{result}\n")

        # cleanup temp frames
        for fp in frames:
            try:
                fp.unlink()
            except Exception:
                pass
        try:
            frames[0].parent.rmdir()
        except Exception:
            pass

        return "\n".join(parts)

    def _write_analysis_doc(self, source_path: Path, content: str) -> Path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = source_path.stem
        out_path = self.output_dir / f"{ts}_{stem}_analysis.md"
        out_path.write_text(content, encoding="utf-8")
        return out_path

    def _transcribe_audio_doc(self, audio_path: Path) -> str:
        transcript = self.transcriber.transcribe(str(audio_path))
        return f"# Audio transcript: {audio_path.name}\n\n{transcript}"

    def _run_analyze(self):
        """Analysis mode: produce one .md document per image/video."""
        all_files: List[Path] = []
        for d in self.input_dirs:
            if not d.is_dir():
                logger.warning(f"Input dir not found: {d}")
                continue
            for p in sorted(d.rglob("*")):
                is_visual = p.suffix in self.exts or p.suffix in self.video_exts
                is_audio = bool(self.transcriber) and p.suffix in self.audio_exts
                if (is_visual or is_audio):
                    if self.output_dir not in p.parents and p.parent != self.output_dir:
                        all_files.append(p)

        if not all_files:
            logger.error("No image/video files found.")
            return

        state = self._load_state()
        total = len(all_files)
        logger.info(f"Analyze mode: {total} files | output → {self.output_dir}")

        for i, fp in enumerate(all_files, 1):
            key = str(fp)
            if key in state.get("analyzed", {}):
                logger.info(f"[{i}/{total}] skip (done): {fp.name}")
                continue

            logger.info(f"[{i}/{total}] analyzing {fp.name} ...")
            try:
                if fp.suffix in self.video_exts:
                    content = self._analyze_video(fp)
                elif fp.suffix in self.audio_exts:
                    content = self._transcribe_audio_doc(fp)
                else:
                    raw = self._analyze_image(fp)
                    content = f"# Image analysis: {fp.name}\n\n{raw}"

                out = self._write_analysis_doc(fp, content)
                logger.info(f"  → {out.name}")

                state.setdefault("analyzed", {})[key] = str(out)
                self._save_state(state)

            except Exception as e:
                logger.warning(f"  [skip] {fp.name}: {e}")

        logger.info(f"\nDone. {len(state.get('analyzed', {}))} documents in {self.output_dir}")

    def _load_state(self) -> dict:
        if self.state_file.exists():
            return json.loads(self.state_file.read_text())
        return {"tagged": {}, "tag_counter": {}, "clusters": []}

    def _save_state(self, state: dict) -> None:
        self.state_file.write_text(json.dumps(state, indent=2))

    def _transfer(self, src: Path, dest_dir: Path) -> None:
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / src.name
        if dest.exists():
            return
        if not src.exists():
            return
        if self.action == "move":
            shutil.move(str(src), str(dest))
        else:
            shutil.copy2(str(src), str(dest))

    def _scan(self) -> List[Path]:
        seen = set()
        images = []
        for d in self.input_dirs:
            if not d.is_dir():
                logger.warning(f"Input dir not found, skipping: {d}")
                continue
            for p in sorted(d.rglob("*")):
                if p.suffix in self.exts and p not in seen:
                    # skip files already inside our own output dir
                    if self.output_dir in p.parents or p.parent == self.output_dir:
                        continue
                    seen.add(p)
                    images.append(p)
        return images

    def run(self):
        if self.mode == "analyze":
            self._run_analyze()
            return

        images = self._scan()
        if not images:
            logger.error(f"No images found in {[str(d) for d in self.input_dirs]}")
            sys.exit(1)

        state = self._load_state()
        tag_counter = Counter(state["tag_counter"])
        clusters: List[str] = state["clusters"]

        total = len(images)
        already = len(state["tagged"])
        logger.info(f"ImageClaw: {total} images found, {already} already tagged.")
        logger.info(f"Output: {self.output_dir} | Action: {self.action} | Threshold: {self.threshold}")

        for i, img in enumerate(images):
            key = str(img)  # absolute path — unique across multiple input dirs

            if key in state["tagged"]:
                tags = state["tagged"][key]
            else:
                logger.info(f"[{i+1}/{total}] tagging {img.name} ...")
                try:
                    raw = self.llm.tag(self.tag_prompt, str(img))
                    tags = parse_tags(raw)
                    logger.info(f"  tags: {', '.join(tags)}")
                except Exception as e:
                    logger.warning(f"  [skip] {img.name}: {e}")
                    tags = []

                state["tagged"][key] = tags
                for t in tags:
                    tag_counter[t] += 1
                state["tag_counter"] = dict(tag_counter)
                self._save_state(state)

            tagged_count = len(state["tagged"])

            if tagged_count >= self.threshold and not clusters:
                clusters = compute_clusters(tag_counter, self.n_clusters)
                state["clusters"] = clusters
                self._save_state(state)
                logger.info(f"[cluster] {self.n_clusters} clusters: {clusters}")
                for past_path, past_tags in state["tagged"].items():
                    past_img = Path(past_path)
                    if past_img.exists():
                        cl = dominant_cluster(past_tags, clusters)
                        self._transfer(past_img, self.output_dir / cl)

            if clusters:
                cl = dominant_cluster(tags, clusters) if tags else clusters[0]
                self._transfer(img, self.output_dir / cl)
                logger.info(f"  → {cl}/")

        if not clusters:
            logger.info(
                f"Only {len(state['tagged'])}/{self.threshold} images tagged. "
                "Need more images or lower cluster_threshold to cluster."
            )
        else:
            logger.info(f"\nDone. Clusters in {self.output_dir}:")
            for cl in clusters:
                n = len(list((self.output_dir / cl).glob("*"))) if (self.output_dir / cl).exists() else 0
                logger.info(f"  {cl:30s} {n} images")

        if self.output_json:
            self._write_json_report(state, clusters, tag_counter)

    def _write_json_report(self, state: dict, clusters: List[str], tag_counter: Counter) -> None:
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = self.output_dir / f"image_results_{ts}.json"

        images_out = []
        for path_str, tags in state["tagged"].items():
            cl = dominant_cluster(tags, clusters) if clusters and tags else None
            images_out.append({
                "path": path_str,
                "name": Path(path_str).name,
                "tags": tags,
                "cluster": cl,
            })

        cluster_counts = {}
        if clusters:
            for cl in clusters:
                cl_dir = self.output_dir / cl
                cluster_counts[cl] = len(list(cl_dir.glob("*"))) if cl_dir.exists() else 0

        report = {
            "clusters": clusters,
            "cluster_counts": cluster_counts,
            "tag_frequency": dict(tag_counter.most_common()),
            "total_tagged": len(state["tagged"]),
            "images": images_out,
        }

        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
        logger.info(f"JSON report: {out_path}")
