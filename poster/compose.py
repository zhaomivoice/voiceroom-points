#!/usr/bin/env python3
"""
有声小馆海报生成脚本 (v1.0)
=============================

基于原图模板，重新绘制底部卡片里的二维码 + 四行引导文案。

用法:
    python3 compose.py \\
        --url https://zhaomivoice.github.io/voiceroom-points \\
        --output ./有声小馆海报.png

依赖:
    pip install pillow qrcode[pil]

模板:
    默认模板放在 poster/assets/template_poster.png (960×1706 原图底)
"""

import argparse
import math
import os
import sys
from pathlib import Path

import qrcode
from PIL import Image, ImageDraw, ImageFont

SCRIPT_DIR = Path(__file__).resolve().parent

# ================= 版式常量（像素，基于 960×1706 模板）=================

# 卡片 + QR + 文字区域（经像素扫描确定）
QR_WHITE_BOX = (118, 1322, 334, 1538)  # QR 白色圆角矩形 bbox
QR_INNER_PAD = 8                        # QR 模块内缩 padding（不覆盖圆角边缘）
TEXT_X = QR_WHITE_BOX[2] + 22           # 四行文字统一起始 x（保证左对齐）
TEXT_X_LEFT = QR_WHITE_BOX[2] + 18      # 覆盖旧文字时的左边界
TEXT_X_RIGHT = 895                      # 覆盖旧文字时的右边界

# 四行文字的垂直位置（与卡片内其他元素对齐）
# 每行 y 为顶部基线，行间距约 35px，整体上沿对齐 QR 白块上沿（1322）
LINE_Y_STARTS = [1324, 1379, 1428, 1479]
LINE_H = 44  # 每行覆盖高度（略大于字高 34px，确保完全覆盖旧文字）

# 波浪装饰线
WAVE_Y = 1536        # 波浪线中心 y
WAVE_X0 = TEXT_X + 18
WAVE_X1 = 882        # 波浪末端 x

# ================= 颜色常量（从原图精确取样）=================

CARD_INNER = (126, 96, 130)   # #7e6082 卡片内部紫色背景（用于覆盖旧文字）
QR_BG = (250, 245, 242)       # QR 内部纯白打底（略暖，贴近原图）
GOLD = (255, 215, 106)        # #ffd76a 角标金色
TEXT_COLOR = (192, 173, 179)  # #c0adb3 引导文字色（淡粉金色）

# L 形角标尺寸
BRACKET_LEN = 26
BRACKET_THK = 4

# ================= 字体 =================

# 优先使用文泉驿正黑（免费开源，中英皆稳），找不到时回退到 Noto Sans CJK
FONT_CANDIDATES = [
    ('/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc', 32),
    ('/usr/share/fonts/truetype/wqy/wqy-microhei.ttc', 32),
    ('/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc', 32),
]


def load_font(candidates):
    """按候选列表顺序加载字体，首个可用即返回 (font_path, font_object)"""
    for path, size in candidates:
        if os.path.isfile(path):
            try:
                font = ImageFont.truetype(path, size)
                return path, font
            except Exception:
                continue
    raise RuntimeError(f"未找到可用的中文字体，候选: {[p for p, _ in candidates]}")


def generate_qr(url):
    """生成指向 url 的二维码 PIL.Image（纯黑白，白底）"""
    qr = qrcode.QRCode(
        version=None,
        box_size=6,
        border=0,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
    )
    qr.add_data(url)
    qr.make(fit=True)
    return qr.make_image(fill_color='black', back_color='white').convert('RGB')


def place_qr(img, qr_im, qr_box, pad):
    """将 qr_im 居中贴入 qr_box（预留 pad 像素内缩）"""
    x1, y1, x2, y2 = qr_box
    inner = (x1 + pad, y1 + pad, x2 - pad, y2 - pad)
    fw = inner[2] - inner[0]
    fh = inner[3] - inner[1]
    scale = min(fw / max(qr_im.size), fh / max(qr_im.size))
    new_sz = int(max(qr_im.size) * scale)
    resized = qr_im.resize((new_sz, new_sz), Image.NEAREST)
    qx = inner[0] + (fw - new_sz) // 2
    qy = inner[1] + (fh - new_sz) // 2
    img.paste(resized, (qx, qy))
    return new_sz


def draw_brackets(draw, box, color):
    """在 QR 白块四角画 L 形金色角标（WeChat 风格）"""
    x1, y1, x2, y2 = box
    corners = [
        (x1 + 2, y1 + 2,  1,  1),  # 左上
        (x2 - 2, y1 + 2, -1,  1),  # 右上
        (x1 + 2, y2 - 2,  1, -1),  # 左下
        (x2 - 2, y2 - 2, -1, -1),  # 右下
    ]
    for cx, cy, sx, sy in corners:
        draw.line([(cx, cy), (cx + sx * BRACKET_LEN, cy)], fill=color, width=BRACKET_THK)
        draw.line([(cx, cy), (cx, cy + sy * BRACKET_LEN)], fill=color, width=BRACKET_THK)


