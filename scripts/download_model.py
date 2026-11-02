"""Fetch the ONNX embedding model into MEMLORD_MODEL_DIR if it isn't there yet.

Downloads straight into the model directory and keeps every Hugging Face cache
in a staging directory beside it (nothing under $HOME), so it works as any UID
as long as the model directory is writable.
"""

import os
import shutil
from pathlib import Path

from memlord.config import settings

REPO_ID = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
FILES = {
    "onnx/model.onnx": "model.onnx",
    "tokenizer.json": "tokenizer.json",
}

dest_dir = settings.model_dir.resolve()
dest_dir.mkdir(parents=True, exist_ok=True)
staging = dest_dir / ".download"

# huggingface_hub reads this at import time, so it must be set first.
os.environ.setdefault("HF_HOME", str(staging / "hf-home"))

from huggingface_hub import hf_hub_download  # noqa: E402

try:
    for repo_filename, local_name in FILES.items():
        dest = dest_dir / local_name
        if dest.exists():
            print(f"  skip  {local_name} (already exists)")
            continue
        print(f"  download  {repo_filename} → {dest}")
        path = Path(hf_hub_download(repo_id=REPO_ID, filename=repo_filename, local_dir=staging))
        # Same filesystem, so this is a rename: a half-finished download never
        # appears under the final name.
        path.replace(dest)
        print(f"  done  {local_name} ({dest.stat().st_size // 1024 // 1024} MB)")
finally:
    shutil.rmtree(staging, ignore_errors=True)
