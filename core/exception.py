import traceback
from datetime import datetime


class SharedMemoryError(Exception):
    """
        Shared memory error.
    """
    def __init__(self, message):
        self.message = message
        super().__init__(self.message)

class RequestHumanTakeOver(Exception):
    """
        Exception can't be handled by baas.
        1. flag_run = false (click stop button)
        2. unable to connect to emulator
    """

    def __init__(self, message="Request Human Take Over"):
        self.message = message
        super().__init__(self.message)


class PackageIncorrect(Exception):
    """
        every 20s core.picture.co_detect func didn't match a feature it will check the package through adb.
        possible reasons:
        1. Game crushed.
        2. When starting the game BAAS may click into browser in Global server.
    """

    def __init__(self, message="Package Incorrect"):
        self.message = message
        super().__init__(self.message)


class FunctionCallTimeout(Exception):
    """
        core.picture.co_detect func call timeout 600s reached.
        possible reasons:
        1. Meet unexpected ui.
        2. Game keeps loading.
    """

    def __init__(self, message="Function Call Timeout"):
        self.message = message
        super().__init__(self.message)


class OcrInternalError(Exception):
    """
        BAAS_ocr_server internal error
    """
    def __init__(self, message="Ocr Internal Error"):
        self.message = message
        super().__init__(self.message)


class LogTraceback:
    def __init__(self, title=None, message=None, context=None):
        traceback.print_exc()
        assert context is not None
        self.message = message
        self.context = context
        context.send('stop')
        self.context.logger.error(title)
        lines = message.split('\n')
        _lines = []
        for line in lines:
            while len(line) > 50:
                _lines.append(line[:50])
                line = line[50:]
            if line == '': continue
            _lines.append(line)
        for line in _lines:
            self.context.logger.error(line)
        self.context.logger.error('All activities stopped. Require human take over.')
        # 把完整日志落到 error.html：Android 上日志框没法翻页也没进 logcat，
        # 排查只能靠这份副本（路径为工作目录，即 files/app）。
        self.log_into_file()

    def log_into_file(self):
        try:
            if self.context.connection is None:
                return
            with open('error.html', 'a', encoding='utf-8') as f:
                f.write(f'\n===== {datetime.now()} =====\n')
                f.write(self.context.logger.logs)
                f.write('\n' + self.message + '\n')
        except Exception:
            pass

    def __str__(self):
        return self.message