def draw_wave(draw):
    """画波浪装饰线（正弦波 + 末端菱形）"""
    pts = [(WAVE_X0 + dx, WAVE_Y + math.sin(dx / 16) * 4)
           for dx in range(0, WAVE_X1 - WAVE_X0, 2)]
    draw.line(pts, fill=GOLD, width=2)
    # 末端小菱形
    diamond = [(WAVE_X1, WAVE_Y - 5), (WAVE_X1 + 5, WAVE_Y),
               (WAVE_X1, WAVE_Y + 5), (WAVE_X1 - 5, WAVE_Y)]
    draw.polygon(diamond, fill=GOLD)


def compose(template_path, url, lines, output_path, font_candidates=None):
    """主流程：读取模板 → 覆盖旧 QR+文字 → 绘制新 QR+文字 → 保存"""

    template_path = Path(template_path)
    if not template_path.is_file():
        raise FileNotFoundError(f"模板文件不存在: {template_path}")

    img = Image.open(template_path).convert('RGB')
    draw = ImageDraw.Draw(img)

    # --- 加载字体 ---
    font_candidates = font_candidates or FONT_CANDIDATES
    font_path, font = load_font(font_candidates)
    print(f"[字体] {font_path}")

    # --- 1. 覆盖旧 QR 码内部 ---
    x1, y1, x2, y2 = QR_WHITE_BOX
    draw.rectangle(
        (x1 + QR_INNER_PAD, y1 + QR_INNER_PAD, x2 - QR_INNER_PAD, y2 - QR_INNER_PAD),
        fill=QR_BG,
    )

    # --- 2. 覆盖旧四行文字（每行一个矩形，用卡片背景色）---
    for ty in LINE_Y_STARTS:
        draw.rectangle(
            (TEXT_X_LEFT - 4, ty - 6, TEXT_X_RIGHT + 4, ty + LINE_H + 4),
            fill=CARD_INNER,
        )

    # --- 3. 生成并贴入新 QR ---
    qr_im = generate_qr(url)
    new_sz = place_qr(img, qr_im, QR_WHITE_BOX, QR_INNER_PAD)
    print(f"[QR] {url}  原始 {qr_im.size} → 缩放 {new_sz}×{new_sz}")

    # --- 4. 画四角金色 L 形角标 ---
    draw_brackets(draw, QR_WHITE_BOX, GOLD)

    # --- 5. 画四行文字（统一 x 起点 → 天然左对齐）---
    for text, ty in zip(lines, LINE_Y_STARTS):
        draw.text((TEXT_X, ty), text, font=font, fill=TEXT_COLOR)
    print(f"[文字] {len(lines)} 行已绘制，统一起点 x={TEXT_X}")

    # --- 6. 画波浪装饰 ---
    draw_wave(draw)

    # --- 7. 保存 ---
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(output_path, quality=100)
    print(f"[输出] {output_path}  ({img.size[0]}×{img.size[1]})")
    return str(output_path)


def main():
    parser = argparse.ArgumentParser(
        description='有声小馆海报生成脚本：基于模板替换底部卡片的 QR + 四行引导文案',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
示例:
  # 使用默认模板、默认引导语，换一个 URL
  python3 poster/compose.py --url https://new.host.example.com/page

  # 完全自定义
  python3 poster/compose.py \\
      --url https://zhaomivoice.github.io/voiceroom-points \\
      --template ./poster/assets/template_poster.png \\
      --line "◆ 扫码进入" \\
      --line "◆ 有声小馆音浪榜" \\
      --line "◆ 长按识别二维码 · 即刻加入" \\
      --line "◆ (扫码出现继续访问请点击)" \\
      --output ./有声小馆海报.png
        ''',
    )
    parser.add_argument(
        '--url', default='https://zhaomivoice.github.io/voiceroom-points',
        help='二维码指向的 URL（默认有声小馆榜单页）',
    )
    parser.add_argument(
        '--template',
        default=str(SCRIPT_DIR / 'assets' / 'template_poster.png'),
        help='原图模板路径（默认 poster/assets/template_poster.png）',
    )
    parser.add_argument(
        '--line', action='append', dest='lines',
        help='一行引导文案，可重复传 4 次；不传则使用默认四行',
    )
    parser.add_argument(
        '--output', default=str(Path.cwd() / '有声小馆海报.png'),
        help='输出 PNG 路径（默认 ./有声小馆海报.png）',
    )
    args = parser.parse_args()

    # 默认四行引导文案
    default_lines = [
        '◆ 扫码进入',
        '◆ 有声小馆音浪榜',
        '◆ 长按识别二维码 · 即刻加入',
        '◆ (扫码出现继续访问请点击)',
    ]
    lines = args.lines or default_lines

    try:
        compose(args.template, args.url, lines, args.output)
    except Exception as e:
        print(f"[错误] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
