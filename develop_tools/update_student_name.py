# Usage:
#   python develop_tools/update_student_name.py
#   python develop_tools/update_student_name.py --proxy http://127.0.0.1:10808
#   需要代理时也可以设置环境变量: set HTTPS_PROXY=http://127.0.0.1:10808
#
# 数据源: https://schaledb.com/data/{cn,en,jp}/students.json
# 旧地址 raw.githubusercontent.com/SchaleDB/SchaleDB 的 data 目录最后更新停在
# 2024-08-20，之后不再更新，新角色永远拉不到，所以改为 schaledb.com。
#
# 脚本会做三件事:
#   1. 下载三服数据，存到 src/student_name_raw/{cn,en,jp}_student.json
#   2. 重新生成 student_names 并回写 core/config/default_config.py
#   3. 若存在 config/static.json（运行时配置），同步更新其中的 student_names
import json
import os
import re
import sys
import time

import requests

# (字段前缀, 文件名, IsReleased 下标)
SERVERS = [("CN", "cn", 2), ("Global", "en", 1), ("JP", "jp", 0)]
URL = "https://schaledb.com/data/{}/students.json"

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(ROOT, "src", "student_name_raw")
DEFAULT_CONFIG = os.path.join(ROOT, "core", "config", "default_config.py")
RUNTIME_STATIC = os.path.join(ROOT, "config", "static.json")

STATIC_BLOCK_RE = re.compile(r"(STATIC_DEFAULT_CONFIG = ''')(.*?)(''')", re.S)
STUDENT_KEY = '"student_names": ['


def download(session, server):
    last_error = None
    for attempt in range(5):
        try:
            r = session.get(URL.format(server), timeout=(30, 180))
            r.raise_for_status()
            return r.json()
        except Exception as e:  # 代理链路偶发超时，重试
            last_error = e
            print(f"  {server} attempt {attempt + 1} failed: {type(e).__name__}")
            time.sleep(2)
    raise last_error


def normalize_name(name):
    return name.replace("（", "(").replace("）", ")")


def build_student_names(students_by_server):
    """按 Id 合并三服数据，生成 student_names 列表。

    排序沿用游戏内的 DefaultOrder（0 = 最早实装的 爱露），倒序 = 新角色在前，
    与旧版本名单顺序一致。
    """
    ids = set()
    for data in students_by_server.values():
        ids.update(data.keys())

    entries = []
    for student_id in ids:
        item = {}
        order = 0
        for prefix, server, released_index in SERVERS:
            student = students_by_server[server].get(student_id) or {}
            name = normalize_name(student.get("Name") or "")
            item[prefix + "_name"] = name
            released = student.get("IsReleased") or [False, False, False]
            item[prefix + "_implementation"] = bool(name) and bool(released[released_index])
            if student.get("DefaultOrder") is not None:
                order = student["DefaultOrder"]
        entries.append((order, int(student_id), item))

    entries.sort(key=lambda x: (x[0], x[1]), reverse=True)
    # 别名（中/英/日任一）重复时只清掉冲突的那个别名，条目保留；
    # 三个别名全部重复说明是同名同人的重复条目（如两个「星野（武装）」），才整条丢弃。
    unique = []
    used_aliases = set()
    dropped = []
    blanks = []
    for _, _, entry in entries:
        keys = ("CN_name", "Global_name", "JP_name")
        present = [key for key in keys if entry[key]]
        collision = [key for key in present if entry[key].casefold() in used_aliases]
        if len(collision) == len(present):
            dropped.append(entry["Global_name"] or entry["CN_name"])
            continue
        for key in collision:
            blanks.append((entry["Global_name"] or entry["CN_name"], key, entry[key]))
            entry[key] = ""
        for key in present:
            if entry[key]:
                used_aliases.add(entry[key].casefold())
        unique.append(entry)
    if dropped:
        print(f"丢弃完全重复的条目 {len(dropped)} 个: {dropped}")
    if blanks:
        print(f"清空冲突别名 {len(blanks)} 处: {blanks}")
    return unique


def find_array_end(text, start):
    """从 text[start] 处的 '[' 开始，返回匹配的 ']' 下标。"""
    depth = 0
    in_string = False
    escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                return i
    raise ValueError("student_names 数组没有闭合")


def detect_indent(text, arr_start):
    """探测数组元素与对象字段的缩进，返回 (元素缩进, 步长)。"""
    first_nl = text.find("\n", arr_start)
    if first_nl < 0:
        return 4, 4
    second_nl = text.find("\n", first_nl + 1)
    item_line = text[first_nl + 1: second_nl]
    item_indent = len(item_line) - len(item_line.lstrip())
    third_nl = text.find("\n", second_nl + 1)
    field_line = text[second_nl + 1: third_nl]
    field_indent = len(field_line) - len(field_line.lstrip())
    step = field_indent - item_indent
    if item_indent <= 0 or step <= 0:
        return 4, 4
    return item_indent, step


