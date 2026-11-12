"""Android 端电源与锁屏控制。

设计约束：**不修改任何系统设置**（不动 stay_on / screen_off_timeout / 亮度 /
keyguard / cached_apps_freezer）。所有动作只有两类：

1. 事件注入：`input keyevent` / `input swipe` / `input tap`
2. 对单个 app 的 shell 命令：`am force-stop`

动作都在 Shizuku 提供的 shell 权限下执行，不改设备状态，只模拟人手指。

熄屏时 `screencap` 只能拿到黑图，所以每轮任务开始前必须「唤醒 + 解锁」；
任务结束后把游戏关掉，屏幕交给系统按用户自己的超时策略自动熄灭。

配置读 ``config/android_power.json``（不入库），字段见 ``DEFAULT_CONFIG``。
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional

SETTINGS_FILE = Path("config") / "android_power.json"

# 坐标以 1080x2400（Redmi K30S / MIUI 13 实测）为参考，运行时按实际分辨率等比缩放
DEFAULT_CONFIG = {
    "enabled": True,
    "password": "",
    "ref_resolution": [1080, 2400],
    "swipe": {"from": [540, 2000], "to": [540, 900], "duration_ms": 150},
    "keypad": {
        "1": [242, 1462],
        "2": [540, 1462],
        "3": [840, 1462],
        "4": [242, 1644],
        "5": [540, 1644],
        "6": [840, 1644],
        "7": [242, 1824],
        "8": [540, 1824],
        "9": [840, 1824],
        "0": [540, 2006],
    },
    "stop_game_when_idle": True,
    "unlock_retry": 2,
}

KEYCODE_WAKEUP = "224"


def load_config(project_root: Path) -> dict:
    """读配置；文件不存在时按默认值创建，缺字段用默认值补齐。"""
    path = project_root / SETTINGS_FILE
    config = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for key, value in data.items():
                if key.startswith("_"):
                    continue
                config[key] = value
    except (OSError, ValueError):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            config["_comment"] = (
                "password 填锁屏 PIN；keypad/swipe 坐标以 ref_resolution 为基准，"
                "运行时按实际分辨率等比缩放。stop_game_when_idle 控制任务结束后是否关闭游戏。"
            )
            path.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
    return config


class AndroidPower:
    """封装唤醒、解锁、停游戏的开关。``u2`` 为 uiautomator2 连接。"""

    def __init__(self, u2, logger, project_root: Path):
        self.u2 = u2
        self.logger = logger
        self.config = load_config(project_root)
        self.enabled = bool(self.config.get("enabled", True))
        self.password = str(self.config.get("password") or "")
        self.stop_game_when_idle = bool(self.config.get("stop_game_when_idle", True))
        self.ref_width, self.ref_height = self._pair(self.config.get("ref_resolution"), (1080, 2400))
        self._screen = None  # 实际分辨率，首次使用时探测

    # ---------------- 基础工具 ----------------

    @staticmethod
    def _pair(value, fallback):
        try:
            if isinstance(value, (list, tuple)) and len(value) == 2:
                return int(value[0]), int(value[1])
        except (TypeError, ValueError):
            pass
        return fallback

    def _shell(self, command: str) -> str:
        try:
            result = self.u2.shell(command)
        except Exception as error:
            self.logger.warning("shell failed: " + command + " -> " + str(error))
            return ""
        return getattr(result, "output", "") or ""

    def screen_size(self):
        """实际物理分辨率（``wm size`` 的 Physical size）。"""
        if self._screen is not None:
            return self._screen
        output = self._shell("wm size")
        match = re.search(r"Physical size:\s*(\d+)x(\d+)", output)
        if match:
            self._screen = (int(match.group(1)), int(match.group(2)))
        else:
            self._screen = (self.ref_width, self.ref_height)
        return self._screen

    def _scale(self, point) -> tuple:
        """把配置里的参考坐标换算成当前设备的实际坐标。"""
        width, height = self.screen_size()
        x, y = self._pair(point, (0, 0))
        if width == self.ref_width and height == self.ref_height:
            return x, y
        return int(round(x * width / self.ref_width)), int(round(y * height / self.ref_height))

    # ---------------- 状态判定 ----------------

    def is_locked(self) -> bool:
        """keyguard 是否正在显示。"""
        output = self._shell("dumpsys window policy")
        match = re.search(r"showing=(\w+)", output)
        return bool(match) and match.group(1).lower() == "true"

    def is_screen_on(self) -> bool:
        output = self._shell("dumpsys power")
        return "mWakefulness=Awake" in output

    # ---------------- 动作 ----------------

    def wake(self) -> None:
        if not self.is_screen_on():
            self.logger.info("Waking screen up.")
            self._shell("input keyevent " + KEYCODE_WAKEUP)
            time.sleep(0.8)

    def unlock(self) -> bool:
        """上滑呼出 PIN 盘，逐位点按密码，最后确认是否真的解锁。"""
        if not self.password:
            self.logger.warning("No unlock password configured, skip unlock.")
            return not self.is_locked()
        swipe = self.config.get("swipe") or {}
        start = self._scale(swipe.get("from", [540, 2000]))
        end = self._scale(swipe.get("to", [540, 900]))
        duration = int(swipe.get("duration_ms", 150))
        self._shell(f"input swipe {start[0]} {start[1]} {end[0]} {end[1]} {duration}")
        time.sleep(1.2)

        keypad = self.config.get("keypad") or {}
        for char in self.password:
            point = keypad.get(char)
            if point is None:
                self.logger.warning("Keypad has no coordinate for digit: " + char)
                return False
            x, y = self._scale(point)
            self._shell(f"input tap {x} {y}")
            time.sleep(0.35)
        time.sleep(1.5)
        return not self.is_locked()

    def ensure_ready(self) -> bool:
        """确保屏幕点亮且已解锁。返回是否达成。"""
        if not self.enabled:
            return True
        self.wake()
        if not self.is_locked():
            return True
        retry = max(1, int(self.config.get("unlock_retry", 2)))
        for attempt in range(1, retry + 1):
            self.logger.info(f"Device locked, unlocking ({attempt}/{retry}).")
            if self.unlock():
                self.logger.info("Device unlocked.")
                return True
            time.sleep(1.0)
        self.logger.warning("Unlock failed, keyguard still showing.")
        return False

    def stop_game(self, package_name: Optional[str]) -> None:
        if not package_name:
            return
        self._shell("am force-stop " + package_name)
