"""熄屏后的保活：前台服务 + 局部唤醒锁。

两个问题要分别解决，缺一个「每 4 小时开关一次游戏」就会跑不准：

1. Android 12+ 的 Cached Apps Freezer：进程进后台后被 SIGSTOP，Python 线程整体冻结。
   → 用常驻前台服务把进程提到前台优先级（``BaasForegroundService``）。
2. CPU suspend：前台服务只能防冻结，管不了 SoC 整体休眠；屏幕熄灭后 CPU 深睡，
   ``time.sleep`` 的定时循环同样会停摆，直到用户下次点亮屏幕才继续。
   → 持有 ``PARTIAL_WAKE_LOCK``，只保持 CPU 唤醒，屏幕仍由系统正常熄灭。

两者都只是 app 自己的权限/组件，不修改任何系统设置（不动亮度、stay_on、
screen_off_timeout、keyguard、cached_apps_freezer）。

对应实现见 ``deploy/android/src/main/java/org/baas/boa/BaasForegroundService.java``。
"""
from __future__ import annotations

from core.android.util import main_activity

# 必须留一个模块级引用：WakeLock 对象被 GC 后系统会自动释放锁。
_WAKE_LOCK = None


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


def ensure_wake_lock(logger=None) -> bool:
    """持有 PARTIAL_WAKE_LOCK，让熄屏后 CPU 不深睡、定时器能按时醒来。

    ``PARTIAL_WAKE_LOCK`` 只保持 CPU，允许屏幕关闭，不需要点亮屏幕或改亮度。
    """
    global _WAKE_LOCK
    if _WAKE_LOCK is not None:
        return True
    try:
        from jnius import autoclass

        activity = main_activity()
        if activity is None:
            if logger is not None:
                logger.warning("Wake lock: main activity unavailable.")
            return False
        Context = autoclass("android.content.Context")
        PowerManager = autoclass("android.os.PowerManager")
        manager = activity.getSystemService(Context.POWER_SERVICE)
        if manager is None:
            if logger is not None:
                logger.warning("Wake lock: PowerManager unavailable.")
            return False
        try:
            level = int(PowerManager.PARTIAL_WAKE_LOCK)
        except Exception:
            level = 1  # PowerManager.PARTIAL_WAKE_LOCK == 1
        lock = manager.newWakeLock(level, "baas:runtime")
        try:
            lock.setReferenceCounted(False)
        except Exception:
            pass
        lock.acquire()
        _WAKE_LOCK = lock
        if logger is not None:
            logger.info("PARTIAL_WAKE_LOCK acquired (screen can still turn off).")
        return True
    except Exception as error:
        if logger is not None:
            logger.warning("Wake lock acquire failed: " + str(error))
        return False


def ensure_runtime_keepalive(logger=None):
    """Python 入口处调用一次：拉起前台服务并持有唤醒锁。"""
    return ensure_foreground_service(logger), ensure_wake_lock(logger)


def release_wake_lock(logger=None) -> None:
    """用户点停止 / 应用退出时可调用；不调用也无妨，进程结束系统会回收。"""
    global _WAKE_LOCK
    if _WAKE_LOCK is None:
        return
    try:
        if _WAKE_LOCK.isHeld():
            _WAKE_LOCK.release()
    except Exception as error:
        if logger is not None:
            logger.warning("Wake lock release failed: " + str(error))
    _WAKE_LOCK = None
