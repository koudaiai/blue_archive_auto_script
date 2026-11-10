# -*- coding: utf-8 -*-
"""把新角色追加进本地图库，让「日程指定学生」立刻能认出 ta。

加新角色不需要重训模型：只要用同一个 ONNX 编码器把这些角色的头像编码成 128 维向量，
追加到本地的 local_gallery.npz 即可（官方 gallery.npz 不动，避免 SHA256 校验失败）。

用法:
    # 1) 先用调试脚本从真实截图裁出头像
    python develop_tools/debug_lesson_recognition.py --image shot.png --save-crops out/

    # 2) 把裁出来的头像挂到某个角色名下（可多次 --image）
    python develop_tools/add_student_to_gallery.py --name "未花(泳装)" --image out/card0_slot0.png

    # 查看当前追加了哪些
    python develop_tools/add_student_to_gallery.py --list
"""
import argparse
import json
from pathlib import Path
import sys

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.student_recognition import StudentCatalog  # noqa: E402
from core.student_recognition.model_downloader import ensure_model_files  # noqa: E402
from core.student_recognition.recognizer import StudentRecognizer  # noqa: E402


def load_catalog():
    with open(ROOT / 'config' / 'static.json', encoding='utf-8') as f:
        return StudentCatalog(json.load(f)['student_names'])


def local_path(model_dir: Path) -> Path:
    return model_dir / 'local_gallery.npz'


def read_local(model_dir: Path, width: int):
    path = local_path(model_dir)
    if not path.is_file():
        return np.empty((0,), dtype=str), np.empty((0, width), dtype=np.float32)
    data = np.load(path, allow_pickle=False)
    return np.asarray(data['student_ids']).astype(str), np.asarray(data['embeddings'], dtype=np.float32)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--name', help='角色名（中文/英文/日文都可以，按名册解析）')
    parser.add_argument('--image', action='append', default=[], help='头像裁图，可多次')
    parser.add_argument('--model-dir', default=None)
    parser.add_argument('--list', action='store_true', help='列出已追加的角色')
    args = parser.parse_args()

    catalog = load_catalog()
    model_dir = Path(args.model_dir) if args.model_dir else ensure_model_files(ROOT)
    recognizer = StudentRecognizer(catalog, model_dir)
    if not recognizer.available:
        print('模型未就绪，先确认 config/cache/student_recognition 下的模型包完整')
        return 1

    width = int(recognizer.metadata.get('embedding_size', 128))
    ids, embeddings = read_local(model_dir, width)

    if args.list or not args.name:
        if not len(ids):
            print('本地图库为空（还没有追加过角色）')
            return 0
        counts = {}
        for sid in ids:
            counts[sid] = counts.get(sid, 0) + 1
        print(f'本地图库共 {len(ids)} 条向量，覆盖 {len(counts)} 个角色:')
        for sid, count in sorted(counts.items()):
            print(f'   {catalog.records[sid].canonical_name:<28} {sid:<28} {count} 条')
        return 0

    record = catalog.resolve(args.name)
    if record is None:
        print(f'名册里找不到 [ {args.name} ]，先用接近的写法再试；确认名字是否在 config/static.json 的 student_names 里')
        return 1
    if not args.image:
        print('至少给一个 --image')
        return 1

    crops = []
    for path in args.image:
        img = cv2.imread(path)
        if img is None:
            print('读不到图片:', path)
            return 1
        crops.append(img)

    new_embeddings = recognizer.encode_views(crops)
    if not len(new_embeddings):
        print('编码失败，检查图片是否正常')
        return 1

    # 同一个角色重复录入时覆盖旧向量
    keep = ids != record.student_id
    ids = np.concatenate([ids[keep], np.array([record.student_id] * len(new_embeddings))])
    embeddings = np.vstack([embeddings[keep], new_embeddings]) if len(embeddings) else new_embeddings

    path = local_path(model_dir)
    np.savez(path, student_ids=ids, embeddings=embeddings.astype(np.float32))
    print(f'已写入 {path}')
    print(f'{record.canonical_name} ({record.student_id}) 新增 {len(new_embeddings)} 条向量'
          f'（{len(crops)} 张图 × 5 视角），本地图库共 {len(ids)} 条')

    # 重新加载后再自检，否则用的是保存前的内存图库
    check_rec = StudentRecognizer(catalog, model_dir)
    check = check_rec.identify(crops)
    for path_, pred in zip(args.image, check):
        ok = 'OK' if pred.student_id == record.student_id else 'FAIL'
        print(f'  自检 {ok} {Path(path_).name}: -> {pred.name} score={pred.score:.3f}'
              f'{"（低于门槛，不会点击）" if not pred.accepted else ""}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
