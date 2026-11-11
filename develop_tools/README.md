# develop_tools

面向开发者的辅助脚本，不参与 BAAS 运行时，仅在维护数据 / 排查问题时手动执行。

## 约定

- **统一用仓库自带环境执行**，不要用系统 Python：

  ```bat
  .venv\Scripts\python.exe develop_tools\xxx.py
  ```

- **需要联网时走代理**（`schaledb.com`、GitHub Release 在国内不稳定）。本机 Clash Verge 的混合端口是 `10808`：

  ```bat
  set HTTPS_PROXY=http://127.0.0.1:10808
  ```

  注意：环境里若已有别的 `HTTPS_PROXY`（例如某个 3779 端口），会覆盖你的设置，用脚本的 `--proxy` 参数最稳。

- 本文档里的新脚本（`update_student_name.py`、`debug_lesson_recognition.py`、`add_student_to_gallery.py`）都用 `__file__` 定位仓库根目录，**在哪个目录执行都可以**；但部分老脚本用相对路径（见下表备注），需要 `cd develop_tools` 之后再跑。

---

## 一、学生名册

咖啡厅邀请下拉框、日程指定学生识别、配置校验共用同一份 `student_names`（在 `core/config/default_config.py` 的 `STATIC_DEFAULT_CONFIG` 里）。

### update_student_name.py

