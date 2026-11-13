# coding:utf-8
"""应用内下拉选项浮层（Android 用）。

qfluentwidgets 的 `ComboBox` 下拉走 `ComboBoxMenu`（`RoundMenu` 的子类），
本质是一个 `Qt.Popup` 顶层窗口：半透明背景 + 阴影 + 揭示动画。Qt for Android
只有一个原生窗口，这类 popup 建得出来却不显示，表现就是「点下拉框没反应」。

这里把 `ComboBoxBase._showComboMenu` 换成应用内浮层：覆盖在当前窗口上的
半透明遮罩 + 选项卡片，点击选项直接回调 `combo._onItemClicked()`，与原来的
信号行为完全一致（`currentIndexChanged` / `currentTextChanged` 照常发）。
"""

from PyQt5.QtCore import Qt, QPoint
from PyQt5.QtWidgets import (
    QFrame,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

_ROW_H = 42           # 单行高度（dp）
_MAX_VISIBLE = 6      # 最多露出几行，超出滚动
_CARD_PAD = 6
_MIN_WIDTH = 190


class _OptionOverlay(QWidget):
    """盖住整个窗口的选项层；点遮罩空白处关闭。"""

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("ComboOverlay")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            "QWidget#ComboOverlay{background:rgba(0,0,0,0.16);}"
        )
        self.setFocusPolicy(Qt.NoFocus)
        self._combo = None
        self._card = None
        self.hide()

    # ---------- 关闭 ----------

    def mousePressEvent(self, event):
        # 点在卡片外（遮罩）就关掉；卡片自己会吞掉点击
        self.close_overlay()

    def close_overlay(self):
        combo = self._combo
        self.hide()
        if combo is not None:
            try:
                combo.dropMenu = None
            except Exception:
                pass
            try:
                combo.setDown(False)
            except Exception:
                pass

    # ---------- 展示 ----------

    def show_for(self, combo):
        try:
            items = list(getattr(combo, "items", []) or [])
        except Exception:
            items = []
        if not items:
            return
        host = combo.window()
        if host is None:
            return
        if self.parentWidget() is not host:
            self.setParent(host)
        self._combo = combo
        self._build(items, combo.currentIndex())
        self.setGeometry(0, 0, host.width(), host.height())
        self._place(combo, len(items))
        self.show()
        self.raise_()

    def _build(self, items, current):
        if self._card is not None:
            self._card.deleteLater()
            self._card = None

        card = QFrame(self)
        card.setObjectName("ComboCard")
        card.setStyleSheet(
            "QFrame#ComboCard{background:#ffffff;border:1px solid #d0d0d0;"
            "border-radius:8px;}"
        )
        outer = QVBoxLayout(card)
        outer.setContentsMargins(_CARD_PAD, _CARD_PAD, _CARD_PAD, _CARD_PAD)
        outer.setSpacing(0)

        area = QScrollArea(card)
        area.setWidgetResizable(True)
        area.setFrameShape(QFrame.NoFrame)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        area.setStyleSheet("QScrollArea{background:transparent;border:none;}")

        inner = QWidget(area)
        inner.setStyleSheet("background:transparent;")
        box = QVBoxLayout(inner)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(0)

        for index, item in enumerate(items):
            text = getattr(item, "text", None)
            if text is None:
                text = str(item)
            btn = QPushButton(text, inner)
            # 不抢焦点：一抢焦点，输入框的键盘就会被收掉
            btn.setFocusPolicy(Qt.NoFocus)
            btn.setMinimumHeight(_ROW_H)
            if index == current:
                btn.setStyleSheet(
                    "QPushButton{background:#e6f0fb;border:none;"
                    "border-radius:5px;color:#1a6fd4;text-align:left;"
                    "padding:0 12px;}"
                )
            else:
                btn.setStyleSheet(
                    "QPushButton{background:transparent;border:none;"
                    "border-radius:5px;color:#222;text-align:left;"
                    "padding:0 12px;}"
                    "QPushButton:pressed{background:#eceff3;}"
                )
            btn.clicked.connect(lambda _=False, i=index: self._choose(i))
            box.addWidget(btn)
        box.addStretch(1)

        area.setWidget(inner)
        outer.addWidget(area)
        self._card = card
        self._card_inner = inner

    def _place(self, combo, rows):
        host = self.parentWidget()
        if host is None or self._card is None:
            return
        width = max(combo.width(), _MIN_WIDTH)
        width = min(width, host.width() - 16)

        visible = min(rows, _MAX_VISIBLE)
        want = visible * _ROW_H + _CARD_PAD * 2 + 2

        below_top = combo.mapTo(host, QPoint(0, combo.height() + 4))
        above_top = combo.mapTo(host, QPoint(0, 0))
        space_below = host.height() - below_top.y() - 8
        space_above = above_top.y() - 8

        if want <= space_below:
            y, height = below_top.y(), want
        elif want <= space_above:
            y, height = space_above - want + 8, want
        elif space_below >= space_above:
            y, height = below_top.y(), max(_ROW_H * 2, space_below)
        else:
            height = max(_ROW_H * 2, space_above)
            y = max(8, space_above - height + 8)

        x = max(8, min(below_top.x(), host.width() - width - 8))
        self._card.setGeometry(x, y, width, height)

    def _choose(self, index):
        combo = self._combo
        self.close_overlay()
        if combo is None:
            return
        try:
            if index != combo.currentIndex():
                combo._onItemClicked(index)
        except Exception:
            pass


_installed = False


def install():
    """把 qfluentwidgets 的下拉换成应用内浮层。重复调用无害。"""
    global _installed
    if _installed:
        return True
    try:
        from qfluentwidgets.components.widgets.combo_box import ComboBoxBase
    except Exception:
        return False

    def _show_combo_menu(self):
        host = self.window()
        if host is None:
            return
        overlay = getattr(host, "_baas_combo_overlay", None)
        if overlay is None:
            overlay = _OptionOverlay(host)
            host._baas_combo_overlay = overlay
        overlay.show_for(self)
        # 借用基类的 dropMenu 字段做「打开与否」的状态，点击组合框可切换关闭
        try:
            self.dropMenu = overlay
        except Exception:
            pass

    def _close_combo_menu(self):
        host = self.window()
        overlay = getattr(host, "_baas_combo_overlay", None) if host else None
        if overlay is not None:
            overlay.close_overlay()
        try:
            self.dropMenu = None
        except Exception:
            pass

    ComboBoxBase._showComboMenu = _show_combo_menu
    ComboBoxBase._closeComboMenu = _close_combo_menu
    _installed = True
    return True
