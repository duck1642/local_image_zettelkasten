import csv
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from fingerprint import extract_sampled_video_frames
from logs.logger import log_system
from utils import MODELS_DIR, atomic_write_text, calculate_file_hash, get_config, wd_tag_cache_path_for
from validators import get_mime_type


@dataclass
class TagResult:
    hash: str
    status: str
    model: str
    threshold: float
    created_at: str
    rating: dict[str, Any] | None
    character_tags: list[dict[str, Any]]
    tags: list[dict[str, Any]]
    provider: str = ""
    device: str = ""
    max_tags: int = 0
    error: str = ""
    media_type: str = "image"
    sampled_frames: list[dict[str, Any]] = field(default_factory=list)
    frame_count: int = 0

    @property
    def item_hash(self) -> str:
        return self.hash

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
    video_config = tag_config.get("video", {})
    video_frame_count = int(video_config.get("frame_count", 5))
    merge_min_frames = int(video_config.get("merge_min_frames", 2))
    merge_high_confidence = float(video_config.get("merge_high_confidence", 0.75))
    try:
        if not item_hash and media_path.exists():
            item_hash = calculate_file_hash(media_path)
        item_hash = item_hash or ""

        if not tag_config.get("enabled", True):
            result = _result(item_hash, media_path, model_repo, device, "", threshold, max_tags, "skipped", error="tagging disabled")
            _write_result(result)
            return result

        if not media_path.exists():
            result = _result(item_hash, media_path, model_repo, device, "", threshold, max_tags, "failed", error="media path does not exist")
            _write_result(result)
            return result
    except Exception as exc:
        result = _result(item_hash or "", media_path, model_repo, device, "", threshold, max_tags, "failed", error=str(exc))
        _write_result(result)
        return result

    mime_type = get_mime_type(media_path) or ""
    media_type = "video" if mime_type.startswith("video/") else "image" if mime_type.startswith("image/") else "unknown"
    if media_type == "video" and not video_config.get("enabled", True):
        result = _result(item_hash, media_path, model_repo, device, "", threshold, max_tags, "skipped", error="video tagging disabled", media_type="video")
        _write_result(result)
        return result
    if media_type == "unknown":
        result = _result(item_hash, media_path, model_repo, device, "", threshold, max_tags, "skipped", error=f"unsupported media type: {mime_type or 'unknown'}", media_type="unknown")
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
        provider = session.get_providers()[0] if session.get_providers() else ""
        if media_type == "video":
            samples = extract_sampled_video_frames(media_path, video_frame_count)
            if not samples:
                result = _result(item_hash, media_path, model_repo, device, provider, threshold, max_tags, "failed", error="could not extract video frames", media_type="video")
                _write_result(result)
                return result
            sampled_frames = []
            for timestamp, image in samples:
                rating, character_tags, tags = _predict_image_tags(session, input_meta, output_meta, labels, image, threshold, max_tags)
                sampled_frames.append({
                    "timestamp": round(float(timestamp), 3),
                    "rating": rating,
                    "character_tags": character_tags,
                    "tags": tags,
                })
            rating, character_tags, tags = _merge_frame_tags(sampled_frames, max_tags, merge_min_frames, merge_high_confidence)
            result = _result(item_hash, media_path, model_repo, device, provider, threshold, max_tags, "ok", rating, character_tags, tags, provider_warning, "video", sampled_frames, len(sampled_frames))
            _write_result(result)
            log_system("INFO", "WD video tagger completed", hash=item_hash, path=str(media_path), frame_count=len(sampled_frames), tag_count=len(tags), provider=provider)
            return result
        image = Image.open(media_path)
        image.seek(0)
        rating, character_tags, tags = _predict_image_tags(session, input_meta, output_meta, labels, image, threshold, max_tags)
        status = "ok"
        error = provider_warning
        result = _result(item_hash, media_path, model_repo, device, provider, threshold, max_tags, status, rating, character_tags, tags, error, "image")
        _write_result(result)
        log_system("INFO", "WD tagger completed", hash=item_hash, path=str(media_path), tag_count=len(tags), provider=provider)
        return result
    except Exception as exc:
        result = _result(item_hash, media_path, model_repo, device, "", threshold, max_tags, "failed", error=str(exc), media_type=media_type)
        _write_result(result)
        log_system("WARNING", "WD tagger failed", hash=item_hash, path=str(media_path), error=str(exc))
        return result


def _result(item_hash: str, media_path: Path, model_repo: str, device: str, provider: str, threshold: float, max_tags: int, status: str, rating=None, character_tags=None, tags=None, error: str = "", media_type: str = "image", sampled_frames=None, frame_count: int = 0) -> TagResult:
    return TagResult(
        hash=item_hash,
        status=status,
        model=model_repo,
        threshold=threshold,
        created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        rating=rating,
        character_tags=character_tags or [],
        tags=tags or [],
        provider=provider,
        device=device,
        max_tags=max_tags,
        error=error,
        media_type=media_type,
        sampled_frames=sampled_frames or [],
        frame_count=frame_count,
    )


def _write_result(result: TagResult):
    if not result.hash:
        return
    target = wd_tag_cache_path_for(result.hash)
    atomic_write_text(target, json.dumps(result.to_dict(), indent=2, ensure_ascii=False))


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


def _predict_image_tags(session, input_meta, output_meta, labels: list[dict[str, str]], image: Image.Image, threshold: float, max_tags: int):
    image_array = _prepare_pil_image(image, input_meta.shape)
    predictions = session.run([output_meta.name], {input_meta.name: image_array})[0][0].astype(float)
    if len(labels) != len(predictions):
        raise ValueError(f"WD label/prediction count mismatch: {len(labels)} labels, {len(predictions)} predictions")
    return _tags_from_predictions(labels, predictions, threshold, max_tags)


