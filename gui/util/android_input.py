# coding:utf-8
"""借 Android 原生 EditText 输入文本（中文 / 粘贴 / 长文本）。

Qt 在 Android 上收不到系统输入法的文字提交：`dumpsys input_method` 能看到
`mServedView=QtEditText`、`mIInputContext=QtInputConnection`，说明链路建起来了，
但 `commitText` 之后 QLineEdit 内容不变（换讯飞输入法对照同样如此），所以自绘
键盘只能敲 ASCII。

这里绕开 Qt：用 jnius 弹一个 Android 原生 `AlertDialog` + `EditText`，由系统输入法
直接驱动（中文、符号、粘贴、语音全都能用），确认后把字符串回填到 Qt 控件。
"""

import os
import queue
import traceback

from PyQt5.QtCore import QTimer


def _log(message):
    """把诊断信息落到应用私有目录（logcat 抓不到 Python 异常）。"""
    paths = []
    base = os.environ.get("BAAS_ANDROID_INTERNAL_FILES_DIR")
    if base:
        paths.append(os.path.join(base, "android_input.log"))
    try:
        if _activity is not None:
            paths.append(os.path.join(
                str(_activity.getFilesDir().getAbsolutePath()), "android_input.log"))
    except Exception:
        pass
    for candidate in (os.getcwd(), os.path.join(os.getcwd(), "files")):
        if candidate:
            paths.append(os.path.join(candidate, "android_input.log"))
    for path in paths:
        try:
            with open(path, "a", encoding="utf-8") as fp:
                fp.write(message + "\n")
            return path
        except Exception:
            continue
    return None

try:
    from jnius import PythonJavaClass, java_method
    _JNIUS_OK = True
except Exception:  # 桌面端没有 jnius，导入本模块不应报错
    _JNIUS_OK = False
    PythonJavaClass = object

    def java_method(*_args, **_kwargs):
        return lambda func: func


# PythonJavaClass 的两个回调：UI 线程执行，结果通过队列回到 Qt 主线程
class _Runnable(PythonJavaClass):
    __javainterfaces__ = ["java/lang/Runnable"]
    __javacontext__ = "app"

    def __init__(self, func):
        super().__init__()
        self._func = func

    @java_method("()V")
    def run(self):
        try:
            self._func()
        except Exception:
            _log("build failed: " + traceback.format_exc())


class _ClickListener(PythonJavaClass):
    __javainterfaces__ = ["android/content/DialogInterface$OnClickListener"]
    __javacontext__ = "app"

    def __init__(self, func):
        super().__init__()
        self._func = func

    @java_method("(Landroid/content/DialogInterface;I)V")
    def onClick(self, _dialog, _which):
        try:
            self._func()
        except Exception:
            _log("click failed: " + traceback.format_exc())


_refs = []          # 持有 Java 侧对象引用，防止被 GC
_results = queue.Queue()
_timers = []

_classes = None
_activity = None


def _load():
    global _classes, _activity
    if _classes is not None:
        return _classes
    if not _JNIUS_OK:
        _log("jnius unavailable")
        return None
    try:
        from jnius import autoclass

        from core.android.util import main_activity

        activity = main_activity()
        if activity is None:
            return None
        _activity = activity
        _classes = {
            "builder": autoclass("android.app.AlertDialog$Builder"),
            "edit": autoclass("android.widget.EditText"),
            "input_type": autoclass("android.text.InputType"),
            "layout_params": autoclass("android.view.WindowManager$LayoutParams"),
            # setText / setTitle 都有多个重载，pyjnius 猜不出 Python str 该走哪个
            # （会报 No methods called setText matching your arguments），
            # 显式构造 java.lang.String 才能命中 CharSequence 版本。
            "string": autoclass("java.lang.String"),
        }
    except Exception:
        _log("load failed: " + traceback.format_exc())
        return None
    return _classes


def available():
    """当前环境能否弹原生输入框。"""
    return _load() is not None


def prompt(title, initial="", on_done=None, multiline=False, hint=""):
    """弹出系统输入框。

    :param on_done: 回调，参数为输入文本；用户取消时传 None
    :return: 是否成功弹起
    """
    classes = _load()
    if classes is None or _activity is None:
        _log("prompt skipped: classes=%r activity=%r" % (classes is not None, _activity))
        return False

    state = {"sent": False}
    initial = "" if initial is None else str(initial)

    def _finish(text):
        # 确定/取消只会走一次，防御重复提交
        if state["sent"]:
            return
        state["sent"] = True
        if text is not None:
            # 拿回来的可能是 java.lang.String 代理对象，不转成 Python str
            # 的话后面 QLineEdit.setText 会失败
            try:
                text = str(text)
            except Exception:
                text = None
        _results.put(text)

    def _build():
        edit = classes["edit"](_activity)
        edit.setText(classes["string"](initial))
        flags = classes["input_type"].TYPE_CLASS_TEXT
        if multiline:
            flags = flags | classes["input_type"].TYPE_TEXT_FLAG_MULTI_LINE
        edit.setInputType(flags)
        try:
            edit.setSelection(len(initial))
        except Exception:
            pass

        def _read_text():
            # getText() 在不同 pyjnius 版本下可能已经是 str，也可能还是
            # Editable / java.lang.String 代理对象，两种都兜住
            value = edit.getText()
            if hasattr(value, "toString"):
                value = value.toString()
            return str(value)

        positive = _ClickListener(lambda: _finish(_read_text()))
        negative = _ClickListener(lambda: _finish(None))
        _refs.append(positive)
        _refs.append(negative)

        builder = classes["builder"](_activity)
        builder.setTitle(classes["string"](str(title)))
        if hint:
            builder.setMessage(classes["string"](str(hint)))
        builder.setView(edit)
        # 直接传 PythonJavaClass 实例，pyjnius 会自己生成 Java proxy；
        # 用 cast() 包一层反而会丢掉 proxy，Java 侧调用静默不执行。
        builder.setPositiveButton(classes["string"]("确定"), positive)
        builder.setNegativeButton(classes["string"]("取消"), negative)

        dialog = builder.create()
        try:
            # 一弹出就把软键盘顶上来，省得用户再点一下输入框
            dialog.getWindow().setSoftInputMode(
                classes["layout_params"].SOFT_INPUT_STATE_ALWAYS_VISIBLE)
        except Exception:
            pass
        dialog.show()
        _refs.append(dialog)
        _refs.append(edit)

    runnable = _Runnable(_build)
    _refs.append(runnable)
    # 引用表别无限增长：只留最近的一批
    if len(_refs) > 40:
        del _refs[: len(_refs) - 40]

    try:
        _activity.runOnUiThread(runnable)
    except Exception:
        _log("runOnUiThread failed: " + traceback.format_exc())
        return False

    if on_done is not None:
        timer = QTimer()
        timer.setInterval(60)

        def _tick():
            try:
                text = _results.get_nowait()
            except queue.Empty:
                return
            timer.stop()
            try:
                on_done(text)
            finally:
                if timer in _timers:
                    _timers.remove(timer)

        timer.timeout.connect(_tick)
        timer.start()
        _timers.append(timer)
    return True
