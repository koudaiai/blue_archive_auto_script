"""启动 Java 侧的常驻前台服务。

屏幕熄灭后，Android 12+ 会把后台进程列入 cached 队列并冻结（SIGSTOP），
导致 Python 的调度定时器停摆。把进程挂到一个前台服务上可以避免这一点，
且不需要任何特权或系统设置改动。

对应实现见 ``deploy/android/src/main/java/org/baas/boa/BaasForegroundService.java``。
"""
from __future__ import annotations

from core.android.util import main_activity


def ensure_foreground_service(logger=None) -> bool:
    """幂等地拉起前台服务；失败只打日志，不影响主流程。"""
    try:
        from jnius import autoclass

        activity = main_activity()
        if activity is None:
            if logger is not None:
                logger.warning("Foreground service: main activity unavailable.")
            return False
        service = autoclass("org.baas.boa.BaasForegroundService")
        service.ensureRunning(activity.getApplicationContext())
        if logger is not None:
            logger.info("Foreground service started.")
        return True
    except Exception as error:
        if logger is not None:
            logger.warning("Foreground service start failed: " + str(error))
        return False