def _prepare_image(image_path: Path, input_shape) -> np.ndarray:
    image = Image.open(image_path)
    image.seek(0)
    return _prepare_pil_image(image, input_shape)


def _prepare_pil_image(image: Image.Image, input_shape) -> np.ndarray:
    target_size = _target_size(input_shape)
    channel_first = len(input_shape) == 4 and input_shape[1] == 3
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
    array = np.ascontiguousarray(array[:, :, ::-1])
    if channel_first:
        array = np.transpose(array, (2, 0, 1))
    return np.expand_dims(array, axis=0)


def _target_size(input_shape) -> int:
    for value in reversed(input_shape):
        if isinstance(value, int) and value > 3:
            return value
    return 448


def _tags_from_predictions(labels: list[dict[str, str]], predictions: np.ndarray, threshold: float, max_tags: int):
    general = []
    characters = []
    rating = None
    for label, score in zip(labels, predictions):
        category = str(label.get("category", ""))
        item = {
            "name": label.get("name", ""),
            "display_name": label.get("name", "").replace("_", " "),
            "score": round(float(score), 6),
        }
        if category == "9":
            if rating is None or item["score"] > rating["score"]:
                rating = {"label": item["display_name"], "name": item["name"], "score": item["score"]}
            continue
        if score >= threshold:
            if category == "4":
                characters.append(item)
            else:
                general.append(item)
    general.sort(key=lambda tag: tag["score"], reverse=True)
    characters.sort(key=lambda tag: tag["score"], reverse=True)
    return rating, characters[:max_tags], general[:max_tags]


def _merge_frame_tags(sampled_frames: list[dict[str, Any]], max_tags: int, merge_min_frames: int, merge_high_confidence: float):
    rating = None
    for frame in sampled_frames:
        frame_rating = frame.get("rating")
        if frame_rating and (rating is None or frame_rating.get("score", 0) > rating.get("score", 0)):
            rating = frame_rating
    characters = _merge_tag_group(sampled_frames, "character_tags", max_tags, merge_min_frames, merge_high_confidence)
    tags = _merge_tag_group(sampled_frames, "tags", max_tags, merge_min_frames, merge_high_confidence)
    return rating, characters, tags


def _merge_tag_group(sampled_frames: list[dict[str, Any]], key: str, max_tags: int, merge_min_frames: int, merge_high_confidence: float):
    merged = {}
    for frame in sampled_frames:
        seen = set()
        for tag in frame.get(key) or []:
            name = tag.get("name") or tag.get("display_name") or ""
            if not name or name in seen:
                continue
            seen.add(name)
            item = merged.setdefault(name, {
                "name": tag.get("name", name),
                "display_name": tag.get("display_name") or str(name).replace("_", " "),
                "scores": [],
                "frame_count": 0,
            })
            item["scores"].append(float(tag.get("score", 0)))
            item["frame_count"] += 1
    results = []
    for item in merged.values():
        best_score = max(item["scores"]) if item["scores"] else 0.0
        if item["frame_count"] < merge_min_frames and best_score < merge_high_confidence:
            continue
        avg_score = sum(item["scores"]) / len(item["scores"])
        results.append({
            "name": item["name"],
            "display_name": item["display_name"],
            "score": round(float(avg_score), 6),
            "frame_count": item["frame_count"],
        })
    results.sort(key=lambda tag: (tag["frame_count"], tag["score"]), reverse=True)
    return results[:max_tags]


def load_tag_cache(item_hash: str) -> dict:
    path = wd_tag_cache_path_for(item_hash)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if "hash" not in data and "item_hash" in data:
        data = _legacy_cache_to_current(data)
    return data


def wd_frontmatter_fields(item_hash: str) -> dict:
    data = load_tag_cache(item_hash)
    if data.get("status") != "ok":
        return {"wd_rating": "", "wd_character_tags": [], "wd_tags": []}
    rating = data.get("rating") or {}
    character_tags = data.get("character_tags") or []
    tags = data.get("tags") or []
    return {
        "wd_rating": rating.get("label") or "",
        "wd_character_tags": [_tag_name(tag) for tag in character_tags if _tag_name(tag)],
        "wd_tags": [_tag_name(tag) for tag in tags if _tag_name(tag)],
    }


def _tag_name(tag: dict) -> str:
    return str(tag.get("display_name") or tag.get("name") or "").strip()


def _legacy_cache_to_current(data: dict) -> dict:
    rating = None
    characters = []
    tags = []
    for tag in data.get("tags") or []:
        category = tag.get("category")
        item = {
            "name": tag.get("name", ""),
            "display_name": tag.get("display_name") or str(tag.get("name", "")).replace("_", " "),
            "score": tag.get("score", 0),
        }
        if category == "rating":
            rating = {"label": item["display_name"], "name": item["name"], "score": item["score"]}
        elif category == "character":
            characters.append(item)
        else:
            tags.append(item)
    return {
        "hash": data.get("item_hash", ""),
        "status": data.get("status", "unknown"),
        "model": data.get("model_repo", ""),
        "threshold": data.get("threshold", ""),
        "created_at": data.get("created_at", ""),
        "rating": rating,
        "character_tags": characters,
        "tags": tags,
        "provider": data.get("provider", ""),
        "device": data.get("device_requested", ""),
        "max_tags": data.get("max_tags", 0),
        "error": data.get("error", ""),
    }
