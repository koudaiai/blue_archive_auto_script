# -*- coding: utf-8 -*-
"""离线调试「日程指定学生」识别，不需要日程券、不需要连设备。

用法:
    python develop_tools/debug_lesson_recognition.py --image shot.png
    python develop_tools/debug_lesson_recognition.py --image shot.png --save-crops out/
    python develop_tools/debug_lesson_recognition.py --image shot.png --statuses available done ...

截图要求: 游戏「全部日程」弹窗，1280x720 最佳（其它分辨率会缩放）。
statuses 对应 9 张卡片的游戏状态，默认全部按 available 处理。
"""
import argparse
import json
import os
from pathlib import Path
import sys

import cv2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.student_recognition import StudentCatalog, StudentRecognitionService  # noqa: E402


def load_rows():
    with open(ROOT / 'config' / 'static.json', encoding='utf-8') as f:
        return json.load(f)['student_names']


def load_priorities():
    path = ROOT / 'config' / 'default_config' / 'config.json'
    if not path.exists():
        return []
    with open(path, encoding='utf-8') as f:
        cfg = json.load(f)
    return cfg.get('lesson_favorStudent') or []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--image', required=True)
    parser.add_argument('--server', default='CN')
    parser.add_argument('--statuses', nargs='*', default=None,
                        help='9 张卡片的状态，默认全部 available')
    parser.add_argument('--save-crops', default=None, help='把裁到的头像存成 PNG')
    args = parser.parse_args()

    image = cv2.imread(args.image)
    if image is None:
        print('读不到图片:', args.image)
        return 1

    rows = load_rows()
    catalog = StudentCatalog(rows)
    service = StudentRecognitionService(rows, ROOT)
    print('名册身份数:', len(catalog.records), '| 模型可用:', service.available,
          '| load_error:', service.load_error)
    if not service.available:
        print('模型未就绪，往下的识别结果不可信')

    statuses = args.statuses or ['available'] * 9
    if len(statuses) < 9:
        statuses += ['unavailable'] * (9 - len(statuses))

    cards = service.recognize_lesson(image, statuses, args.server)
    print('识别到卡片:', len(cards), '| recognition_error:', service.recognition_error)
    if not cards:
        print('没找到卡片。可能原因：截图不是「全部日程」弹窗、分辨率不对、或卡片位置与固定布局不符。')
        return 0

    if args.save_crops:
        os.makedirs(args.save_crops, exist_ok=True)

    for card in cards:
        print()
        print(f'[卡片 {card.index}] state={card.state} click_point={card.click_point} '
              f'bbox=({card.bbox.x1},{card.bbox.y1})-({card.bbox.x2},{card.bbox.y2})')
        for avatar in card.avatars:
            pred = avatar.prediction
            if pred and pred.name:
                line = (f'  头像 slot{avatar.slot_index} 粉框={avatar.eligible} '
                        f'-> {pred.name} ({pred.student_id}) '
                        f'score={pred.score:.3f} margin={pred.margin:.3f}')
            else:
                line = f'  头像 slot{avatar.slot_index} 粉框={avatar.eligible} -> 识别失败'
            print(line)
            if args.save_crops:
                out = os.path.join(args.save_crops, f'card{card.index}_slot{avatar.slot_index}.png')
                cv2.imwrite(out, avatar.crop)

    priorities = load_priorities()
    if priorities:
        hit = StudentRecognitionService.select_priority_card(cards, priorities)
        print()
        print('配置的优先学生:', priorities)
        if hit is None:
            print('=> 不会触发指定学生（没有卡片同时满足 命中+粉框+可执行）')
        else:
            print(f'=> 会点击卡片 {hit.index}，点击坐标 {hit.click_point}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
