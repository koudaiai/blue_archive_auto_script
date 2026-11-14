from core.device.uiautomator2_client import U2Client


class U2Screenshot:
    """uiautomator2 截图。

    注意：uiautomator2 的 screencap 走的是主屏，Android 上游戏跑在虚拟屏
    （overlay_display_devices 建的那块）时拿不到游戏画面，所以真机跑任务
    必须用 adb 截图方式。这里保留 U2 实现只为桌面模拟器。
    """

    def __init__(self, conn):
        self.serial = conn.serial
        self.u2 = U2Client.get_instance(self.serial)
        self.logger = getattr(conn, "logger", None)

    def _log(self, level: str, message: str):
        try:
            if self.logger is not None:
                getattr(self.logger, level)(message)
        except Exception:
            pass

    def screenshot(self):
        last_error = None
        for _ in range(5):
            try:
                image = self.u2.screenshot()
                if image is not None and getattr(image, "size", 0):
                    return image
                last_error = f'empty image: shape={getattr(image, "shape", None)}'
            except Exception as error:  # noqa: BLE001 - 重试后统一报错
                last_error = f'{type(error).__name__}: {error}'
        # 以前这里静默返回 None，下游拿到空图后在 cv2.resize 抛
        # "!ssize.empty()"，看不出真正原因；改成抛明确的异常。
        self._log("warning", f"uiautomator2 screenshot failed: {last_error}")
        raise TimeoutError(f"uiautomator2 screenshot failed: {last_error}")
