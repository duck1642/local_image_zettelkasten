import csv
import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from logs.logger import log_system
from utils import MODELS_DIR, TOPICS_DIR, calculate_file_hash, get_config
from validators import get_mime_type


@dataclass
class TagResult:
    item_hash: str
    asset_path: str
    model_repo: str
    device_requested: str
    provider: str
    threshold: float
    max_tags: int
    created_at: str
    status: str
    tags: list[dict[str, Any]]
    error: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def tag_media(media_path: str | Path, item_hash: str = None, config: dict = None) -> TagResult:
    config = config or get_config()
    tag_config = config.get("tagging", {})
    media_path = Path(media_path)
    model_repo = tag_config.get("model_repo", "SmilingWolf/wd-vit-tagger-v3")
    device = tag_config.get("device", "auto")
    threshold = float(tag_config.get("threshold", 0.35))
    max_tags = int(tag_config.get("max_tags", 30))
    if not item_hash and media_path.exists():
        item_hash = calculate_file_hash(media_path)
    item_hash = item_hash or ""

    if not tag_config.get("enabled", True):
        result = _result(item_hash, media_path, model_repo, device, "", threshold, max_tags, "skipped", [], "tagging disabled")
        _write_result(result)
        return result

    if not media_path.exists():
        result = _result(item_hash, media_path, model_repo, device, "", threshold, max_tags, "failed", [], "media path does not exist")
        _write_result(result)
        return result

    mime_type = get_mime_type(media_path) or ""
    if not mime_type.startswith("image/"):
        result = _result(item_hash, media_path, model_repo, device, "", threshold, max_tags, "skipped", [], f"unsupported media type: {mime_type or 'unknown'}")
        _write_result(result)
        return result

    try:
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download

        model_path, tags_path = _ensure_model_files(model_repo, hf_hub_download)
        labels = _load_labels(tags_path)
        providers, provider_warning = _providers_for_device(device, ort)
        session = ort.InferenceSession(str(model_path), providers=providers)
        input_meta = session.get_inputs()[0]
        output_meta = session.get_outputs()[0]
        image_array = _prepare_image(media_path, input_meta.shape)
        predictions = session.run([output_meta.name], {input_meta.name: image_array})[0][0].astype(float)
        provider = session.get_providers()[0] if session.get_providers() else ""
        tags = _tags_from_predictions(labels, predictions, threshold, max_tags)
        status = "ok"
        error = provider_warning
        result = _result(item_hash, media_path, model_repo, device, provider, threshold, max_tags, status, tags, error)
        _write_result(result)
        log_system("INFO", "WD tagger completed", hash=item_hash, path=str(media_path), tag_count=len(tags), provider=provider)
        return result
    except Exception as exc:
        result = _result(item_hash, media_path, model_repo, device, "", threshold, max_tags, "failed", [], str(exc))
        _write_result(result)
        log_system("WARNING", "WD tagger failed", hash=item_hash, path=str(media_path), error=str(exc))
        return result


def _result(item_hash: str, media_path: Path, model_repo: str, device: str, provider: str, threshold: float, max_tags: int, status: str, tags: list[dict[str, Any]], error: str = "") -> TagResult:
    return TagResult(
        item_hash=item_hash,
        asset_path=str(media_path),
        model_repo=model_repo,
        device_requested=device,
        provider=provider,
        threshold=threshold,
        max_tags=max_tags,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        status=status,
        tags=tags,
        error=error,
    )


def _write_result(result: TagResult):
    if not result.item_hash:
        return
    TOPICS_DIR.mkdir(parents=True, exist_ok=True)
    target = TOPICS_DIR / f"{result.item_hash}.json"
    target.write_text(json.dumps(result.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")


def _ensure_model_files(model_repo: str, hf_hub_download):
    model_dir = MODELS_DIR / model_repo.split("/")[-1]
    model_dir.mkdir(parents=True, exist_ok=True)
    local_model = model_dir / "model.onnx"
    local_tags = model_dir / "selected_tags.csv"
    if local_model.exists() and local_tags.exists():
        return local_model, local_tags
    model_path = hf_hub_download(repo_id=model_repo, filename="model.onnx", local_dir=str(model_dir))
    tags_path = hf_hub_download(repo_id=model_repo, filename="selected_tags.csv", local_dir=str(model_dir))
    return Path(model_path), Path(tags_path)


def _load_labels(tags_path: Path) -> list[dict[str, str]]:
    labels = []
    with tags_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            values = list(row.values())
            name = row.get("name") or (values[1] if len(values) > 1 else "")
            category = row.get("category") or (values[2] if len(values) > 2 else "")
            if name:
                labels.append({"name": name, "category": category})
    return labels


def _providers_for_device(device: str, ort):
    available = ort.get_available_providers()
    device = (device or "auto").lower()
    if device == "cpu":
        return ["CPUExecutionProvider"], ""
    if device == "cuda":
        if "CUDAExecutionProvider" in available:
            return ["CUDAExecutionProvider", "CPUExecutionProvider"], ""
        return ["CPUExecutionProvider"], "CUDAExecutionProvider unavailable; fell back to CPUExecutionProvider"
    if "CUDAExecutionProvider" in available:
        return ["CUDAExecutionProvider", "CPUExecutionProvider"], ""
    return ["CPUExecutionProvider"], ""


def _prepare_image(image_path: Path, input_shape) -> np.ndarray:
    target_size = _target_size(input_shape)
    channel_first = len(input_shape) == 4 and input_shape[1] == 3
    image = Image.open(image_path)
    image.seek(0)
    image = image.convert("RGBA")
    canvas = Image.new("RGBA", image.size, (255, 255, 255, 255))
    canvas.alpha_composite(image)
    image = canvas.convert("RGB")
    width, height = image.size
    max_dim = max(width, height)
    padded = Image.new("RGB", (max_dim, max_dim), (255, 255, 255))
    padded.paste(image, ((max_dim - width) // 2, (max_dim - height) // 2))
    if max_dim != target_size:
        padded = padded.resize((target_size, target_size), Image.Resampling.BICUBIC)
    array = np.asarray(padded, dtype=np.float32)
    array = array[:, :, ::-1]
    if channel_first:
        array = np.transpose(array, (2, 0, 1))
    return np.expand_dims(array, axis=0)


def _target_size(input_shape) -> int:
    for value in reversed(input_shape):
        if isinstance(value, int) and value > 3:
            return value
    return 448


def _tags_from_predictions(labels: list[dict[str, str]], predictions: np.ndarray, threshold: float, max_tags: int) -> list[dict[str, Any]]:
    category_names = {"9": "rating", "0": "general", "4": "character"}
    scored = []
    rating = None
    for label, score in zip(labels, predictions):
        category = str(label.get("category", ""))
        item = {
            "name": label.get("name", ""),
            "display_name": label.get("name", "").replace("_", " "),
            "score": round(float(score), 6),
            "category": category_names.get(category, category),
        }
        if category == "9":
            if rating is None or item["score"] > rating["score"]:
                rating = item
            continue
        if score >= threshold:
            scored.append(item)
    scored.sort(key=lambda tag: tag["score"], reverse=True)
    tags = scored[:max_tags]
    if rating:
        tags.insert(0, rating)
    return tags
