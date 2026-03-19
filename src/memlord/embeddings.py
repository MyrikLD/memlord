from functools import cache

import numpy as np
from onnxruntime import InferenceSession
from tokenizers import Tokenizer

from memlord.config import settings


@cache
def _get_session() -> InferenceSession:
    return InferenceSession(str(settings.model_dir / "model.onnx"))


@cache
def _get_tokenizer() -> Tokenizer:
    t = Tokenizer.from_file(str(settings.model_dir / "tokenizer.json"))
    t.enable_padding(pad_token="[PAD]")
    t.enable_truncation(max_length=512)
    return t


def embed(text: str) -> list[float]:
    tokenizer = _get_tokenizer()
    session = _get_session()

    encoding = tokenizer.encode(text)
    input_ids = np.array([encoding.ids], dtype=np.int64)
    attention_mask = np.array([encoding.attention_mask], dtype=np.int64)
    token_type_ids = np.zeros_like(input_ids, dtype=np.int64)

    outputs = session.run(
        None,
        {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "token_type_ids": token_type_ids,
        },
    )

    # mean pooling with attention mask
    token_embeddings = np.asarray(outputs[0])  # (1, seq_len, 384)
    mask = attention_mask[..., np.newaxis].astype(np.float32)  # (1, seq_len, 1)
    pooled = (token_embeddings * mask).sum(axis=1) / mask.sum(axis=1).clip(min=1e-9)

    # L2 normalize
    norm = np.linalg.norm(pooled, axis=1, keepdims=True).clip(min=1e-9)
    normalized = (pooled / norm).astype(np.float32)

    return normalized[0].tolist()
