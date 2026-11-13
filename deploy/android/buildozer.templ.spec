[app]
title = Baas on Android
package.name = boa
package.domain = top.qwq123
source.dir = .
source.include_exts = py, png, jpg, kv, atlas, qml, js, json, txt, apk
# 注：原来的 "deploy" 是无效项——buildozer 拿带尾斜杠的目录相对路径做 fnmatch，
# "deploy/" 匹配不到 "deploy"，从未生效，已移除以免误导。
# p4a_hook 依赖的 xml/java 不受 include_exts 影响：buildozer 把 --hook 的源码绝对路径
# 传给 p4a，hook 的 BASE_DIR 即源码目录，片段直接从源码读取，不进 .buildozer/android/app。
source.exclude_patterns = boa-*.apk
android.whitelist = *.apk
version = 0.1
# NOTE : requirements should be written in on line
requirements = {{ requirements }}
orientation = landscape
fullscreen = 1
android.archs = {{ arch }}
android.allow_backup = True
android.minapi = {{ min_api }}
android.ndk_path = {{ android_ndk_path }}
android.sdk_path = {{ android_sdk_path }}
p4a.url = https://github.com/XcantloadX/python-for-android.git
p4a.branch = develop
p4a.commit = 4838a0a2455783ad511478e44bc661ad5153bb42
p4a.bootstrap = qt
p4a.local_recipes = {{ local_recipes_path }}
android.permissions = android.permission.WRITE_EXTERNAL_STORAGE, android.permission.INTERNET, android.permission.INTERACT_ACROSS_USERS_FULL, android.permission.FOREGROUND_SERVICE, android.permission.FOREGROUND_SERVICE_DATA_SYNC, android.permission.WAKE_LOCK
android.add_jars = {{ jars_path }}
p4a.extra_args = --qt-libs=Core,Gui,Widgets --load-local-libs=plugins_platforms_qtforandroid --init-classes=
icon.filename = {{ icon_path }}
android.enable_androidx = True
android.entrypoint = org.baas.boa.MainActivity
# 常驻前台服务的 <service> 声明由 deploy/android/p4a_hook.py 在 before_apk_assemble 注入。
# 不能用 android.extra_manifest_application_arguments：buildozer 把它当「文件路径」open()，
# 且 p4a 模板只把它渲染到 <application> 的属性位置，放 <service> 子元素属于非法 XML。
# 服务类型用 dataSync（Java 侧常量 0x1），不用 specialUse：后者要求 compileSdk>=34。
# 注：Android 15 对 dataSync 有「每 24 小时最多 6 小时」超时；若测试机升到 Android 15
# 且要长期挂机，改 p4a_hook 注入的 foregroundServiceType 并显式设 android.api=35。

######### Shizuku #########
android.gradle_dependencies = dev.rikka.shizuku:api:13.1.5,dev.rikka.shizuku:provider:13.1.5,androidx.core:core:1.6.0,org.jetbrains.kotlin:kotlin-stdlib:1.9.22
# ps: androidx is not required by shizuku
p4a.hook = {{ p4a_hook_path }}
android.no-byte-compile-python = True

[buildozer]
log_level = 2
warn_on_root = 1
bin_dir = {{ bin_dir }}

