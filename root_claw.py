import os
import sys
import json
import time
import logging
import fnmatch
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("root_claw.log")
    ]
)
logger = logging.getLogger("root_claw")

@dataclass
class OllamaConfig:
    model: str
    fallback_models: List[str] = field(default_factory=list)
    validation_model: Optional[str] = None
    validation_fallback_models: List[str] = field(default_factory=list)
    notes: str = ""

@dataclass
class Config:
    extensions: List[str]
    ignore: List[str] = field(default_factory=list)
    ignore_file: str = ""
    accuracy_intensity: int = 1
    git_repo: str = ""
    ollama_config: Optional[OllamaConfig] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Config":
        ollama_data = data.get("ollama_config")
        ollama_config = OllamaConfig(**ollama_data) if ollama_data else None
        return cls(
            extensions=data.get("extensions", []),
            ignore=data.get("ignore", []),
            ignore_file=data.get("ignore_file", ""),
            accuracy_intensity=data.get("accuracy_intensity", 1),
            git_repo=data.get("git_repo", ""),
            ollama_config=ollama_config
        )

class LLMClient:
    """Robust wrapper for Ollama communication with fallback logic and native timeouts."""
    def __init__(self, config: OllamaConfig, timeout: int = 180):
        self.config = config
        self.timeout = timeout
        try:
            from ollama import Client
            # Use native timeout provided by the library (passes to httpx)
            self.client = Client(host="http://localhost:11434", timeout=float(self.timeout))
        except ImportError:
            logger.error("Ollama library not found. Please install with 'pip install ollama'.")
            sys.exit(1)

    def generate(self, prompt: str, system_prompt: str = "", use_validation: bool = False) -> str:
        """Call LLM with internal fallback logic."""
        primary = self.config.validation_model if use_validation and self.config.validation_model else self.config.model
        fallbacks = self.config.validation_fallback_models if use_validation else self.config.fallback_models
        
        models_to_try = [primary] + fallbacks
        
        last_error = None
        for model in models_to_try:
            if not model: continue
            try:
                logger.info(f"Attempting generation with model: {model}")
                response = self.client.chat(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": prompt}
                    ],
                    options={"num_ctx": 4096}
                )
                return response['message']['content']
            except Exception as e:
                logger.warning(f"Model {model} failed or timed out: {e}")
                last_error = e
                continue
        
        raise Exception(f"All models failed. Last error: {last_error}")

