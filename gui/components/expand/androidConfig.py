from PyQt5.QtCore import QObject

from .expandTemplate import TemplateLayout


class Layout(TemplateLayout):
    """Android 端运行设置：锁屏 PIN、空闲关游戏、稳定性测试。"""

    def __init__(self, parent=None, config=None):
        AndroidConfig = QObject()
        configItems = [
            {
                'label': AndroidConfig.tr('锁屏 PIN（熄屏后自动解锁用，留空则不尝试解锁）'),
                'key': 'android_unlock_password',
                'type': 'text'
            },
            {
                'label': AndroidConfig.tr('任务结束后关闭游戏（屏幕交给系统自动熄灭）'),
                'key': 'android_stop_game_when_idle',
                'type': 'switch'
            },
            {
                'label': AndroidConfig.tr('稳定性测试模式（只做定时开关游戏，不执行任务）'),
                'key': 'android_test_mode',
                'type': 'switch'
            },
            {
                'label': AndroidConfig.tr('测试间隔（小时）'),
                'key': 'android_test_interval_hours',
                'type': 'text'
            },
            {
                'label': AndroidConfig.tr('每轮开启游戏时长（分钟）'),
                'key': 'android_test_keep_minutes',
                'type': 'text'
            },
        ]
        super().__init__(parent=parent, configItems=configItems, config=config, context='AndroidConfig')
