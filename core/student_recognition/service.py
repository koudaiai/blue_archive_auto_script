from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Optional

import cv2
import numpy as np

from core.student_recognition.catalog import StudentCatalog
from core.student_recognition.fixed_layout import FixedLessonLayout
from core.student_recognition.model_downloader import ModelDownloadError, ensure_model_files
from core.student_recognition.recognizer import StudentRecognizer
from core.student_recognition.types import LessonCard


# 识别相似度门槛：低于该值一律不点击（宁可不点，也不要点错）。
# 依据：用 65 张真实游戏头像模板回归，正确样本最低 0.761，唯一一次误认 0.747。
DEFAULT_MIN_SCORE = 0.75
SETTINGS_FILE = Path("config") / "student_recognition.json"


def load_min_score(project_root: Path) -> float:
    """读 config/student_recognition.json 的 min_score；文件不存在时按默认值创建。"""
    path = project_root / SETTINGS_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return float(data.get("min_score", DEFAULT_MIN_SCORE))
    except (OSError, ValueError):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(
                json.dumps(
                    {
                        "min_score": DEFAULT_MIN_SCORE,
                        "_comment": "识别相似度门槛：低于该值不点击；填 0 表示不设门槛",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        except OSError:
            pass
        return DEFAULT_MIN_SCORE


class StudentRecognitionService:
    def __init__(
        self,
        student_rows: Iterable[dict],
        project_root: Path,
        model_dir: Optional[Path] = None,
        catalog: Optional[StudentCatalog] = None,
        min_score: Optional[float] = None,
    ):
        self.catalog = catalog if catalog is not None else StudentCatalog(student_rows)
        self.layout = FixedLessonLayout()
        self.min_score = load_min_score(project_root) if min_score is None else float(min_score)
        self.load_error: Optional[str] = None
        self.recognition_error: Optional[str] = None
        try:
            resolved_model_dir = model_dir or ensure_model_files(project_root)
            self.recognizer = StudentRecognizer(
                self.catalog, resolved_model_dir, min_score=self.min_score
            )
            if not self.recognizer.available:
                self.load_error = "student model package is invalid"
        except ModelDownloadError as error:
            self.load_error = str(error)
            self.recognizer = None

    @property
    def available(self) -> bool:
        return self.recognizer is not None and self.recognizer.available

    def recognize_lesson(
        self,
        image: Optional[np.ndarray],
        statuses: list[str],
        server: str = "",
    ) -> list[LessonCard]:
        self.recognition_error = None
        try:
            cards = self.layout.locate(image, statuses)
        except (ValueError, cv2.error) as error:
            self.recognition_error = str(error)
            return []
        if not self.available:
            return cards
        avatars = [avatar for card in cards for avatar in card.avatars]
        predictions = self.recognizer.identify(
            [avatar.crop for avatar in avatars], server=server
        )
        for avatar, prediction in zip(avatars, predictions):
            avatar.prediction = prediction
        return cards

    @staticmethod
    def select_priority_card(
        cards: Iterable[LessonCard], priorities: Iterable[str]
    ) -> Optional[LessonCard]:
        ordered = sorted(cards, key=lambda card: card.index)
        for target in priorities:
            for card in ordered:
                if card.state != "available":
                    continue
                for avatar in card.avatars:
                    prediction = avatar.prediction
                    if avatar.eligible and prediction and prediction.accepted and prediction.name == target:
                        return card
        return None
