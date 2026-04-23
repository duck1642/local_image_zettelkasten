
import subprocess
import json
from pathlib import Path


_model = None

def get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer('clip-ViT-B-32')
    return _model

def is_silent(video_path: Path, threshold_db: float = -60.0) -> bool:

    try:
        cmd = [
            'ffmpeg', '-i', str(video_path),
            '-af', 'volumedetect',
            '-vn', '-sn', '-dn',
            '-f', 'null', '-'
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, check=False)


        import re
        match = re.search(r"max_volume:\s+(-?\d+\.\d*)\s+dB", result.stderr)

        if match:
            max_vol = float(match.group(1))
            return max_vol <= threshold_db


        return True
    except Exception:
        return True

def get_audio_fingerprint(video_path: Path) -> bytes:

    try:

        if is_silent(video_path):
            return b''


        result = subprocess.run(
            ['fpcalc', '-raw', '-json', '-length', '120', str(video_path)],
            capture_output=True,
            text=True,
            check=False
        )

        if result.stdout:
            data = json.loads(result.stdout)
            raw_fp = data.get('fingerprint', [])
            if raw_fp:
                import numpy as np

                return np.array(raw_fp, dtype=np.int32).tobytes()
        return b''
    except Exception:
        return b''

def get_visual_embedding(video_path: Path) -> bytes:

    try:


        probe = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(video_path)],
            capture_output=True,
            text=True,
            check=False
        )
        if probe.returncode != 0:
            from logs.logger import log_system
            log_system("WARNING", "ffprobe failed - possibly corrupt or unsupported video",
                       file=str(video_path.name), stderr=probe.stderr.strip()[:200])
            return b''
        duration_str = probe.stdout.strip()
        duration = float(duration_str) if duration_str and duration_str != 'N/A' else 1.0


        points = [duration * 0.10, duration * 0.30, duration * 0.50, duration * 0.70, duration * 0.90]
        model = get_model()
        vectors = []

        from io import BytesIO
        import numpy as np
        from PIL import Image
        for ts in points:

            frame_cmd = [
                'ffmpeg', '-y', '-ss', f"{ts:.3f}", '-i', str(video_path),
                '-frames:v', '1', '-f', 'image2pipe', '-vcodec', 'png', '-'
            ]
            frame_proc = subprocess.run(frame_cmd, capture_output=True, check=True)

            img = Image.open(BytesIO(frame_proc.stdout)).convert('RGB')
            vectors.append(model.encode(img))


        avg_vector = np.mean(vectors, axis=0)


        norm = np.linalg.norm(avg_vector)
        if norm > 0:
            avg_vector = avg_vector / norm


        return avg_vector.astype(np.float32).tobytes()

    except Exception:
        return b''

def compare_audio_fingerprints(fp1_bytes: bytes, fp2_bytes: bytes) -> float:

    if not fp1_bytes or not fp2_bytes:
        return 0.0

    if fp1_bytes == fp2_bytes:
        return 1.0

    import numpy as np

    a = np.frombuffer(fp1_bytes, dtype=np.int32)
    b = np.frombuffer(fp2_bytes, dtype=np.int32)


    length = min(len(a), len(b))
    if length == 0:
        return 0.0

    a = a[:length]
    b = b[:length]


    xor_res = a.astype(np.uint32) ^ b.astype(np.uint32)


    diff_bits = int(np.unpackbits(xor_res.view(np.uint8)).sum())
    total_bits = length * 32

    return 1.0 - (diff_bits / total_bits)

def compare_embeddings(emb1_bytes: bytes, emb2_bytes: bytes) -> float:

    if not emb1_bytes or not emb2_bytes:
        return 0.0

    import numpy as np
    emb1 = np.frombuffer(emb1_bytes, dtype=np.float32)
    emb2 = np.frombuffer(emb2_bytes, dtype=np.float32)


    dot_product = np.dot(emb1, emb2)
    norm1 = np.linalg.norm(emb1)
    norm2 = np.linalg.norm(emb2)

    if norm1 == 0 or norm2 == 0:
        return 0.0

    return dot_product / (norm1 * norm2)
