from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Optional

import cv2
import numpy as np
import requests


MODEL_VERSION = "1.0.0"
RELEASE_TAG = "student-recognition-v" + MODEL_VERSION
RELEASE_BASE_URL = (
    "https://github.com/kosetsu905/blue_archive_auto_script_ai/"
    "releases/download/" + RELEASE_TAG
)
MODEL_FILES = ("student_encoder.onnx", "gallery.npz", "student_encoder.json")


class ModelDownloadError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_checksums(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        parts = line.strip().split(None, 1)
        if len(parts) == 2 and len(parts[0]) == 64:
            result[parts[1].lstrip("*")] = parts[0].lower()
    if set(result) != set(MODEL_FILES):
        raise ModelDownloadError("Release checksum manifest is incomplete")
    return result


def check_model_dir(
    directory: Path,
    checksums: Optional[dict[str, str]] = None,
) -> tuple[bool, str]:
    """校验模型目录，返回 (是否有效, 失败原因)。

    失败原因要能说清是哪一步挂的：Android 上打包的 OpenCV 可能没有 dnn
    模块，这时只报一句「package is invalid」根本无从下手。
    """
    try:
        if any(not (directory / name).is_file() for name in MODEL_FILES):
            return False, "missing model file"
        if checksums and any(sha256(directory / name) != checksums[name] for name in MODEL_FILES):
            return False, "checksum mismatch"
        metadata = json.loads((directory / "student_encoder.json").read_text(encoding="utf-8"))
        width = int(metadata["embedding_size"])
        gallery = np.load(directory / "gallery.npz", allow_pickle=False)
        embeddings = np.asarray(gallery["embeddings"], dtype=np.float32)
        ids = np.asarray(gallery["student_ids"])
        if embeddings.ndim != 2 or embeddings.shape[1] != width or len(ids) != len(embeddings):
            return False, (
                f"gallery shape {getattr(embeddings, 'shape', None)} / "
                f"ids {len(ids)} vs embedding_size {width}"
            )
        if not hasattr(cv2, "dnn"):
            return False, "opencv has no cv2.dnn module"
        net = cv2.dnn.readNetFromONNX(str(directory / "student_encoder.onnx"))
        if net is None:
            return False, "onnx model loaded None"
        try:
            if net.empty():
                return False, "onnx model loaded empty"
        except AttributeError:
            pass
        return True, ""
    except Exception as error:  # noqa: BLE001 - 校验失败一律降级为不可用
        return False, f"{type(error).__name__}: {error}"


def validate_model_dir(
    directory: Path,
    checksums: Optional[dict[str, str]] = None,
) -> bool:
    return check_model_dir(directory, checksums)[0]


def ensure_model_files(project_root: Path, timeout: float = 15.0) -> Path:
    cache_root = project_root / "config" / "cache" / "student_recognition"
    destination = cache_root / MODEL_VERSION
    checksum_path = destination / "SHA256SUMS"
    if checksum_path.is_file():
        try:
            checksums = parse_checksums(checksum_path.read_text(encoding="ascii"))
            if validate_model_dir(destination, checksums):
                return destination
        except (OSError, UnicodeError, ModelDownloadError):
            pass
    try:
        cache_root.mkdir(parents=True, exist_ok=True)
        checksum_response = requests.get(RELEASE_BASE_URL + "/SHA256SUMS", timeout=timeout)
        checksum_response.raise_for_status()
        checksums = parse_checksums(checksum_response.text)
        with tempfile.TemporaryDirectory(prefix=MODEL_VERSION + "-", dir=cache_root) as temporary:
            temporary_path = Path(temporary)
            for name in MODEL_FILES:
                response = requests.get(RELEASE_BASE_URL + "/" + name, timeout=timeout, stream=True)
                response.raise_for_status()
                target = temporary_path / name
                with target.open("wb") as stream:
                    for chunk in response.iter_content(1024 * 1024):
                        if chunk:
                            stream.write(chunk)
                if sha256(target) != checksums[name]:
                    raise ModelDownloadError("Checksum mismatch for " + name)
            (temporary_path / "SHA256SUMS").write_text(checksum_response.text, encoding="ascii")
            valid, reason = check_model_dir(temporary_path, checksums)
            if not valid:
                raise ModelDownloadError("Downloaded model package is invalid: " + reason)
            destination.mkdir(parents=True, exist_ok=True)
            for name in MODEL_FILES + ("SHA256SUMS",):
                os.replace(temporary_path / name, destination / name)
        return destination
    except (OSError, requests.RequestException, ModelDownloadError) as error:
        raise ModelDownloadError(str(error)) from error
