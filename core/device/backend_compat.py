"""Compatibility settings selected by the control or screenshot backend."""
from dataclasses import dataclass


@dataclass(frozen=True)
class BackendCompat:
    swipe_min_duration: float = 0
    u2_swipe_min_duration: float = 0
    rgb_tolerance: int = 0
    cafe_zoom_delay: float = 0
    cafe_gift_shot_delay: float = 0
    cafe_student_threshold: float = 0.75


DEFAULT_COMPAT = BackendCompat()
BACKEND_COMPAT = {
    # H.264/YUV capture needs color tolerance; Companion returns PNG frames.
    "virtual_scrcpy": BackendCompat(
        swipe_min_duration=0.3, u2_swipe_min_duration=1.5, rgb_tolerance=15,
        cafe_zoom_delay=0.2, cafe_gift_shot_delay=0.6, cafe_student_threshold=0.55,
    ),
    "android_companion": BackendCompat(
        # 原值 1.5s 太保守：咖啡厅一轮有十几次滑动，累积会拖到几十秒。
        # 0.8s 仍高于 Companion 识别滑动所需的下限，实测再微调。
        swipe_min_duration=0.25, u2_swipe_min_duration=0.8,
        cafe_zoom_delay=0.15, cafe_gift_shot_delay=0.4,
    ),
}


def get_backend_compat(method):
    return BACKEND_COMPAT.get(method, DEFAULT_COMPAT)
