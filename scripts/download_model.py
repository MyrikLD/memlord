from pathlib import Path

from huggingface_hub import hf_hub_download

REPO_ID = "sentence-transformers/all-MiniLM-L6-v2"
FILES = {
    "onnx/model.onnx": "model.onnx",
    "tokenizer.json": "tokenizer.json",
}

dest_dir = Path(__file__).parent.parent / "src" / "memlord" / "onnx"
dest_dir.mkdir(parents=True, exist_ok=True)

for repo_filename, local_name in FILES.items():
    dest = dest_dir / local_name
    if dest.exists():
        print(f"  skip  {local_name} (already exists)")
        continue
    print(f"  download  {repo_filename} → {dest}")
    path = hf_hub_download(repo_id=REPO_ID, filename=repo_filename)
    dest.write_bytes(Path(path).read_bytes())
    print(f"  done  {local_name} ({dest.stat().st_size // 1024 // 1024} MB)")