def dump_array(entries, item_indent=4, step=2, eol="\n"):
    """按探测到的缩进序列化，保持与原文件一致的排版。"""
    text = json.dumps(entries, ensure_ascii=False, indent=step)
    prefix = " " * (item_indent - step) if item_indent > step else ""
    return text.replace("\n", eol + prefix)


def replace_student_names(text, entries, eol="\n"):
    pos = text.find(STUDENT_KEY)
    if pos < 0:
        raise ValueError('没有找到 "student_names": [')
    arr_start = pos + len(STUDENT_KEY) - 1
    arr_end = find_array_end(text, arr_start)
    item_indent, step = detect_indent(text, arr_start)
    return text[:arr_start] + dump_array(entries, item_indent, step, eol) + text[arr_end + 1:]


def update_default_config(entries):
    # newline="" 保留原文件的 CRLF/LF，避免整个文件被改写
    with open(DEFAULT_CONFIG, "r", encoding="utf-8", newline="") as f:
        src = f.read()

    match = STATIC_BLOCK_RE.search(src)
    if match is None:
        raise ValueError("default_config.py 里没有找到 STATIC_DEFAULT_CONFIG")

    old_block = match.group(2)
    json.loads(old_block)  # 先确认能解析，避免写坏文件
    eol = "\r\n" if "\r\n" in old_block else "\n"
    new_block = replace_student_names(old_block, entries, eol=eol)
    json.loads(new_block)  # 写完再校验一次

    new_src = src[:match.start(2)] + new_block + src[match.end(2):]
    with open(DEFAULT_CONFIG, "w", encoding="utf-8", newline="") as f:
        f.write(new_src)
    return len(json.loads(old_block)["student_names"]), len(entries)


def update_runtime_static(entries):
    if not os.path.exists(RUNTIME_STATIC):
        return None
    with open(RUNTIME_STATIC, "r", encoding="utf-8", newline="") as f:
        src = f.read()
    data = json.loads(src)
    before = len(data.get("student_names") or [])
    data["student_names"] = entries
    # 尽量沿用文件原本的缩进与换行
    indent = 2 if '\n  "' in src[:2000] else 4
    text = json.dumps(data, ensure_ascii=False, indent=indent)
    if "\r\n" in src:
        text = text.replace("\n", "\r\n")
    with open(RUNTIME_STATIC, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    return before, len(entries)


def parse_proxy(argv):
    """支持 --proxy http://ip:port，其次读环境变量。"""
    for i, arg in enumerate(argv):
        if arg == "--proxy" and i + 1 < len(argv):
            return argv[i + 1]
        if arg.startswith("--proxy="):
            return arg.split("=", 1)[1]
    return os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")


def load_cached():
    """--from-cache: 直接用 src/student_name_raw 里已下载的数据，不联网。"""
    students_by_server = {}
    for _, server, _ in SERVERS:
        path = os.path.join(RAW_DIR, server + "_student.json")
        with open(path, "r", encoding="utf-8") as f:
            students_by_server[server] = json.load(f)
        print(f"cached {server}: {len(students_by_server[server])} students")
    return students_by_server


def main():
    proxy = parse_proxy(sys.argv[1:])
    print("proxy:", proxy or "(none)")
    session = requests.Session()
    if proxy:
        session.proxies.update({"http": proxy, "https": proxy})
    session.headers.update({"User-Agent": "BAAS-update-student-name"})

    if "--from-cache" in sys.argv[1:]:
        students_by_server = load_cached()
    else:
        if not os.path.isdir(RAW_DIR):
            os.makedirs(RAW_DIR)
        students_by_server = {}
        for _, server, _ in SERVERS:
            data = download(session, server)
            students_by_server[server] = data
            path = os.path.join(RAW_DIR, server + "_student.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            print(f"downloaded {server}: {len(data)} students -> {path}")

    entries = build_student_names(students_by_server)
    cn_released = sum(1 for e in entries if e["CN_implementation"])
    print(f"student_names: {len(entries)} entries, CN released {cn_released}")

    before, after = update_default_config(entries)
    print(f"default_config.py student_names: {before} -> {after}")

    runtime = update_runtime_static(entries)
    if runtime:
        print(f"config/static.json student_names: {runtime[0]} -> {runtime[1]}")
    else:
        print("config/static.json 不存在，跳过")

    return 0


if __name__ == "__main__":
    sys.exit(main())
