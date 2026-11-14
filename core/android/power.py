"""Android 端电源与锁屏控制。

设计约束：**不修改任何系统设置**（不动 stay_on / screen_off_timeout / 亮度 /
keyguard / cached_apps_freezer）。所有动作只有两类：

1. 事件注入：`input keyevent` / `input swipe` / `input tap`
2. 对单个 app 的 shell 命令：`am force-stop`

动作都在 Shizuku 提供的 shell 权限下执行，不改设备状态，只模拟人手指。

锁屏 PIN 由 BAAS 配置项 ``android_unlock_password`` 提供（GUI「Android 运行设置」里填），
不写入仓库；``config/android_power.json`` 只保存与设备相关的坐标参数。
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Optional

SETTINGS_FILE = Path("config") / "android_power.json"

# 坐标以 1080x2400（Redmi K30S / MIUI 13 实测）为参考，运行时按实际分辨率等比缩放
DEFAULT_SETTINGS = {
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
    "unlock_retry": 2,
}

KEYCODE_WAKEUP = "224"


def load_settings(project_root: Path) -> dict:
    """读坐标配置；文件不存在时按默认值创建，缺字段用默认值补齐。"""
    path = project_root / SETTINGS_FILE
    settings = json.loads(json.dumps(DEFAULT_SETTINGS))  # deep copy
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            for key, value in data.items():
                if key.startswith("_"):
                    continue
                settings[key] = value
    except (OSError, ValueError):
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            settings["_comment"] = (
                "锁屏密码请在 BAAS 界面的「Android 运行设置」里填写；"
                "这里只放与设备分辨率相关的滑动/按键坐标，ref_resolution 为基准分辨率。"
            )
            path.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
        except OSError:
            pass
    return settings


class AndroidPower:
    """封装唤醒、解锁、停游戏的开关。``u2`` 为 uiautomator2 连接。"""

    def __init__(self, u2, logger, app_config, project_root: Path):
        self.u2 = u2
        self.logger = logger
        self.app_config = app_config
        self.settings = load_settings(project_root)
        raw_password = getattr(app_config, "android_unlock_password", "")
        if isinstance(raw_password, int):
            self.logger.warning(
                "android_unlock_password is an int in config (leading zero lost); "
                "check init_config type conversion"
            )
        self.password = str(raw_password or "").strip()
        self.stop_game_when_idle = bool(getattr(app_config, "android_stop_game_when_idle", True))
        self.ref_width, self.ref_height = self._pair(self.settings.get("ref_resolution"), (1080, 2400))
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

    # ---------------- 两条 shell 通道 ----------------

    def _u2_shell(self, command: str) -> str:
        """uiautomator2 自己的 shell 通道，**不经过 Shizuku**。

        uiautomator2 2.16.x 的 ``Device.shell`` 走本机 atx-agent 的 HTTP
        ``/shell``（实测 atx-agent 以 root 运行），注入的 ``input`` 事件能落到
        锁屏上；而经 patch_adb → Shizuku 那条 ``/system/bin/sh -c input ...``
        在 keyguard 上经常打空，表现就是「Unlock failed, keyguard still showing」。

        这里显式打 atx-agent 的 /shell，避免误用被 patch_adb 改过的 adbutils；
        拿不到 http 端点时才退回公开的 ``u2.shell``。
        """
        http = getattr(self.u2, "http", None)
        if http is not None:
            try:
                resp = http.post(
                    "/shell",
                    data={"command": command, "timeout": "30"},
                    timeout=40,
                )
                if getattr(resp, "status_code", 200) == 200:
                    payload = resp.json()
                    output = payload.get("output") or ""
                    # 诊断：注入类命令是否真的执行、坐标是多少、有没有报错
                    if command.startswith("input "):
                        self.logger.info(
                            f"u2 shell: {command} -> err={payload.get('error')!r} "
                            f"code={payload.get('exitCode')} out={output[:80]!r}"
                        )
                    return output
                self.logger.warning(f"u2 /shell HTTP {resp.status_code}: {command}")
            except Exception as error:
                self.logger.warning("u2 /shell failed: " + command + " -> " + str(error))
        try:
            result = self.u2.shell(command)
            return getattr(result, "output", "") or ""
        except Exception as error:
            self.logger.warning("u2 shell failed: " + command + " -> " + str(error))
            return ""

    def _shizuku_shell(self, command: str) -> str:
        """状态查询 / force-stop 等操作仍走 Shizuku。"""
        try:
            from core.android.shizuku import ShizukuClient

            client = ShizukuClient.active()
            if client is None:
                raise RuntimeError("ShizukuClient is not initialized")
            ok, result = client.execute_command(command)
            if not ok:
                raise RuntimeError(str(result))
            return getattr(result, "stdout", "") or ""
        except Exception as error:
            self.logger.warning("shizuku shell failed: " + command + " -> " + str(error))
            return ""

    def _shell(self, command: str) -> str:
        """兼容旧调用：默认走 Shizuku（事件注入请显式用 ``_u2_shell``）。"""
        return self._shizuku_shell(command)

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
            self._u2_shell("input keyevent " + KEYCODE_WAKEUP)
            # 熄屏很久后按 WAKEUP，锁屏界面要 1.5~2s 才真正绘制出来；
            # 之前只等 0.8s 就上滑，滑动落在黑屏/doze 上，密码盘根本没出来，
            # 后面点 PIN 全打空 -> "Unlock failed, keyguard still showing."
            time.sleep(2.0)

    def unlock(self) -> bool:
        """上滑呼出 PIN 盘，逐位点按密码，最后确认是否真的解锁。"""
        if not self.password:
            self.logger.warning(
                "Unlock password is empty (set android_unlock_password in Android settings)."
            )
            return not self.is_locked()
        swipe = self.settings.get("swipe") or {}
        start = self._scale(swipe.get("from", [540, 2000]))
        end = self._scale(swipe.get("to", [540, 900]))
        duration = int(swipe.get("duration_ms", 150))
        keypad = self.settings.get("keypad") or {}
        self.logger.info(
            f"unlock geometry: screen={self.screen_size()} swipe={start}->{end} "
            f"digits={len(self.password)} first_key={self._scale(keypad.get(self.password[0], (0, 0)))}"
        )
        # 上滑 + 点 PIN 整体重试两次：锁屏刚亮起时第一次上滑常常打空
        for attempt in range(1, 3):
            self._u2_shell(f"input swipe {start[0]} {start[1]} {end[0]} {end[1]} {duration}")
            time.sleep(1.8)
            for char in self.password:
                point = keypad.get(char)
                if point is None:
                    self.logger.warning("Keypad has no coordinate for digit: " + char)
                    return False
                x, y = self._scale(point)
                self._u2_shell(f"input tap {x} {y}")
                time.sleep(0.35)
            time.sleep(1.5)
            if not self.is_locked():
                return True
            self.logger.info(f"Unlock attempt {attempt} failed, retrying with a slower swipe.")
        return False

    def ensure_ready(self) -> bool:
        """确保屏幕点亮且已解锁。返回是否达成。"""
        self.wake()
        if not self.is_locked():
            return True
        retry = max(1, int(self.settings.get("unlock_retry", 2)))
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
