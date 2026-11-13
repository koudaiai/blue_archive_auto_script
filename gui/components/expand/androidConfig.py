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
                # 用 SpinBox 而不是文本框：Android 上软键盘输入不通（Qt 侧的
                # IME 事件根本没到控件，见 customized_ui 的说明），数值项改成
                # 点上下箭头就能调，完全不依赖键盘。
                'type': 'spin',
                'selection': {'min': 1, 'max': 24}
            },
            {
                'label': AndroidConfig.tr('每轮开启游戏时长（分钟）'),
                'key': 'android_test_keep_minutes',
                'type': 'spin',
                'selection': {'min': 1, 'max': 60}
            },
        ]
        super().__init__(parent=parent, configItems=configItems, config=config, context='AndroidConfig')
