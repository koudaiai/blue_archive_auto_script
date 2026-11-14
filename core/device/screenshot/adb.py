from adbutils import adb
import cv2
import numpy as np
import socket
import threading
import time

from core.utils import host_platform_is_android


class AdbScreenshot:
    # 空帧重试次数与间隔：游戏冷启动的瞬间虚拟屏还没有任何图层，
    # screencap 会返回 0 字节，直接解码就是空图，下游 cv2.resize 会抛
    # (-215:Assertion failed) !ssize.empty()。等一两秒通常就有画面了。
    _EMPTY_RETRY = 4
    _EMPTY_RETRY_INTERVAL = 0.4
    def __init__(self, conn):
        self.serial = conn.serial
        self.logger = conn.logger

        self.adb = adb.device(self.serial)
        self.display_id = None

        # Create a localhost listener on a random free port
        if host_platform_is_android():
            self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._server.bind(('127.0.0.1', 0))
            self._server.listen(1)
            self._host, self._port = self._server.getsockname()

    def __del__(self):
        if self._server:
            try:
                self._server.close()
            except Exception:
                pass

    def set_display_id(self, display_id):
        self.display_id = display_id

    def _accept_and_read(self, out_container):
        # Blocking accept and read all bytes until EOF
        conn, addr = self._server.accept()
        try:
            chunks = []
            while True:
                data = conn.recv(8192)
                if not data:
                    break
                chunks.append(data)
            out_container.append(b''.join(chunks))
        finally:
            try:
                conn.close()
            except Exception:
                pass

    def _capture_once(self) -> bytes:
        if host_platform_is_android() and self.display_id:
            # Binder IPC on Android cannot pass data larger than 500 KB,
            # so we have to pipe the screenshot data through a socket.
            # Thus we have to use sh to pipe the output of screencap to nc.
            cmd = f'screencap -p -d {self.display_id} | nc 127.0.0.1 {self._port}'
            out = []
            th = threading.Thread(target=self._accept_and_read, args=(out,), daemon=True)
            th.start()
            self.adb.shell(cmd, stream=False, encoding=None, timeout=10)
            # Wait for accept thread to finish reading
            th.join(10)
            if th.is_alive():
                raise TimeoutError('Timed out waiting for screenshot data')
            return out[0] if out else b''
        cmd = ['screencap', '-p']
        return self.adb.shell(cmd, stream=False, encoding=None)

    def screenshot(self):
        data = b''
        for attempt in range(self._EMPTY_RETRY):
            data = self._capture_once()
            if len(data) >= 500:
                image = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
                if image is not None and image.size:
                    return image
            if attempt + 1 < self._EMPTY_RETRY:
                time.sleep(self._EMPTY_RETRY_INTERVAL)

        # 连拍几次还是空帧：目标屏当前没有内容（游戏刚拉起、或屏被关掉）。
        # 抛明确的异常，避免下游抛 OpenCV 的 !ssize.empty() 让人无从判断。
        if host_platform_is_android() and self.display_id:
            raise TimeoutError(
                f'Empty screenshot on display {self.display_id} '
                f'(got {len(data)} bytes); the display may have nothing rendered yet'
            )
        self.logger.warning(f'Unexpected screenshot: {data}')
        return None


