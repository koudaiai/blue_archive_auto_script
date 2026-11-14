import cv2
import numpy as np
import os
from core.utils import host_platform_is_android
from core.exception import SharedMemoryError
if host_platform_is_android():
    shared_memory = None
else:
    from multiprocessing import shared_memory

class SharedMemory:
    shm_map = {}

    @staticmethod
    def get(name):
        if name not in SharedMemory.shm_map:
            SharedMemory.shm_map[name] = SharedMemory(name)
        return SharedMemory.shm_map[name]

    @staticmethod
    def shm_exists(name):
        return name in SharedMemory.shm_map

    @staticmethod
    def set_data(name, data, size):
        if name not in SharedMemory.shm_map:
            # 句柄丢了（OCR 服务重建过共享内存、或模块被重新导入）时，
            # 按名字重新打开一次；打不开就抛 SharedMemoryError，让调用方
            # 退回 multipart 内联传输，而不是把整条任务打死。
            try:
                SharedMemory.shm_map[name] = SharedMemory(name)
            except SharedMemoryError:
                raise
            except Exception as error:  # noqa: BLE001
                # Android 上 shared_memory 模块是 None，会抛 AttributeError
                raise SharedMemoryError(f"Shared memory {name} unavailable: {error}") from error
        shm = SharedMemory.shm_map[name]
        if shm.size < size:
            raise SharedMemoryError(f"Shared memory {name} size {shm.size} not enough for {size}")
        shm.shm.buf[:size] = data

    @staticmethod
    def release(name):
        if name in SharedMemory.shm_map:
            SharedMemory.shm_map[name]._release()
            del SharedMemory.shm_map[name]

    def __init__(self, name):
        self.name = name
        self.size = None
        self.shm = None
        self._init()

    def _init(self):
        self.shm = shared_memory.SharedMemory(create=False, name=self.name)
        if self.shm is None:
            raise SharedMemoryError(f"Shared memory {self.name} not found")
        self.size = self.shm.size

    def _release(self):
        self.shm.close()
        self.shm.unlink()
