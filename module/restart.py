import time
from datetime import datetime

from core.utils import host_platform_is_android


def implement(self):
    if not self.is_android_device:
        return True
    cur_package = self.u2.app_current()['package']
    if cur_package != self.package_name:
        self.logger.warning("APP NOT RUNNING current package: " + cur_package)
        start(self)
        return True
    self.logger.info("CHECK RESTART")
    if check_need_restart(self):
        self.logger.info("current package: " + cur_package)
        self.logger.info("--STOP CURRENT BLUE ARCHIVE--")
        self.u2.app_stop(self.package_name)
        time.sleep(2)
        start(self)
        return True
    return True


def start(self):
    self.logger.info("-- START BLUE ARCHIVE --")
    if host_platform_is_android():
        # 统一走 _android_start_game：它会先确认游戏不在别的虚拟屏上跑着、
        # 再用 pidof 校验进程真的起来了（am start 的返回码不可靠）。
        started = self._android_start_game()
        self.logger.info(f"start game: {started}")
        # 冷启动瞬间虚拟屏上还没有任何图层，screencap 会返回 0 字节，
        # 直接进 to_main_page 就会在 cv2.resize 上抛 !ssize.empty()。
        # 先等游戏真的渲染出画面（稳定性循环里也是这么做的），再走识别。
        if started and hasattr(self, "_android_wait_for_picture"):
            pictured = self._android_wait_for_picture(120)
            self.logger.info(f"start game picture: {pictured}")
    else:
        activity_name = None if self.server == 'CN' else self.activity_name
        self.u2.app_start(self.package_name, activity_name)
    self.to_main_page()



def check_need_restart(self):
    now = datetime.now()
    if self.server == 'CN':
        if abs(time.time() - datetime(year=now.year, month=now.month, day=now.day, hour=4).timestamp()) <= 60:
            return True
    elif self.server == 'Global' or self.server == 'JP':
        if abs(time.time() - datetime(year=now.year, month=now.month, day=now.day, hour=3).timestamp()) <= 60:
            return True
    return False
