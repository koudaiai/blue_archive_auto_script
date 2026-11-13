"""把用户配置持久化到 APK 私有目录根，避免升级 APK 时被清空。

p4a 启动时会先清空 ``<filesDir>/app`` 再解压 private.tar，所以 ``./config`` 下
运行时生成的内容（config.json / event.json / switch.json）每次升级都会丢，
表现是 android_test_mode 变回 false、解锁密码变空。

这里把权威副本放到 ``<filesDir>/user_config/<config_id>/``：

- 启动早期 ``restore_configs`` 把用户副本复制回 ``./config/<config_id>/``，
  之后 ``ConfigInitializer.check_config`` 走的是「补全缺失 key」而不是重置；
- 每次 ``ConfigSet.save`` 之后 ``snapshot_config`` 回写，保证副本始终最新。

``config/static.json`` 属于随包分发的静态数据（体积大、需要跟包更新），
不参与备份；桌面端没有 ``BAAS_ANDROID_INTERNAL_FILES_DIR``，所有函数直接空转。
"""

import os
import shutil

_CONFIG_SUBDIR = "config"
_USER_CONFIG_SUBDIR = "user_config"


def _internal_files_dir() -> str:
    """APK 私有目录根；非 Android 或显式关闭时返回空串。"""
    if os.getenv("BAAS_ANDROID", "").lower() not in {"1", "true", "yes", "on"}:
        return ""
    if os.getenv("BAAS_DISABLE_CONFIG_PERSIST", "").lower() in {"1", "true", "yes", "on"}:
        return ""
    return os.getenv("BAAS_ANDROID_INTERNAL_FILES_DIR", "").strip()


def user_config_root() -> str:
    root = _internal_files_dir()
    if not root:
        return ""
    return os.path.join(root, _USER_CONFIG_SUBDIR)


def _json_files(directory: str):
    try:
        names = os.listdir(directory)
    except OSError:
        return []
    return [name for name in names if name.endswith(".json") and os.path.isfile(os.path.join(directory, name))]


def _is_newer(source: str, target: str) -> bool:
    """source 比 target 新才覆盖。

    用 mtime 是为了保留「手动改过 app 内 config.json」这种用法：此时目标更新，
    不会被旧副本盖回去。
    """
    try:
        return os.path.getmtime(source) > os.path.getmtime(target)
    except OSError:
        return False


def restore_configs(project_root: str) -> int:
    """把 user_config/<id>/*.json 还原到 <project_root>/config/<id>/，返回还原文件数。"""
    root = user_config_root()
    if not root or not os.path.isdir(root):
        return 0
    target_root = os.path.join(project_root, _CONFIG_SUBDIR)
    restored = 0
    for config_id in os.listdir(root):
        source_dir = os.path.join(root, config_id)
        if not os.path.isdir(source_dir):
            continue
        target_dir = os.path.join(target_root, config_id)
        try:
            os.makedirs(target_dir, exist_ok=True)
        except OSError:
            continue
        for name in _json_files(source_dir):
            source = os.path.join(source_dir, name)
            target = os.path.join(target_dir, name)
            if os.path.exists(target) and not _is_newer(source, target):
                continue
            try:
                shutil.copy2(source, target)
                restored += 1
            except OSError:
                pass
    return restored


def snapshot_config(config_dir: str) -> None:
    """把某个 config 目录下的 json 回写到 user_config，供下次升级还原。"""
    root = user_config_root()
    if not root or not config_dir:
        return
    config_dir = os.path.abspath(config_dir)
    config_id = os.path.basename(config_dir)
    if not config_id:
        return
    target_dir = os.path.join(root, config_id)
    try:
        os.makedirs(target_dir, exist_ok=True)
    except OSError:
        return
    for name in _json_files(config_dir):
        try:
            shutil.copy2(os.path.join(config_dir, name), os.path.join(target_dir, name))
        except OSError:
            pass


def snapshot_all(project_root: str) -> None:
    """把 <project_root>/config 下所有配置目录回写一遍（首次安装时建立副本）。"""
    root = user_config_root()
    if not root:
        return
    target_root = os.path.join(project_root, _CONFIG_SUBDIR)
    try:
        config_ids = os.listdir(target_root)
    except OSError:
        return
    for config_id in config_ids:
        directory = os.path.join(target_root, config_id)
        if os.path.isdir(directory):
            snapshot_config(directory)
