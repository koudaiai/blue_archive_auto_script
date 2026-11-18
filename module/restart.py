import time
from datetime import datetime


def _get_current_package(self):
    if self.config.screenshot_method == "virtual_scrcpy":
        from core.device.virtual_scrcpy_client import VirtualScrcpyClient
        return VirtualScrcpyClient.get_instance(self.serial).get_foreground_package()
    return self.u2.app_current()['package']


def implement(self):
    if not self.is_android_device:
        return True
    cur_package = _get_current_package(self)
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
        start(self, recreate_virtual_scrcpy=True)
        return True
    return True


def start(self, recreate_virtual_scrcpy=False):
    self.logger.info("-- START BLUE ARCHIVE --")
    activity_name = self.activity_name
    if self.server == 'CN' and self.config.screenshot_method != 'virtual_scrcpy':
        activity_name = None
    if self.config.screenshot_method == "virtual_scrcpy":
        from core.device.virtual_scrcpy_client import VirtualScrcpyClient
        if recreate_virtual_scrcpy:
            self.logger.info("Recreate virtual_scrcpy session before app start")
            cli = VirtualScrcpyClient.recreate_instance(self.serial)
        else:
            cli = VirtualScrcpyClient.get_instance(self.serial)
        cli.launch_app(self.package_name, activity_name)
    else:
        # android_companion 模式下 app_start 内部会 awaitGameInput，
        # 而 SocketBroker 把它硬编码成只等 10 秒；蔚蓝档案冷启动常要 15~25 秒，
        # 第一次必然超时。此时 am start 已经发出、游戏正在启动，重试就能拿到焦点窗口。
        last_error = None
        for attempt in range(1, 4):
            try:
                self.u2.app_start(self.package_name, activity_name)
                last_error = None
                break
            except Exception as error:
                last_error = error
                self.logger.warning("app_start attempt " + str(attempt) + " failed: " + str(error))
                time.sleep(3)
        if last_error is not None:
            raise last_error
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