class RootClaw:
    def __init__(self, target_dir: str, config_path: str):
        self.target_dir = os.path.abspath(target_dir)
        self.config_path = os.path.abspath(config_path)
        self.start_time_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.config = self._load_config(self.config_path)
        self._init_llm()
        
        # Paths for state tracking
        dir_name = os.path.basename(self.target_dir.rstrip(os.sep)) or "root"
        self.files_json_path = os.path.join(self.target_dir, f"{self.start_time_str}_{dir_name}_files_rc.json")
        self.analyzed_txt_path = os.path.join(self.target_dir, f"{self.start_time_str}_{dir_name}_analyzed_rc.txt")
        self.ignore_patterns = self._load_ignore_patterns()

    def _init_llm(self):
        """Initialize or refresh the LLM client."""
        if self.config.ollama_config:
            self.llm = LLMClient(self.config.ollama_config)
        else:
            self.llm = None

    def _load_config(self, path: str) -> Config:
        try:
            with open(path, 'r') as f:
                data = json.load(f)
            return Config.from_dict(data)
        except Exception as e:
            logger.error(f"Failed to load config from {path}: {e}")
            sys.exit(1)

    def _load_ignore_patterns(self) -> List[str]:
        patterns = self.config.ignore[:]
        if self.config.ignore_file and os.path.exists(self.config.ignore_file):
            with open(self.config.ignore_file, 'r') as f:
                patterns.extend([line.strip() for line in f if line.strip() and not line.startswith('#')])
        return patterns

    def should_ignore(self, path: str) -> bool:
        rel_path = os.path.relpath(path, self.target_dir)
        filename = os.path.basename(path)
        
        # Check extensions
        if not any(path.endswith(ext) for ext in self.config.extensions):
            return True
        
        # Check ignore patterns
        for pattern in self.ignore_patterns:
            if fnmatch.fnmatch(filename, pattern) or fnmatch.fnmatch(rel_path, pattern):
                return True
        return False

    def scan_files(self) -> List[str]:
        logger.info(f"Scanning directory: {self.target_dir}")
        file_list = []
        for root, dirs, files in os.walk(self.target_dir):
            for file in files:
                full_path = os.path.join(root, file)
                if not self.should_ignore(full_path):
                    file_list.append(full_path)
        
        logger.info(f"Found {len(file_list)} files to analyze.")
        return file_list

    def _handle_git_clone(self):
        """Clone the repository if configured."""
        if not self.config.git_repo:
            return

        repo_name = self.config.git_repo.split("/")[-1].replace(".git", "")
        clone_target = os.path.join(self.target_dir, f"repo_{repo_name}_{self.start_time_str}")
        
        logger.info(f"Cloning repository: {self.config.git_repo} into {clone_target}")
        try:
            import subprocess
            subprocess.run(["git", "clone", self.config.git_repo, clone_target], check=True, capture_output=True)
            # Update target_dir to the cloned repo for the analysis
            self.target_dir = clone_target
            logger.info("Clone successful. Target directory updated.")
        except Exception as e:
            logger.error(f"Failed to clone repository {self.config.git_repo}: {e}")
            # We don't exit, we try to continue with the original directory if it exists

    def chunk_content(self, content: str, max_chars: int = 4000) -> List[str]:
        """Split content into chunks with some overlap."""
        if len(content) <= max_chars:
            return [content]
        
        chunks = []
        start = 0
        overlap = 200
        while start < len(content):
            end = start + max_chars
            chunks.append(content[start:end])
            start = end - overlap
        return chunks

    def analyze_file(self, file_path: str):
        logger.info(f"Analyzing: {file_path}")
        try:
            with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            
            # Accuracy-driven parameters
            intensity = self.config.accuracy_intensity
            max_chars = 6000 if intensity == 1 else (4000 if intensity == 2 else 2500)
            chunks = self.chunk_content(content, max_chars=max_chars)
            
            chunk_results = []
            previous_summary = "None (first chunk)"
            
            for i, chunk in enumerate(chunks):
                logger.info(f"  [{i+1}/{len(chunks)}] Processing chunk...")
                
                # Context-aware prompt
                prompt = (
                    f"File Context (Previous Findings): {previous_summary}\n\n"
                    f"Current Chunk ({i+1}/{len(chunks)}) Content:\n"
                    f"```\n{chunk}\n```\n\n"
                    f"Project Notes: {self.config.ollama_config.notes}\n\n"
                    "Analyze this code for architecture, potential bugs."
                )
                
                # Use "think" prompt for high intensity
                system_prompt = "You are an expert developer. "
                if intensity >= 3:
                    system_prompt += "Perform a deep, step-by-step analysis. Think critically about side effects and edge cases."
                else:
                    system_prompt += "Provide a concise architectural and logical analysis."

                result = self.llm.generate(prompt, system_prompt)
                
                # Validation pass for high accuracy
                if intensity >= 2:
                    validation_prompt = f"Critique and refine this analysis. Ensure it is coherent and accurate according to the code:\n\n{result}"
                    result = self.llm.generate(validation_prompt, "Refine the analysis for accuracy and tone.", use_validation=True)

                chunk_results.append(result)
                
                # Generate a tiny summary for the next chunk's context
                if i < len(chunks) - 1:
                    sum_prompt = f"Provide a 2-sentence summary of the key findings in this chunk for the next analysis turn:\n\n{result}"
                    previous_summary = self.llm.generate(sum_prompt, "Brief summary of code state.")

            final_md = "\n\n---\n\n".join(chunk_results)
            
            # Merge and consolidate
            logger.info(f"Consolidating results for {file_path}")
            merge_prompt = f"Combine these chunk-based findings into a single, high-quality, professional markdown report for {os.path.basename(file_path)}:\n\n{final_md}"
            final_md = self.llm.generate(merge_prompt, "Create a structured, executive-level technical summary.")

            # Save result
            file_dir = os.path.dirname(file_path)
            file_base = os.path.basename(file_path).replace('.', '_')
            output_path = os.path.join(file_dir, f"{self.start_time_str}_{file_base}_rc.md")
            
            with open(output_path, 'w') as f:
                f.write(final_md)
            
            # Update analyzed list
            with open(self.analyzed_txt_path, 'a') as f:
                f.write(f"{os.path.relpath(file_path, self.target_dir)}\n")
                
        except Exception as e:
            logger.error(f"Failed to analyze {file_path}: {e}")

    def run(self):
        start_ts = time.time()

        # Wave 2: Handle optional git clone before scanning
        self._handle_git_clone()

        file_list = self.scan_files()
        
        # Save initial file list
        state = {
            "start_time": datetime.now().isoformat(),
            "target_dir": self.target_dir,
            "files_to_analyze": [os.path.relpath(p, self.target_dir) for p in file_list],
            "config": asdict(self.config)
        }
        with open(self.files_json_path, 'w') as f:
            json.dump(state, f, indent=4)
        
        for i, file_path in enumerate(file_list):
            # Wave 2: Hot-reloading config between files
            logger.info(f"Progress: {i+1}/{len(file_list)} | Reloading config...")
            self.config = self._load_config(self.config_path)
            self._init_llm()
            self.ignore_patterns = self._load_ignore_patterns()
            
            self.analyze_file(file_path)
        
        # Finalize
        state["end_time"] = datetime.now().isoformat()
        state["duration_seconds"] = time.time() - start_ts
        with open(self.files_json_path, 'w') as f:
            json.dump(state, f, indent=4)
        
        logger.info(f"Analysis complete. Results in {self.target_dir}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 root_claw.py [dir] [config_file]")
        sys.exit(1)
    
    target_dir = sys.argv[1]
    config_file = sys.argv[2]
    
    app = RootClaw(target_dir, config_file)
    app.run()