从 [SchaleDB](https://schaledb.com) 拉三服学生数据，重新生成 `student_names`。

```bat
:: 联网刷新（推荐开着代理）
.venv\Scripts\python.exe develop_tools\update_student_name.py --proxy http://127.0.0.1:10808

:: 不联网，用上次下载的缓存重算
.venv\Scripts\python.exe develop_tools\update_student_name.py --from-cache
```

**它会做三件事**

1. 下载 `https://schaledb.com/data/{cn,en,jp}/students.json`，存到 `src/student_name_raw/{cn,en,jp}_student.json`
2. 重新生成名册，回写 `core/config/default_config.py`
3. 同步写出 `config/static.json`

**排序**：按 SchaleDB 的 `DefaultOrder` 倒序（0 = 最早实装的「爱露」），也就是**新角色排在前面**。

**去重规则**（重要）：`StudentCatalog` 要求中/英/日三个别名全局唯一，所以

- 只有一个别名冲突 → 清空那个字段，条目保留（例：`瞬(泳装)` 与 `雪玲(泳装)` 日文名都是 `シュン(水着)`，保留条目、日文名置空）
- 三个别名全冲突 → 判定为同名同人的重复条目，整条丢弃（例：两个 `星野（武装）` 单位）

**注意**

- 写回时保留原文件的缩进与 `CRLF`，`git diff` 只会显示名册那一段
- ⚠️ `window.py` 的 `check_static_config()` **每次启动都会用 `default_config.py` 覆盖重写 `config/static.json`**，所以名册只能改 `default_config.py`，直接改 `static.json` 无效
- 数据源变更历史：早期抓的是 `raw.githubusercontent.com/SchaleDB/SchaleDB` 的 `data/` 目录，该目录最后更新停在 2024-08-20，之后拉不到新角色，已换到 `schaledb.com`

---

## 二、日程「指定学生」识别

### 背景

旧方案是**头像模板匹配**：用 94 张学生头像 PNG 做模板，靠滚屏 + 固定坐标截图去比对。游戏改成新版「全部日程」弹窗（一屏 3×3 卡片）后整套失效，模板在提交 `870ddc33` 里被删除，那段代码至今仍在仓库里（`module/lesson.py` 的 `invite_favor_student`），但名册表为空，配置了名字也不会生效。

现在的实现来自 PR #547（kosetsu905），思路是**向量检索**：

```
截图(1280×720)
  → FixedLessonLayout：按固定坐标裁 3×3 卡片，每卡最多 3 个头像(62×58)
  → StudentRecognizer：每个头像取 5 个视角(原图+4 个平移/缩放) → 96×96
  → MobileNetV3-Small ONNX：输出 128 维向量（L2 归一化）
  → 与 gallery.npz（690 条 = 270 身份 × 1~3 视角）算余弦 → 全局 Top-1
  → 同时满足「命中目标 + 粉框 + 卡片可执行 + 分数达门槛」才点击
```

**仓库里不需要任何学生图片**，只有模型包：

```
config/cache/student_recognition/1.0.0/
├─ student_encoder.onnx   (4.0 MB，MobileNetV3-Small)
├─ gallery.npz            (330 KB，270 身份 / 690 条向量)
├─ student_encoder.json   (预处理参数：mean/std、输入尺寸、embedding 维数)
└─ SHA256SUMS             (下载校验)
```

首次使用时从 `kosetsu905/blue_archive_auto_script_ai` 的 Release 自动下载并校验 SHA256；`MODEL_VERSION` 写死在 `model_downloader.py`，**不会自动升级**。

### debug_lesson_recognition.py

**不需要日程券、不需要连模拟器**，给一张截图就能看识别结果。

```bat
:: 基本用法
.venv\Scripts\python.exe develop_tools\debug_lesson_recognition.py --image shot.png

:: 把裁到的头像存成 PNG（用来检查裁切位置对不对）
.venv\Scripts\python.exe develop_tools\debug_lesson_recognition.py --image shot.png --save-crops out\

:: 指定 9 张卡片的状态（默认全按 available）
.venv\Scripts\python.exe develop_tools\debug_lesson_recognition.py --image shot.png --statuses available available done ...
```

输出示例：

```
名册身份数: 280 | 模型可用: True | load_error: None
相似度门槛 min_score: 0.75（config/student_recognition.json 可改，0 = 不设门槛）
识别到卡片: 1 | recognition_error: None

[卡片 0] state=available click_point=(297, 252) bbox=(129,181)-(466,324)
  头像 slot0 粉框=True -> Koyuki (Pajamas) (koyuki_pajamas) score=0.477 margin=0.008 [低于门槛]

配置的优先学生: ['Shiroko Terror', 'Hoshino (Battle)', ...]
=> 不会触发指定学生（没有卡片同时满足 命中+粉框+可执行）
```

**怎么读**

| 字段 | 含义 |
|---|---|
| `click_point` | 命中后会点的坐标，和 `fixed_layout.py` 的固定布局一致 |
| `粉框=True` | 该头像当前可获得好感（HSV 判色，要求至少两条外边缘是粉色） |
| `score` | 与图库最相似身份的余弦相似度，实测正确样本中位数 0.88 |
| `[低于门槛]` | 分数 < `min_score`，即使命中目标也不会点 |
| `recognition_error` | 布局解析异常信息，正常为 `None` |

### add_student_to_gallery.py

把**图库还没收录的角色**加进去，用于新角色上线后立即可识别 —— **不需要重训模型**，因为编码器是通用的，只需要给该角色补几条参考向量。

```bat
:: 录入（同角色重复录入会覆盖旧向量）
.venv\Scripts\python.exe develop_tools\add_student_to_gallery.py --name "心" --image out\card0_slot0.png

:: 多张不同角度一起录（识别更稳）
.venv\Scripts\python.exe develop_tools\add_student_to_gallery.py --name "心" --image a.png --image b.png

:: 看当前都追加了谁
.venv\Scripts\python.exe develop_tools\add_student_to_gallery.py --list
```

输出：

```
已写入 config\cache\student_recognition\1.0.0\local_gallery.npz
心 (kokoro) 新增 5 条向量（1 张图 × 5 视角），本地图库共 5 条
  自检 OK card0_slot0.png: -> Kokoro score=1.000
```

**设计要点**

- 官方 `gallery.npz` 受 `SHA256SUMS` 校验约束，改动会被识别为损坏并重新下载，因此追加内容写入**独立的 `local_gallery.npz`**，识别时与官方图库拼接检索
- `--name` 支持中/英/日任一写法，按 `student_names` 名册解析；写不进名册的角色（`student_id` 查不到）会直接报错
- 写入后会自动重新加载并自检，显示 `OK` / `FAIL`

### 推荐工作流

```bat
:: 1. 截图「全部日程」（有想加的角色出现即可，不消耗日程券）
:: 2. 裁头像并看识别结果
.venv\Scripts\python.exe develop_tools\debug_lesson_recognition.py --image shot.png --save-crops out\

:: 3. 挑出目标角色的头像，挂到名字下
.venv\Scripts\python.exe develop_tools\add_student_to_gallery.py --name "霞(泳装)" --image out\card2_slot1.png

:: 4. 重启 BAAS 生效
```

### 相似度门槛

配置在 `config/student_recognition.json`（首次运行时自动生成）：

```json
{
  "min_score": 0.75,
  "_comment": "识别相似度门槛：低于该值不点击；填 0 表示不设门槛"
}
```

默认 `0.75` 来自回归数据：用 65 张真实游戏头像模板测试，正确样本最低 0.761、中位 0.884，唯一一次误认（`Moe → Saki`）分数 0.747。门槛 0.75 可以拦掉这次误认、同时保留全部正确样本。

**漏点就调低**（如 0.72），**还点错就调高**（如 0.78）。

---

## 三、其他工具

| 脚本 | 用途 |
|---|---|
| `generate_dataclass_code.py` | 由 `default_config.py` 里的 JSON 生成 `core/config/generated_user_config.py` 与 `generated_static_config.py`。**改了配置字段后必须重跑**，否则 `Config(**json)` 会报缺少参数。⚠️ 用相对路径写 `../core/config/...`，必须 `cd develop_tools` 后执行 |
| `config_translation_generator.py` | 生成 `ConfigTranslation` 翻译表；注意文件头写明不要直接替换现成翻译文件 |
| `auto_translate.py` | 调用在线翻译批量补翻译（依赖 `translators` 库） |
| `demo_telegram_push.py` | 不依赖游戏，单独验证 `core/pushkit.py` 的 Telegram 推送链路 |
| `explore_task_data_generator.py` | 生成 `explore_normal_task` 用的推图网格数据，用法见同目录 `explore_task_data_generator_usage.txt` |
| `test_explore_task_data.py` | 推图数据的手动校验脚本 |
| `taskDataFixer.py` | 修正任务配置数据 |
| `lesson/lesson_affection_student_image_extractor.py` | **已废弃**。旧方案用：从截图按坐标裁头像存进 `src/images/{server}/lesson_affection/`，那个目录和整套模板匹配已在 `870ddc33` 删除。现在裁头像请用 `debug_lesson_recognition.py --save-crops` |
| `ActivityInfomations.txt` | 活动资料速查，非可执行脚本 |

---

## 四、排障

**日程识别完全不动，日志只有 `Lesson Inviting favor student.`**
说明名册或模型没起来。先跑 `debug_lesson_recognition.py`：`模型可用: False` 就是模型包问题（删掉 `config/cache/student_recognition` 让它重新下载，注意需要代理，单文件 15s 超时）；`名册身份数: 0` 就是 `static.json` 里 `student_names` 空了。

**日志出现 `Student roster is invalid`**
名册有重复别名（中/英/日任一）。跑一次 `update_student_name.py --from-cache` 重新生成即可，它会自动处理冲突别名。

**咖啡厅下拉框角色少 / 顺序怪**
先确认 `config/static.json` 的 `student_names` 条数；它每次启动会被 `default_config.py` 覆盖重写，所以改完 `default_config.py` 必须**重启**。顺序由 `DefaultOrder` 决定，新角色在前。

**推送 / 拉取 GitHub 报 `CONNECT tunnel failed 502`**
环境里的代理变量指向了一个不可用的端口。清掉再指定 Clash：

```bat
set HTTPS_PROXY=
set HTTP_PROXY=
git -c http.proxy=http://127.0.0.1:10808 -c https.proxy=http://127.0.0.1:10808 push
```
