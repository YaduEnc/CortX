#!/usr/bin/env python3
"""
Download a faster-whisper model once to local storage for self-hosted use.

Example:
  python scripts/download_whisper_model.py --model-size small --output-dir /models
"""

from __future__ import annotations

import argparse
from pathlib import Path

from huggingface_hub import snapshot_download


def main() -> None:
    parser = argparse.ArgumentParser(description="Download faster-whisper model to local directory")
    parser.add_argument("--model-size", default="small", help="tiny, base, small, medium, large-v2, large-v3, ...")
    parser.add_argument("--output-dir", default="/models", help="Parent directory for downloaded model")
    parser.add_argument("--force", action="store_true", help="Force re-download even if model.bin exists")
    args = parser.parse_args()

    model_dir = Path(args.output_dir) / f"faster-whisper-{args.model_size}"
    model_bin = model_dir / "model.bin"

    if model_bin.exists() and not args.force:
        print(f"[OK] Model already present: {model_dir}")
        print(f"[SET] WHISPER_MODEL_PATH={model_dir}")
        return

    model_dir.mkdir(parents=True, exist_ok=True)
    repo_id = f"Systran/faster-whisper-{args.model_size}"
    print(f"[DL] Downloading {repo_id} -> {model_dir}")

    snapshot_download(
        repo_id=repo_id,
        local_dir=str(model_dir),
        local_dir_use_symlinks=False,
        allow_patterns=[
            "config.json",
            "model.bin",
            "tokenizer.json",
            "vocabulary.*",
            "preprocessor_config.json",
        ],
    )

    print(f"[DONE] Model downloaded: {model_dir}")
    print(f"[SET] WHISPER_MODEL_PATH={model_dir}")


if __name__ == "__main__":
    main()
