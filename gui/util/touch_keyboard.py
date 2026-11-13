# coding:utf-8
"""应用内自绘软键盘。

背景：Android 上系统输入法的文字提交链路到不了 Qt —— 输入法能收到按键、
能出候选词，但 `QtInputConnection` 的 native 回调没有把文字交给 QLineEdit，
表现就是「键盘弹得出来、点了没反应」。Qt 自带的 qtvirtualkeyboard 插件虽然
打进了包，但在 widget 应用里无法创建独立的 QML 窗口，同样用不了。

这里改用完全由 Qt 控件绘制的键盘，按键直接调用焦点控件的 insert/backspace，
绕开 Android 的 InputConnection 整条链路。默认数字面板（次数、时间、密码都是
数字），可切到字母面板给「指定学生」这类文本字段用。
"""

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import (
    QAbstractSpinBox,
    QApplication,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

# 每个面板是「若干行」，行内是 (标签, 跨列数, 动作) 三元组
_PANELS = {
    "num": [
        [("1", 1, "1"), ("2", 1, "2"), ("3", 1, "3"), ("4", 1, "4"), ("5", 1, "5")],
        [("6", 1, "6"), ("7", 1, "7"), ("8", 1, "8"), ("9", 1, "9"), ("0", 1, "0")],
        [(".", 1, "."), ("-", 1, "-"), (">", 1, ">"), ("(", 1, "("), (")", 1, ")")],
        [("退格", 1, "back"), ("清空", 1, "clear"), ("中文", 1, "ime"),
         ("ABC", 1, "alpha"), ("完成", 1, "done")],
    ],
    "alpha": [
        [("A", 1, "A"), ("B", 1, "B"), ("C", 1, "C"), ("D", 1, "D"), ("E", 1, "E"),
         ("F", 1, "F"), ("G", 1, "G"), ("H", 1, "H"), ("I", 1, "I"), ("J", 1, "J")],
        [("K", 1, "K"), ("L", 1, "L"), ("M", 1, "M"), ("N", 1, "N"), ("O", 1, "O"),
         ("P", 1, "P"), ("Q", 1, "Q"), ("R", 1, "R"), ("S", 1, "S"), ("T", 1, "T")],
        [("U", 1, "U"), ("V", 1, "V"), ("W", 1, "W"), ("X", 1, "X"), ("Y", 1, "Y"),
         ("Z", 1, "Z"), ("空格", 1, " "), (".", 1, "."), (">", 1, ">"), ("退格", 1, "back")],
        [("清空", 2, "clear"), ("中文", 2, "ime"), ("123", 2, "num"), ("完成", 4, "done")],
    ],
}

_LETTERS = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")


class TouchKeyboard(QWidget):
    """浮在当前窗口底部的自绘键盘。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TouchKeyboard")
        self.setAutoFillBackground(False)
        # 键盘自己绝不能抢焦点，否则 QLineEdit 一失焦，光标和选区就没了
        self.setFocusPolicy(Qt.NoFocus)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._target = None
        self._panel = "num"
        self._preview = None
        self._build_shell()
        self.hide()

    # ---------- 外观 ----------

    def _build_shell(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 6, 8, 8)
        outer.setSpacing(6)

        head = QHBoxLayout()
        head.setSpacing(8)
        self._preview = QLabel("", self)
        self._preview.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self._preview.setStyleSheet(
            "QLabel{color:#333;background:rgba(255,255,255,0.75);"
            "border:1px solid #d8d8d8;border-radius:4px;padding:2px 8px;}"
        )
        head.addWidget(self._preview, 1)
        outer.addLayout(head)

        self._grid_host = QWidget(self)
        self._grid_host.setFocusPolicy(Qt.NoFocus)
        self._grid_host.setStyleSheet("background:transparent;")
        outer.addWidget(self._grid_host, 1)

        self.setStyleSheet(
            "QWidget#TouchKeyboard{background:rgba(246,246,248,0.97);"
            "border-top:1px solid #dcdcdc;}"
        )

    def _rebuild(self, panel):
        self._panel = panel
        old = self._grid_host.layout()
        if old is not None:
            # 把旧 layout 摘下来交给临时 widget，随它一起销毁，避免
            # 「widget already has a layout」并且让旧按钮真正释放
            while old.count():
                item = old.takeAt(0)
                widget = item.widget()
                if widget is not None:
                    widget.setParent(None)
                    widget.deleteLater()
            # QWidget.setLayout 不会自动顶掉已有 layout，先把它转交给临时
            # widget 一并销毁，否则新 layout 装不上、旧按钮残留在界面上
            QWidget().setLayout(old)
        grid = QGridLayout(self._grid_host)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(5)
        rows = _PANELS[panel]
        cols = max(sum(span for _, span, _ in row) for row in rows)

        num_font = QFont(self.font())
        num_font.setPixelSize(18)
        num_font.setBold(True)

        for r, row in enumerate(rows):
            c = 0
            for label, span, action in row:
                btn = QPushButton(label, self._grid_host)
                btn.setFocusPolicy(Qt.NoFocus)
                btn.setFont(num_font if len(label) == 1 else self.font())
                btn.setMinimumHeight(2)
                btn.setStyleSheet(
                    "QPushButton{background:#ffffff;border:1px solid #d9d9d9;"
                    "border-radius:6px;color:#222;}"
                    "QPushButton:pressed{background:#e8e8e8;}"
                )
                btn.clicked.connect(lambda _=False, a=action: self._on_key(a))
                grid.addWidget(btn, r, c, 1, span)
                c += span
            grid.setRowStretch(r, 1)
        for c in range(cols):
            grid.setColumnStretch(c, 1)

    # ---------- 行为 ----------

    def _current_text(self):
        w = self._target
        if w is None:
            return ""
        if isinstance(w, QLineEdit):
            return w.text()
        if hasattr(w, "toPlainText"):
            return w.toPlainText()
        return ""

    def _refresh_preview(self):
        text = self._current_text()
        if len(text) > 40:
            text = "…" + text[-40:]
        self._preview.setText(text if text else "（空）")

    def _on_key(self, action):
        w = self._target
        if action == "done":
            self.hide()
            # 不清焦点的话，用户再点同一个输入框不会触发 focusChanged，
            # 键盘就再也弹不出来了
            if w is not None:
                w.clearFocus()
            return
        if action in ("num", "alpha"):
            self._rebuild(action)
            self._relayout()
            return
        if action == "ime":
            self._open_native_input()
            return
        if w is None:
            return

        if action == "back":
            if isinstance(w, QLineEdit):
                w.backspace()
            else:
                cursor = w.textCursor()
                cursor.deletePreviousChar()
                w.setTextCursor(cursor)
        elif action == "clear":
            if isinstance(w, QLineEdit):
                w.clear()
            else:
                w.clear()
        else:
            if isinstance(w, QLineEdit):
                w.insert(action)
            elif isinstance(w, (QTextEdit, QPlainTextEdit)):
                w.insertPlainText(action)
        self._refresh_preview()

    def _open_native_input(self):
        """中文输入：交给 Android 原生 EditText，输入完回填到 Qt 控件。"""
        w = self._target
        if w is None:
            return
        try:
            from gui.util import android_input
        except Exception:
            android_input = None
        if android_input is None or not android_input.available():
            # 没有原生通道（桌面端 / jnius 不可用）就退到字母面板
            self._rebuild("alpha")
            self._relayout()
            return

        initial = self._current_text()
        multiline = not isinstance(w, QLineEdit)
        # 原生对话框会整个盖在 Qt 窗口上，键盘先收起来
        self.hide()

        def _done(text):
            if text is None:
                return
            widget = self._target
            if widget is None:
                return
            text = str(text)
            try:
                if isinstance(widget, QLineEdit):
                    widget.setText(text)
                else:
                    widget.setPlainText(text)
                # 有些字段（confirm=False 的 text）只在 editingFinished 时落盘，
                # 手工 emit 一次，等价于用户敲完回车/点别处
                signal = getattr(widget, "editingFinished", None)
                if signal is not None:
                    signal.emit()
            except Exception:
                pass

        android_input.prompt("输入内容", initial, _done, multiline=multiline)

    # ---------- 定位 ----------
    def _relayout(self):
        parent = self.parentWidget()
        if parent is None:
            return
        self._rebuild_if_needed()
        rows = len(_PANELS[self._panel])
        ph = parent.height()
        # 行高按 46dp 走，但整体不超过父窗口的 52%
        want = rows * 46 + 44
        height = max(140, min(int(ph * 0.52), want))
        self.setGeometry(0, ph - height, parent.width(), height)
        self.raise_()

    def _rebuild_if_needed(self):
        if self._grid_host.layout() is None:
            self._rebuild(self._panel)

    def show_for(self, widget):
        if widget is None:
            return
        host = widget.window()
        if host is None:
            host = widget
        if self.parentWidget() is not host:
            self.setParent(host)
        self._target = widget
        self._rebuild_if_needed()
        self._refresh_preview()
        self._relayout()
        self.show()
        self.raise_()


def _is_keyboard_target(widget):
    """只有真正可编辑的文本控件才弹键盘。"""
    if not isinstance(widget, (QLineEdit, QTextEdit, QPlainTextEdit)):
        return False
    if isinstance(widget, QLineEdit) and widget.isReadOnly():
        return False
    # SpinBox 内部的 QLineEdit：用箭头调值就够了，交给原控件处理
    parent = widget.parentWidget()
    while parent is not None:
        if isinstance(parent, QAbstractSpinBox):
            return False
        parent = parent.parentWidget()
    return True


_installed = None


def install(app=None):
    """安装全局键盘。重复调用返回同一个实例。"""
    global _installed
    if _installed is not None:
        return _installed
    app = app or QApplication.instance()
    if app is None:
        return None
    keyboard = TouchKeyboard()
    _installed = keyboard

    def _on_focus_changed(_old, new):
        if _is_keyboard_target(new):
            keyboard.show_for(new)
            return
        # Android 上点键盘按钮（NoFocus）时 Qt 仍可能报一次「焦点变成 None」，
        # 但输入框自己还持有焦点；这种假失焦不能收键盘，否则按一个键就消失。
        if keyboard.isVisible() and keyboard._target is not None:
            try:
                if keyboard._target.hasFocus():
                    return
            except RuntimeError:
                # 控件已被销毁
                pass
        keyboard.hide()

    app.focusChanged.connect(_on_focus_changed)
    return keyboard
