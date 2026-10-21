#!/usr/bin/env python3
"""
有声小馆 · 规则海报生成脚本
=================================
纯矢量（SVG → PNG）绘制，三张海报：

1. 有声小馆音浪榜（9:21 / 1080×2520，含榜单二维码）
2. 周三歌唱小比赛（9:16 / 1080×1920）
3. 周日小电台（9:16 / 1080×1920）

用法:
    python3 generate.py
    python3 generate.py --only 1          # 只生成第一张
    python3 generate.py --out ./output

依赖:
    pip install cairosvg qrcode[pil] pillow

艺术字体:
    海报主标题使用 ZCOOL 系列花体字体，已随仓库放在 assets/fonts/ 目录。
    脚本启动时会自动注册到 fontconfig，无需手动安装。

二维码指向:
    https://zhaomivoice.github.io/voiceroom-points/

所有坐标均为 1080 宽画布上的绝对坐标，修改文字/间距时直接改下面
对应的 build_* 函数即可。
"""

import argparse
import base64
import math
import os
import subprocess
import tempfile
from pathlib import Path

import cairosvg
import qrcode
from PIL import Image, ImageDraw, ImageFont
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.colormasks import RadialGradiantColorMask
from qrcode.image.styles.moduledrawers.pil import RoundedModuleDrawer

SCRIPT_DIR = Path(__file__).resolve().parent
ASSETS = SCRIPT_DIR / "assets"
FONTS_DIR = ASSETS / "fonts"
OUTPUT = SCRIPT_DIR / "output"
URL = "https://zhaomivoice.github.io/voiceroom-points/"
SCALE = 2  # 2 倍渲染后缩小，边缘更干净


def _register_local_fonts():
    """将 assets/fonts 下的字体注册到 fontconfig，供 CairoSVG 渲染使用。"""
    if not FONTS_DIR.is_dir():
        return
    fonts = [f for f in FONTS_DIR.iterdir() if f.suffix.lower() in (".ttf", ".otf", ".ttc")]
    if not fonts:
        return
    conf = (
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n'
        "<fontconfig>\n"
        f'  <dir>{FONTS_DIR}</dir>\n'
        "  <cachedir>/tmp/voice-room-fonts-cache</cachedir>\n"
        "</fontconfig>\n"
    )
    conf_path = Path(tempfile.gettempdir()) / "voice-room-fonts.conf"
    conf_path.write_text(conf, encoding="utf-8")
    os.environ["FONTCONFIG_FILE"] = str(conf_path)
    subprocess.run(["fc-cache", "-f", str(FONTS_DIR)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


_register_local_fonts()

# ---------------------------------------------------------------- 配色
INK = "#1b3348"
INK2 = "#2f5169"
MUT = "#5f7d93"
SOFT = "#7d9aae"
ICE_DEEP = "#37688c"
ICE = "#7fb4d6"
ICE_LIGHT = "#cfe7f7"
LINE = "#a6c3d6"
WHITE = "#ffffff"

SERIF = "Noto Serif CJK SC"
SANS = "Noto Sans CJK SC"
MUSIC = "Noto Music"
SYMBOL = "DejaVu Sans"

# 艺术 / 花字字体（用于海报主标题）
ART_BOLD = "ZCOOL QingKe HuangYou"   # 站酷庆科黄油体 · 粗体标题
ART_FUN = "ZCOOL KuaiLe"              # 站酷快乐体 · 活泼
ART_ELEGANT = "ZCOOL XiaoWei"         # 站酷小薇体 · 优雅手写
ART_BRUSH = "Ma Shan Zheng"           # 马善政 · 毛笔楷书


# ---------------------------------------------------------------- 文本工具
def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace('"', "&quot;"))


def tw(s, size):
    """粗略估算文本宽度（CJK 按 1em，拉丁按 0.56em）"""
    w = 0.0
    for ch in s:
        if ord(ch) < 128:
            w += 0.56
        elif ch in "·、，。：；！？（）【】《》/":
            w += 0.95
        else:
            w += 1.0
    return w * size


def wrap(s, size, max_w):
    lines, cur = [], ""
    for ch in s:
        if tw(cur + ch, size) <= max_w:
            cur += ch
        else:
            lines.append(cur)
            cur = ch
    if cur:
        lines.append(cur)
    return lines


def T(x, y, s, size=26, fill=INK, weight=400, anchor="start", font=SANS,
      ls=0, op=1, stroke=None, sw=0, style=""):
    st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    stl = f' font-style="{style}"' if style else ""
    return (f'<text x="{x}" y="{y}" font-family="{font}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}" '
            f'letter-spacing="{ls}" opacity="{op}"{st}{stl}>{esc(s)}</text>')


# ---------------------------------------------------------------- 图形工具
def rect(x, y, w, h, r=0, fill=WHITE, op=1, stroke=None, sw=1, dash=None, extra=""):
    st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    ds = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{r}" ry="{r}" '
            f'fill="{fill}" fill-opacity="{op}"{st}{ds} {extra}/>')


def line(x1, y1, x2, y2, stroke=LINE, sw=1, op=1, dash=None, cap="round"):
    ds = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" '
            f'stroke-width="{sw}" stroke-opacity="{op}" stroke-linecap="{cap}"{ds}/>')


def circle(cx, cy, r, fill="none", stroke=None, sw=1, op=1, dash=None):
    st = f' stroke="{stroke}" stroke-width="{sw}"' if stroke else ""
    ds = f' stroke-dasharray="{dash}"' if dash else ""
    return (f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}" fill-opacity="{op}"'
            f'{st}{ds}/>')


def path(d, fill="none", stroke=None, sw=1, op=1, cap="round", join="round", extra=""):
    st = f' stroke="{stroke}" stroke-width="{sw}" stroke-linecap="{cap}" stroke-linejoin="{join}"' if stroke else ""
    return f'<path d="{d}" fill="{fill}" fill-opacity="{op}"{st} {extra}/>'


def diamond(cx, cy, r, fill=ICE, op=1, stroke=None, sw=1):
    d = f"M {cx} {cy-r} L {cx+r} {cy} L {cx} {cy+r} L {cx-r} {cy} Z"
    return path(d, fill=fill, stroke=stroke, sw=sw, op=op)


def sparkle(cx, cy, r, fill=WHITE, op=0.9):
    # 四角星
    d = (f"M {cx} {cy-r} C {cx+r*0.16} {cy-r*0.16} {cx+r*0.16} {cy-r*0.16} {cx+r} {cy} "
         f"C {cx+r*0.16} {cy+r*0.16} {cx+r*0.16} {cy+r*0.16} {cx} {cy+r} "
         f"C {cx-r*0.16} {cy+r*0.16} {cx-r*0.16} {cy+r*0.16} {cx-r} {cy} "
         f"C {cx-r*0.16} {cy-r*0.16} {cx-r*0.16} {cy-r*0.16} {cx} {cy-r} Z")
    return path(d, fill=fill, op=op)


def note(cx, cy, s=1.0, fill=ICE_DEEP, op=0.8, rot=0, double=False):
    g = [f'<g transform="translate({cx} {cy}) rotate({rot}) scale({s})" opacity="{op}">']
    g.append(f'<ellipse cx="0" cy="0" rx="13" ry="9" fill="{fill}" transform="rotate(-18)"/>')
    g.append(f'<rect x="10" y="-52" width="3.4" height="54" rx="1.7" fill="{fill}"/>')
    g.append(path("M 13 -52 C 30 -44 34 -30 26 -18 C 30 -36 24 -44 13 -45 Z", fill=fill))
    if double:
        g.append(f'<ellipse cx="46" cy="-14" rx="13" ry="9" fill="{fill}" transform="rotate(-18 46 -14)"/>')
        g.append(f'<rect x="56" y="-66" width="3.4" height="54" rx="1.7" fill="{fill}"/>')
        g.append(f'<rect x="10" y="-56" width="50" height="7" rx="3" fill="{fill}"/>')
    g.append('</g>')
    return "".join(g)


def wave_bars(x, y, w, h, n=26, fill=ICE, op=0.5, seed=0):
    """均衡器柱状装饰"""
    out = []
    bw = w / n * 0.55
    step = w / n
    for i in range(n):
        t = i / max(n - 1, 1)
        amp = (0.25 + 0.75 * abs(math.sin(t * math.pi * 3.3 + seed))) * h
        amp *= 0.55 + 0.45 * abs(math.sin(i * 1.7))
        bx = x + i * step
        out.append(f'<rect x="{bx:.1f}" y="{y + h - amp:.1f}" width="{bw:.1f}" '
                   f'height="{amp:.1f}" rx="{bw/2:.1f}" fill="{fill}" opacity="{op}"/>')
    return "".join(out)


def sine_line(x1, x2, y, amp=8, step=4, stroke=ICE, sw=2, op=0.6):
    pts = []
    for x in range(int(x1), int(x2), step):
        pts.append(f"{x},{y + math.sin((x - x1) / 18.0) * amp:.1f}")
    return f'<polyline points="{" ".join(pts)}" fill="none" stroke="{stroke}" stroke-width="{sw}" stroke-opacity="{op}" stroke-linecap="round"/>'


# ---------------------------------------------------------------- 图标
def icon_calendar(cx, cy, s=1, c=ICE_DEEP):
    return (f'<g transform="translate({cx} {cy}) scale({s})" fill="none" stroke="{c}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
            f'<rect x="-15" y="-14" width="30" height="28" rx="5"/>'
            f'<line x1="-15" y1="-6" x2="15" y2="-6"/>'
            f'<line x1="-7" y1="-19" x2="-7" y2="-12"/><line x1="7" y1="-19" x2="7" y2="-12"/>'
            f'<path d="M -7 3 L -2 8 L 8 -3"/></g>')


def icon_mic(cx, cy, s=1, c=ICE_DEEP):
    return (f'<g transform="translate({cx} {cy}) scale({s})" fill="none" stroke="{c}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
            f'<rect x="-8" y="-18" width="16" height="24" rx="8"/>'
            f'<path d="M -14 -2 C -14 10 14 10 14 -2"/>'
            f'<line x1="0" y1="9" x2="0" y2="16"/><line x1="-7" y1="17" x2="7" y2="17"/></g>')


def icon_radio(cx, cy, s=1, c=ICE_DEEP):
    return (f'<g transform="translate({cx} {cy}) scale({s})" fill="none" stroke="{c}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
            f'<rect x="-18" y="-11" width="36" height="26" rx="4"/>'
            f'<line x1="6" y1="-11" x2="14" y2="-22"/>'
            f'<circle cx="-9" cy="2" r="5"/><circle cx="-9" cy="2" r="1.4"/>'
            f'<line x1="3" y1="-3" x2="14" y2="-3"/><line x1="3" y1="3" x2="14" y2="3"/>'
            f'<line x1="3" y1="9" x2="10" y2="9"/></g>')


def icon_star_badge(cx, cy, s=1, c=ICE_DEEP, fill="none"):
    d = "M 0 -15 L 4.4 -4.6 L 15 -4.6 L 6.4 2 L 9.6 13 L 0 6.2 L -9.6 13 L -6.4 2 L -15 -4.6 L -4.4 -4.6 Z"
    return f'<g transform="translate({cx} {cy}) scale({s})"><path d="{d}" fill="{fill}" stroke="{c}" stroke-width="2.2" stroke-linejoin="round"/></g>'


def icon_warn(cx, cy, s=1, c=ICE_DEEP):
    return (f'<g transform="translate({cx} {cy}) scale({s})" fill="none" stroke="{c}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
            f'<path d="M 0 -17 L 17 13 L -17 13 Z"/><line x1="0" y1="-7" x2="0" y2="4"/>'
            f'<circle cx="0" cy="9" r="1.4" fill="{c}"/></g>')


def icon_shield(cx, cy, s=1, c=ICE_DEEP):
    return (f'<g transform="translate({cx} {cy}) scale({s})" fill="none" stroke="{c}" stroke-width="2.2" stroke-linejoin="round">'
            f'<path d="M 0 -16 L 14 -10 L 14 3 C 14 11 7 16 0 18 C -7 16 -14 11 -14 3 L -14 -10 Z"/>'
            f'<path d="M -6 0 L -1 5 L 7 -4"/></g>')


def icon_gift(cx, cy, s=1, c=ICE_DEEP):
    return (f'<g transform="translate({cx} {cy}) scale({s})" fill="none" stroke="{c}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
            f'<rect x="-16" y="-4" width="32" height="20" rx="3"/>'
            f'<rect x="-11" y="-13" width="22" height="9" rx="2"/>'
            f'<line x1="0" y1="-13" x2="0" y2="16"/>'
            f'<path d="M 0 -13 C -10 -22 -18 -12 -4 -11"/><path d="M 0 -13 C 10 -22 18 -12 4 -11"/></g>')


def icon_ballot(cx, cy, s=1, c=ICE_DEEP):
    return (f'<g transform="translate({cx} {cy}) scale({s})" fill="none" stroke="{c}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
            f'<rect x="-17" y="-16" width="34" height="32" rx="4"/>'
            f'<path d="M -17 -2 L -6 -2 L -3 4 L 3 4 L 6 -2 L 17 -2"/>'
            f'<path d="M -7 8 L -2 12 L 8 3"/></g>')


def icon_clock(cx, cy, s=1, c=ICE_DEEP):
    return (f'<g transform="translate({cx} {cy}) scale({s})" fill="none" stroke="{c}" stroke-width="2.2" stroke-linecap="round">'
            f'<circle cx="0" cy="0" r="15"/><path d="M 0 -8 L 0 0 L 6 4"/></g>')


def icon_headphone(cx, cy, s=1, c=ICE_DEEP):
    return (f'<g transform="translate({cx} {cy}) scale({s})" fill="none" stroke="{c}" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">'
            f'<path d="M -17 2 C -17 -12 -7 -19 0 -19 C 7 -19 17 -12 17 2"/>'
            f'<rect x="-21" y="0" width="7" height="15" rx="3.5"/>'
            f'<rect x="14" y="0" width="7" height="15" rx="3.5"/></g>')


def icon_coin(cx, cy, s=1, c=ICE_DEEP):
    return (f'<g transform="translate({cx} {cy}) scale({s})" fill="none" stroke="{c}" stroke-width="2" stroke-linecap="round">'
            f'<circle cx="0" cy="0" r="10"/><path d="M -3 -5 L 0 -8 L 3 -5 M 0 -8 L 0 7 M -4 1 L 4 1 M -3 5 L 3 5"/></g>')


# ---------------------------------------------------------------- 大装饰
def mic(cx, cy, s=1.0, rot=0, op=1.0, c1="url(#chrome)", c2="url(#chromeDeep)"):
    """银色手持麦克风"""
    g = [f'<g transform="translate({cx} {cy}) rotate({rot}) scale({s})" opacity="{op}">']
    # 光晕
    g.append(f'<ellipse cx="0" cy="-60" rx="120" ry="150" fill="url(#micGlow)" opacity="0.55"/>')
    # 头罩
    g.append(f'<rect x="-54" y="-170" width="108" height="140" rx="54" fill="{c1}" stroke="#7f9fb5" stroke-width="2"/>')
    g.append(f'<clipPath id="micClip"><rect x="-49" y="-165" width="98" height="130" rx="49"/></clipPath>')
    g.append('<g clip-path="url(#micClip)">')
    for i in range(19):
        y = -162 + i * 7
        g.append(f'<line x1="-60" y1="{y}" x2="60" y2="{y}" stroke="#6d8ea6" stroke-width="1.6" opacity="0.42"/>')
    for i in range(9):
        x = -44 + i * 11
        g.append(f'<line x1="{x}" y1="-170" x2="{x}" y2="-25" stroke="#ffffff" stroke-width="1.2" opacity="0.28"/>')
    g.append('</g>')
    # 头罩高光
    g.append(path("M -40 -152 C -24 -168 18 -168 36 -150 C 20 -158 -20 -158 -40 -152 Z", fill="#ffffff", op="0.85"))
    g.append(f'<rect x="-58" y="-36" width="116" height="24" rx="12" fill="{c2}" stroke="#7f9fb5" stroke-width="1.6"/>')
    # 手柄
    g.append(f'<path d="M -32 -14 L -26 92 Q -24 122 0 126 Q 24 122 26 92 L 32 -14 Z" fill="{c2}" stroke="#7f9fb5" stroke-width="1.8"/>')
    g.append(path("M -21 -6 L -17 90 Q -16 110 -2 116", stroke="#ffffff", sw="3", op="0.55"))
    g.append(path("M 18 -4 L 15 80", stroke="#6d8ea6", sw="2", op="0.35"))
    # 底座
    g.append(f'<ellipse cx="0" cy="126" rx="31" ry="12" fill="{c1}" stroke="#7f9fb5" stroke-width="1.6"/>')
    g.append(f'<rect x="-27" y="112" width="54" height="14" rx="7" fill="{c2}"/>')
    g.append('</g>')
    return "".join(g)


def vinyl(cx, cy, r=110, op=0.55, label="音"):
    out = [f'<g opacity="{op}">']
    out.append(circle(cx, cy, r, fill="#eaf4fa", stroke="#a9c7da", sw=1.5))
    for k in (0.94, 0.83, 0.72, 0.61, 0.5, 0.4):
        out.append(circle(cx, cy, r * k, stroke="#8fb4cb", sw=1, op=0.5))
    out.append(circle(cx, cy, r * 0.3, fill="#cfe6f5", stroke="#8fb4cb", sw=1.2))
    out.append(T(cx, cy + r * 0.11, label, size=r * 0.3, fill=ICE_DEEP, weight=700, anchor="middle", font=SERIF))
    out.append('</g>')
    return "".join(out)


def headphones(cx, cy, s=1.0, op=0.65):
    return (f'<g transform="translate({cx} {cy}) scale({s})" opacity="{op}" fill="none" stroke="#6f97b2" stroke-width="7" stroke-linecap="round" stroke-linejoin="round">'
            f'<path d="M -120 30 C -120 -55 -65 -95 0 -95 C 65 -95 120 -55 120 30"/>'
            f'<rect x="-146" y="20" width="40" height="86" rx="20" fill="#eaf5fc"/>'
            f'<rect x="106" y="20" width="40" height="86" rx="20" fill="#eaf5fc"/>'
            f'<rect x="-136" y="32" width="20" height="62" rx="10" fill="#b8d7ea" stroke="none"/>'
            f'<rect x="116" y="32" width="20" height="62" rx="10" fill="#b8d7ea" stroke="none"/></g>')


def radio(cx, cy, s=1.0, op=1.0):
    g = [f'<g transform="translate({cx} {cy}) scale({s})" opacity="{op}">']
    g.append(f'<ellipse cx="0" cy="112" rx="150" ry="20" fill="#8db2c9" opacity="0.16"/>')
    # 机身
    g.append(f'<rect x="-170" y="-90" width="340" height="196" rx="26" fill="url(#radioBody)" stroke="#8aaec4" stroke-width="2.4"/>')
    g.append(f'<rect x="-158" y="-78" width="316" height="172" rx="18" fill="none" stroke="#ffffff" stroke-width="2" opacity="0.8"/>')
    # 天线
    g.append('<line x1="118" y1="-90" x2="196" y2="-210" stroke="#6f97b2" stroke-width="4" stroke-linecap="round"/>')
    g.append('<circle cx="196" cy="-210" r="6" fill="#8fb6ce"/>')
    # 扬声器
    g.append(circle(-82, 8, 62, fill="#dfeef8", stroke="#8aaec4", sw=2))
    for k in (0.72, 0.5, 0.28):
        g.append(circle(-82, 8, 62 * k, stroke="#9dbdce", sw=1.2, op=0.8))
    g.append(circle(-82, 8, 7, fill="#7fa9c2"))
    # 面板
    g.append(rect(2, -46, 142, 62, 10, fill="#f6fbff", op=1, stroke="#a8c6d8", sw=1.5))
    g.append(T(18, -9, "FM 98.7", size=26, fill=ICE_DEEP, weight=700, font=SANS, ls=1))
    g.append(sine_line(16, 132, 20, amp=5, step=3, stroke="#8db8d2", sw=1.8, op=0.9))
    # 旋钮
    g.append(circle(22, 48, 17, fill="#eaf5fc", stroke="#8aaec4", sw=1.8))
    g.append(circle(22, 48, 4, fill="#6f97b2"))
    g.append(circle(70, 48, 12, fill="#eaf5fc", stroke="#8aaec4", sw=1.8))
    g.append(circle(108, 48, 8, fill="#8fb6ce"))
    # 提手
    g.append('<path d="M -120 -90 C -120 -126 120 -126 120 -90" fill="none" stroke="#8fb6ce" stroke-width="8" stroke-linecap="round"/>')
    g.append('</g>')
    return "".join(g)


def trophy(cx, cy, s=1.0, op=1.0):
    g = [f'<g transform="translate({cx} {cy}) scale({s})" opacity="{op}" fill="none" stroke="#5d87a3" stroke-width="2.4" stroke-linejoin="round">']
    g.append('<path d="M -42 -50 L 42 -50 L 38 -8 C 35 22 18 34 0 34 C -18 34 -35 22 -38 -8 Z" fill="url(#chrome)"/>')
    g.append('<path d="M -42 -38 C -66 -38 -70 -8 -46 2 L -40 -8 C -54 -14 -52 -26 -40 -28 Z" fill="#dcebf5"/>')
    g.append('<path d="M 42 -38 C 66 -38 70 -8 46 2 L 40 -8 C 54 -14 52 -26 40 -28 Z" fill="#dcebf5"/>')
    g.append('<path d="M 0 34 L 0 56"/><path d="M -22 58 L 22 58 L 26 70 L -26 70 Z" fill="#dcebf5"/>')
    g.append('<circle cx="0" cy="-14" r="0" />')
    g.append('</g>')
    return "".join(g)


def clef(x, y, size=120, fill=ICE, op=0.3, rot=0):
    return (f'<text x="{x}" y="{y}" font-family="{MUSIC}" font-size="{size}" fill="{fill}" '
            f'opacity="{op}" transform="rotate({rot} {x} {y})">𝄞</text>')


# ---------------------------------------------------------------- 通用版式
def background(w, h, stars=False):
    out = [f'<rect width="{w}" height="{h}" fill="url(#bg)"/>',
           f'<rect width="{w}" height="{h}" fill="url(#bgGlow1)"/>',
           f'<rect width="{w}" height="{h}" fill="url(#bgGlow2)"/>',
           f'<rect width="{w}" height="{h}" fill="url(#vignette)"/>',
           f'<rect width="{w}" height="{h}" fill="url(#dots)" opacity="0.5"/>']
    # 飘带
    out.append(path(f"M -60 260 C 220 150 300 360 560 250 C 760 168 940 210 1140 120",
                    stroke="url(#ribbon)", sw=1.6, op=0.55))
    out.append(path(f"M -60 292 C 220 182 300 392 560 282 C 760 200 940 242 1140 152",
                    stroke="url(#ribbon)", sw=1.0, op=0.35))
    out.append(path(f"M -80 {h-420} C 190 {h-520} 380 {h-300} 620 {h-400} C 840 {h-492} 980 {h-455} 1160 {h-540}",
                    stroke="url(#ribbon)", sw=1.4, op=0.4))
    # 底部均衡器
    out.append(wave_bars(40, h - 132, 1000, 88, n=54, fill="url(#barGrad)", op=0.38, seed=1.2))
    # 星点
    if stars:
        pts = [(90, 740, 6), (990, 690, 5), (120, 1150, 4), (960, 1210, 7),
               (80, 1760, 5), (1010, 1800, 4), (300, 420, 4), (820, 380, 6)]
    else:
        pts = [(90, 720, 5), (1000, 640, 4), (110, 1520, 5), (980, 1660, 4),
               (70, 2100, 4), (1008, 2150, 5), (240, 360, 4), (860, 400, 5)]
    for x, y, r in pts:
        out.append(sparkle(x, y, r, fill=WHITE, op=0.85))
    return "".join(out)


def frame(w, h):
    return "".join([
        rect(24, 24, w - 48, h - 48, 26, fill="none", stroke=WHITE, sw=2.2, op=0.95),
        rect(36, 36, w - 72, h - 72, 20, fill="none", stroke=LINE, sw=1.1, op=0.75),
        # 四角装饰
        path(f"M 60 108 L 60 60 L 108 60", stroke=ICE_DEEP, sw=2, op=0.55),
        path(f"M {w-60} 108 L {w-60} 60 L {w-108} 60", stroke=ICE_DEEP, sw=2, op=0.55),
        path(f"M 60 {h-108} L 60 {h-60} L 108 {h-60}", stroke=ICE_DEEP, sw=2, op=0.55),
        path(f"M {w-60} {h-108} L {w-60} {h-60} L {w-108} {h-60}", stroke=ICE_DEEP, sw=2, op=0.55),
        diamond(60, 60, 6, fill=ICE_DEEP, op=0.55),
        diamond(w - 60, 60, 6, fill=ICE_DEEP, op=0.55),
        diamond(60, h - 60, 6, fill=ICE_DEEP, op=0.55),
        diamond(w - 60, h - 60, 6, fill=ICE_DEEP, op=0.55),
    ])


def section(x, y, cn, en, width=980, num=None):
    out = []
    out.append(rect(x, y - 28, 5, 50, 2.5, fill="url(#accentGrad)", op=1))
    out.append(T(x + 20, y + 2, cn, size=38, fill=INK, weight=700, font=SANS, ls=1))
    out.append(T(x + 20, y + 28, en, size=16, fill=SOFT, weight=600, font=SANS, ls=4))
    if num:
        out.append(T(x + width, y + 4, num, size=34, fill=ICE, weight=700, anchor="end", font=SERIF, op=0.55))
    lx1 = x + 190
    lx2 = x + max(width - 62, 210)
    if lx2 > lx1:
        out.append(line(lx1, y - 6, lx2, y - 6, stroke="url(#lineGrad)", sw=1.4, op=0.8))
        out.append(diamond(lx1, y - 6, 4, fill=ICE_DEEP, op=0.6))
    return "".join(out)


def pill(cx, y, w, h, text, size=24, fill="url(#pillGrad)", color=ICE_DEEP, op=1, weight=600, ls=1):
    return "".join([rect(cx - w / 2, y, w, h, h / 2, fill=fill, op=op, stroke=WHITE, sw=1.4),
                    T(cx, y + h / 2 + size * 0.36, text, size=size, fill=color, weight=weight,
                      anchor="middle", font=SANS, ls=ls)])


# ---------------------------------------------------------------- 资源定义
def defs(w, h):
    return f'''
<defs>
  <linearGradient id="bg" x1="0" y1="0" x2="0.35" y2="1">
    <stop offset="0" stop-color="#fcfdff"/>
    <stop offset="0.28" stop-color="#f0f8fd"/>
    <stop offset="0.62" stop-color="#e2f0f9"/>
    <stop offset="0.86" stop-color="#d3e6f3"/>
    <stop offset="1" stop-color="#c2d9e9"/>
  </linearGradient>
  <radialGradient id="vignette" cx="0.5" cy="0.42" r="0.78">
    <stop offset="0.55" stop-color="#6f97b2" stop-opacity="0"/>
    <stop offset="1" stop-color="#5c86a3" stop-opacity="0.22"/>
  </radialGradient>
  <radialGradient id="glowW" cx="0.5" cy="0.5" r="0.5">
    <stop offset="0" stop-color="#ffffff" stop-opacity="0.95"/>
    <stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="glowB" cx="0.5" cy="0.5" r="0.5">
    <stop offset="0" stop-color="#9fd0f0" stop-opacity="0.7"/>
    <stop offset="1" stop-color="#9fd0f0" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="glowS" cx="0.5" cy="0.5" r="0.5">
    <stop offset="0" stop-color="#8fb4cc" stop-opacity="0.55"/>
    <stop offset="1" stop-color="#8fb4cc" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="bgGlow1" cx="0.16" cy="0.1" r="0.72">
    <stop offset="0" stop-color="#ffffff" stop-opacity="0.95"/>
    <stop offset="0.55" stop-color="#ffffff" stop-opacity="0.25"/>
    <stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="bgGlow2" cx="0.9" cy="0.2" r="0.62">
    <stop offset="0" stop-color="#a9d6f3" stop-opacity="0.65"/>
    <stop offset="0.6" stop-color="#bfe2f8" stop-opacity="0.2"/>
    <stop offset="1" stop-color="#bfe2f8" stop-opacity="0"/>
  </radialGradient>
  <radialGradient id="micGlow" cx="0.5" cy="0.5" r="0.5">
    <stop offset="0" stop-color="#ffffff" stop-opacity="0.9"/>
    <stop offset="0.6" stop-color="#cfe9fb" stop-opacity="0.35"/>
    <stop offset="1" stop-color="#cfe9fb" stop-opacity="0"/>
  </radialGradient>
  <linearGradient id="chrome" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#ffffff"/>
    <stop offset="0.16" stop-color="#dbe8f1"/>
    <stop offset="0.34" stop-color="#ffffff"/>
    <stop offset="0.52" stop-color="#9db9cc"/>
    <stop offset="0.68" stop-color="#eef7fd"/>
    <stop offset="0.86" stop-color="#c2d8e6"/>
    <stop offset="1" stop-color="#ffffff"/>
  </linearGradient>
  <linearGradient id="chromeDeep" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#f7fcff"/>
    <stop offset="0.2" stop-color="#c9dde9"/>
    <stop offset="0.45" stop-color="#ffffff"/>
    <stop offset="0.66" stop-color="#a7c2d4"/>
    <stop offset="1" stop-color="#e8f3fa"/>
  </linearGradient>
  <linearGradient id="radioBody" x1="0" y1="0" x2="0.4" y2="1">
    <stop offset="0" stop-color="#ffffff"/>
    <stop offset="0.45" stop-color="#e7f3fa"/>
    <stop offset="1" stop-color="#c4dcec"/>
  </linearGradient>
  <linearGradient id="titleGrad" x1="0" y1="0" x2="0.2" y2="1">
    <stop offset="0" stop-color="#122a3d"/>
    <stop offset="0.4" stop-color="#2c5470"/>
    <stop offset="0.62" stop-color="#5f839b"/>
    <stop offset="0.8" stop-color="#284f6b"/>
    <stop offset="1" stop-color="#142f44"/>
  </linearGradient>
  <linearGradient id="accentGrad" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#9cc6e2"/>
    <stop offset="1" stop-color="#3f7396"/>
  </linearGradient>
  <linearGradient id="lineGrad" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#7fa9c4" stop-opacity="0.85"/>
    <stop offset="1" stop-color="#7fa9c4" stop-opacity="0"/>
  </linearGradient>
  <linearGradient id="ribbon" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#ffffff" stop-opacity="0"/>
    <stop offset="0.4" stop-color="#8dbbd9" stop-opacity="0.9"/>
    <stop offset="0.7" stop-color="#ffffff" stop-opacity="0.6"/>
    <stop offset="1" stop-color="#8dbbd9" stop-opacity="0"/>
  </linearGradient>
  <linearGradient id="barGrad" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#9fcde9"/>
    <stop offset="1" stop-color="#5b8dad"/>
  </linearGradient>
  <linearGradient id="beam" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#ffffff" stop-opacity="0.85"/>
    <stop offset="0.55" stop-color="#d8eefc" stop-opacity="0.45"/>
    <stop offset="1" stop-color="#d8eefc" stop-opacity="0"/>
  </linearGradient>
  <linearGradient id="pillGrad" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#ffffff" stop-opacity="0.95"/>
    <stop offset="1" stop-color="#dcecf7" stop-opacity="0.95"/>
  </linearGradient>
  <linearGradient id="levelGrad" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#4a7a9b"/>
    <stop offset="1" stop-color="#22465f"/>
  </linearGradient>
  <linearGradient id="levelGrad6" x1="0" y1="0" x2="1" y2="1">
    <stop offset="0" stop-color="#6f9db8"/>
    <stop offset="0.5" stop-color="#2c5874"/>
    <stop offset="1" stop-color="#163a52"/>
  </linearGradient>
  <linearGradient id="glass" x1="0" y1="0" x2="0.2" y2="1">
    <stop offset="0" stop-color="#ffffff" stop-opacity="0.88"/>
    <stop offset="1" stop-color="#f0f8fd" stop-opacity="0.62"/>
  </linearGradient>
  <linearGradient id="glassDeep" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#ffffff" stop-opacity="0.8"/>
    <stop offset="1" stop-color="#d8eaf6" stop-opacity="0.72"/>
  </linearGradient>
  <pattern id="dots" width="28" height="28" patternUnits="userSpaceOnUse">
    <circle cx="3" cy="3" r="1.1" fill="#86abc4" opacity="0.16"/>
    <circle cx="17" cy="17" r="0.8" fill="#ffffff" opacity="0.6"/>
  </pattern>
</defs>'''


# ---------------------------------------------------------------- 海报一
def build_main():
    W, H = 1080, 2520
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{W}" height="{H}" viewBox="0 0 {W} {H}">']
    o.append(defs(W, H))
    o.append(background(W, H))

    # ===== 顶部装饰 =====
    # 五线谱弧线
    for i in range(5):
        yy = 128 + i * 15
        o.append(path(f"M 60 {yy} C 260 {yy-26} 420 {yy+24} 620 {yy-4} C 800 {yy-28} 920 {yy+8} 1022 {yy-10}",
                      stroke="#6f97b2", sw=1, op=0.12))
    o.append(vinyl(146, 232, 104, op=0.2, label="♪"))
    for r in (230, 292, 354):
        o.append(circle(930, 292, r, stroke="#8fb6cf", sw=1, op=0.24, dash="2 7"))
    o.append(mic(930, 292, 0.66, rot=8, op=0.95))
    o.append(clef(112, 352, 142, fill=ICE, op=0.3, rot=-8))
    o.append(note(792, 376, 1.0, fill=ICE_DEEP, op=0.5, rot=10))
    o.append(note(1022, 410, 0.7, fill=ICE, op=0.45, rot=-14, double=True))
    o.append(note(232, 392, 0.74, fill=ICE_DEEP, op=0.35, rot=-18, double=True))
    o.append(sparkle(768, 150, 10, fill=WHITE, op=0.95))
    o.append(sparkle(1030, 306, 7, fill=WHITE, op=0.9))
    o.append(sparkle(318, 176, 5, fill=WHITE, op=0.85))

    # 眉标
    o.append(line(300, 86, 386, 86, stroke=ICE_DEEP, sw=1.2, op=0.5))
    o.append(line(694, 86, 780, 86, stroke=ICE_DEEP, sw=1.2, op=0.5))
    o.append(diamond(390, 86, 4, fill=ICE_DEEP, op=0.6))
    o.append(diamond(690, 86, 4, fill=ICE_DEEP, op=0.6))
    o.append(T(540, 94, "着迷有声小馆 · 小馆成长体系", size=24, fill=INK2, weight=600, anchor="middle", ls=5))

    # 主标题（花字艺术字体）
    o.append(T(540, 278, "音浪榜", size=196, fill=WHITE, weight=400, anchor="middle", font=ART_BOLD, ls=14, op=0.95, stroke=WHITE, sw=10))
    o.append(T(540, 274, "音浪榜", size=196, fill="url(#titleGrad)", weight=400, anchor="middle", font=ART_BOLD, ls=14))
    o.append(T(540, 330, "VOICE WAVE  ·  LEVEL SYSTEM", size=18, fill=ICE_DEEP, weight=700, anchor="middle", ls=7, op=0.8))
    o.append(T(540, 386, "以声会友 · 用音浪记录每一次开麦", size=32, fill=INK2, weight=500, anchor="middle", ls=3, font=SERIF))

    # 三个小标签
    o.append(pill(292, 416, 160, 44, "语音打卡", size=22, color=INK2))
    o.append(pill(472, 416, 160, 44, "歌唱比赛", size=22, color=INK2))
    o.append(pill(652, 416, 160, 44, "周日电台", size=22, color=INK2))
    o.append(diamond(540, 435, 5, fill=ICE_DEEP, op=0.5))

    # 分隔装饰
    o.append(line(70, 492, 360, 492, stroke=LINE, sw=1.2, op=0.6))
    o.append(line(720, 492, 1010, 492, stroke=LINE, sw=1.2, op=0.6))
    o.append(wave_bars(430, 476, 220, 30, n=16, fill=ICE_DEEP, op=0.35))
    o.append(diamond(540, 492, 5, fill=ICE_DEEP, op=0.45))

    # 漂浮光斑与音符
    for bx, by, br in [(188, 760, 46), (1002, 890, 58), (128, 1368, 52), (968, 1806, 44), (86, 2110, 36)]:
        o.append(circle(bx, by, br, fill="url(#glowW)", op=0.55))
        o.append(circle(bx, by, br * 0.72, stroke="#ffffff", sw=1, op=0.35))
    o.append(sine_line(70, 1020, 1000, amp=7, step=6, stroke=ICE_DEEP, sw=1.2, op=0.18))
    o.append(sine_line(70, 1020, 1468, amp=5, step=6, stroke=ICE_DEEP, sw=1.1, op=0.16))
    o.append(sine_line(70, 1020, 1872, amp=5, step=6, stroke=ICE_DEEP, sw=1.1, op=0.16))
    o.append(note(612, 1010, 0.82, fill=ICE_DEEP, op=0.32, rot=-8, double=True))
    o.append(note(1032, 1002, 0.62, fill=ICE, op=0.38, rot=14))
    o.append(note(74, 1440, 0.55, fill=ICE_DEEP, op=0.28, rot=-16))
    o.append(note(966, 1478, 0.6, fill=ICE_DEEP, op=0.25, rot=12))
    o.append(note(282, 1862, 0.55, fill=ICE, op=0.3, rot=-10))
    o.append(sparkle(682, 1024, 6, fill=WHITE, op=0.9))

    # ===== 一、音浪获取 =====
    sx, sy, sw = 50, 552, 594
    o.append(section(sx, sy, "音浪获取", "HOW TO EARN", width=sw, num="01"))
    cy = sy + 42
    o.append(rect(sx, cy, sw, 360, 22, fill="url(#glass)", op=1, stroke=WHITE, sw=2))
    o.append(rect(sx + 1, cy + 1, sw - 2, 42, 21, fill=WHITE, op=0.18))
    rows = [
        (icon_calendar, "每日小馆打卡", "2音浪/条 · 每日上限3条", "+2", "音浪"),
        (icon_mic, "周三唱歌比赛", "参赛10音浪 · 投票5音浪/场", "+10", "音浪"),
        (icon_radio, "周日小电台", "挂麦5音浪/场 · 接点歌3音浪/首", "+5", "音浪"),
        (icon_star_badge, "额外加分", "协助控场 · 活跃 · 整理歌单 3音浪/场", "+3", "音浪"),
    ]
    heights = [78, 78, 78, 96]
    ry = cy + 18
    for i, (ic, title, sub, val, unit) in enumerate(rows):
        rh = heights[i]
        o.append(rect(sx + 16, ry + 4, sw - 32, rh - 10, 14, fill=WHITE, op=0.4))
        o.append(ic(sx + 54, ry + rh / 2 + 1, 1.1, c=ICE_DEEP))
        o.append(circle(sx + 54, ry + rh / 2 + 1, 28, stroke="#a9c9dc", sw=1, op=0.65))
        o.append(T(sx + 96, ry + 36, title, size=28, fill=INK, weight=700, ls=1))
        o.append(T(sx + 96, ry + 66, sub, size=22, fill=MUT, weight=400, ls=0.5))
        # 分值徽章（数值+单位统一字号，居中）
        label = f"{val}{unit}"
        o.append(rect(sx + sw - 128, ry + (rh - 40) / 2, 108, 40, 20, fill="url(#pillGrad)", op=0.95, stroke=ICE, sw=1))
        o.append(T(sx + sw - 74, ry + (rh - 40) / 2 + 29, label, size=24, fill=ICE_DEEP, weight=800, anchor="middle", font=SANS))
        ry += rh

    # ===== 二、扣分项 =====
    dx, dy, dw = 668, 552, 362
    o.append(section(dx, dy, "扣分项", "DEDUCTIONS", width=dw, num="02"))
    o.append(rect(dx, dy + 42, dw, 242, 22, fill="url(#glassDeep)", op=1, stroke=WHITE, sw=2))
    deductions = [
        ("吵架 · 嘲讽 · 刷屏", "活动期间扣10音浪/次", "-10"),
        ("报名比赛无故缺席", "每次扣5音浪", "-5"),
    ]
    ry = dy + 60
    for i, (title, sub, val) in enumerate(deductions):
        o.append(circle(dx + 46, ry + 48, 27, fill=WHITE, op=0.55, stroke=ICE, sw=1.4))
        o.append(T(dx + 46, ry + 56, val, size=24, fill=ICE_DEEP, weight=800, anchor="middle"))
        o.append(T(dx + 88, ry + 42, title, size=24, fill=INK, weight=700))
        o.append(T(dx + 88, ry + 82, sub, size=20, fill=MUT))
        if i == 0:
            o.append(line(dx + 24, ry + 104, dx + dw - 24, ry + 104, stroke=LINE, sw=1, op=0.55))
        ry += 108

    # 右侧下方装饰
    o.append(vinyl(870, 890, 74, op=0.35, label="♪"))
    o.append(note(800, 930, 0.85, fill=ICE_DEEP, op=0.35, rot=-12, double=True))
    o.append(sparkle(960, 948, 7, fill=WHITE, op=0.9))
    o.append(T(870, 996, "KEEP  THE  GROOVE", size=16, fill=SOFT, weight=600, anchor="middle", ls=4, op=0.8))

    # ===== 三、等级称号 =====
    ly = 1040
    o.append(section(50, ly, "等级称号", "LEVEL TITLES", width=980, num="03"))
    card_y = ly + 42
    o.append(rect(50, card_y, 980, 376, 22, fill="url(#glass)", op=1, stroke=WHITE, sw=2))
    levels = [
        ("Lv.1", "0", "59", "声乐萌新"),
        ("Lv.2", "60", "149", "歌唱新秀"),
        ("Lv.3", "150", "269", "实力唱将"),
        ("Lv.4", "270", "419", "金牌歌手"),
        ("Lv.5", "420", "599", "小馆歌神"),
        ("Lv.6", "600", "以上", "着迷好声音"),
    ]
    row_y = card_y + 14
    o.append(line(120, row_y + 28, 120, row_y + 6 * 58 - 28, stroke="#a9c9dc", sw=2, op=0.6))
    for i, (lv, lo, hi, name) in enumerate(levels):
        y = row_y + i * 58
        o.append(rect(62, y, 956, 50, 12, fill=WHITE, op=0.34 if i % 2 == 0 else 0.18))
        o.append(circle(120, y + 25, 6, fill=WHITE, stroke=ICE_DEEP, sw=2))
        grad = "url(#levelGrad6)" if i == 5 else "url(#levelGrad)"
        o.append(rect(84, y + 7, 72, 36, 18, fill=grad, op=1, stroke=WHITE, sw=1.2))
        o.append(T(120, y + 32, lv, size=22, fill=WHITE, weight=700, anchor="middle", font=SANS))
        # 数值区间：左值右对齐、破折号居中、右值左对齐，确保所有行破折号垂直对齐
        o.append(T(238, y + 34, lo, size=26, fill=INK2, weight=600, anchor="end", ls=0.5))
        o.append(T(244, y + 34, "–", size=26, fill=INK2, weight=600, anchor="middle", ls=0.5))
        o.append(T(250, y + 34, hi, size=26, fill=INK2, weight=600, anchor="start", ls=0.5))
        o.append(T(372, y + 35, name, size=32, fill=INK, weight=700, font=SERIF, ls=2))
        # 星级
        for k in range(6):
            o.append(diamond(846 + k * 24, y + 25, 6.2,
                             fill=ICE_DEEP if k <= i else "#ffffff",
                             op=0.92 if k <= i else 0.55,
                             stroke="#9fc2d8", sw=0.8))
        if i == 5:
            o.append(sparkle(1010, y + 25, 8, fill=WHITE, op=0.95))

    # ===== 四、等级特权 =====
    py = 1492
    o.append(section(50, py, "等级特权", "LEVEL PRIVILEGES", width=980, num="04"))
    card_y = py + 42
    o.append(rect(50, card_y, 980, 320, 22, fill="url(#glassDeep)", op=1, stroke=WHITE, sw=2))
    perks = [
        ("Lv.1", "声乐萌新", "暂无额外特权"),
        ("Lv.2", "歌唱新秀", "小馆 / 小店任务奖励加成 +5%"),
        ("Lv.3", "实力唱将", "任务奖励 +5% · 小馆活动优先排麦"),
        ("Lv.4", "金牌歌手", "任务奖励 +10% · 优先点歌及排麦"),
        ("Lv.5", "小馆歌神", "任务奖励 +20% · 优先点歌及排麦"),
        ("Lv.6", "着迷好声音", "任务奖励 +30% · 优先点歌及排麦"),
    ]
    ry = card_y + 12
    for i, (lv, name, desc) in enumerate(perks):
        y = ry + i * 50
        o.append(rect(66, y, 70, 32, 16, fill="url(#levelGrad6)" if i == 5 else "url(#levelGrad)", op=0.95))
        o.append(T(101, y + 23, lv, size=20, fill=WHITE, weight=700, anchor="middle"))
        o.append(T(158, y + 24, name, size=24, fill=INK, weight=700, ls=1))
        o.append(T(330, y + 24, desc, size=24, fill=MUT, weight=400))
        o.append(icon_shield(1004, y + 16, 0.7, c=ICE))
        if i < 5:
            o.append(line(66, y + 44, 1014, y + 44, stroke=LINE, sw=0.8, op=0.35))

    # ===== 五、积分兑换 =====
    ey = 1892
    o.append(section(50, ey, "积分兑换", "POINTS STORE", width=980, num="05"))
    card_y = ey + 42
    o.append(rect(50, card_y, 980, 246, 22, fill="url(#glass)", op=1, stroke=WHITE, sw=2))
    items = [
        ("小馆称号头衔 · 15天", "50"),
        ("小馆自由头衔 · 15天", "80"),
        ("小馆称号头衔 · 30天", "90"),
        ("小馆自由头衔 · 30天", "145"),
        ("小馆永久头衔", "688"),
        ("小馆活动冠名权", "150/次"),
        ("周三 / 周日定制主题", "80/次"),
        ("优先点歌 / 优先排麦", "5/次"),
    ]
    for i, (name, price) in enumerate(items):
        col = i % 2
        row = i // 2
        x = 66 + col * 476
        y = card_y + 12 + row * 58
        o.append(rect(x, y, 456, 48, 12, fill=WHITE, op=0.45, stroke=WHITE, sw=1))
        o.append(icon_coin(x + 28, y + 24, 0.85, c=ICE_DEEP))
        o.append(T(x + 50, y + 31, name, size=24, fill=INK2, weight=500))
        # 数值+单位统一字号，合并渲染避免遮挡
        label = price if "/" in price else f"{price}音浪"
        o.append(T(x + 444, y + 32, label, size=24, fill=ICE_DEEP, weight=800, anchor="end"))

    # ===== 底部二维码 =====
    qy = 2216
    o.append(rect(50, qy, 980, 258, 24, fill="url(#glassDeep)", op=1, stroke=WHITE, sw=2))
    o.append(rect(66, qy + 14, 232, 230, 18, fill=WHITE, op=0.95, stroke=ICE, sw=1.4))
    qr_data = base64.b64encode((ASSETS / "qr_yinlang.png").read_bytes()).decode()
    o.append(f'<image x="76" y="{qy+24}" width="212" height="212" xlink:href="data:image/png;base64,{qr_data}"/>')
    # 二维码四角
    for bx, by, sx_, sy_ in [(68, qy + 16, 1, 1), (296, qy + 16, -1, 1), (68, qy + 242, 1, -1), (296, qy + 242, -1, -1)]:
        o.append(path(f"M {bx} {by + sy_*20} L {bx} {by} L {bx + sx_*20} {by}", stroke=ICE_DEEP, sw=3, op=0.75))

    o.append(T(344, qy + 56, "SCAN  TO  ENTER", size=16, fill=SOFT, weight=700, ls=5))
    o.append(T(344, qy + 104, "扫码进入 · 音浪榜", size=36, fill=INK, weight=700, font=SERIF, ls=2))
    o.append(T(344, qy + 146, "实时查看小馆等级、音浪明细与榜单排名", size=24, fill=MUT, ls=0.5))
    o.append(T(344, qy + 222, "长按识别二维码 · 即刻加入", size=20, fill=SOFT, weight=500, ls=1))

    # 右侧装饰
    o.append(wave_bars(800, qy + 108, 190, 56, n=16, fill=ICE_DEEP, op=0.32))
    o.append(note(858, qy + 66, 1.0, fill=ICE_DEEP, op=0.4, rot=-10))
    o.append(clef(958, qy + 196, 82, fill=ICE, op=0.25))
    o.append(sparkle(1000, qy + 54, 8, fill=WHITE, op=0.95))

    o.append(frame(W, H))
    o.append('</svg>')
    return "".join(o)


# ---------------------------------------------------------------- 海报二
def build_wednesday():
    W, H = 1080, 1920
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{W}" height="{H}" viewBox="0 0 {W} {H}">']
    o.append(defs(W, H))
    o.append(background(W, H, stars=True))

    # 舞台光束
    o.append(f'<polygon points="0,40 360,40 610,560 260,560" fill="url(#beam)" opacity="0.55"/>')
    o.append(f'<polygon points="1080,40 720,40 470,560 820,560" fill="url(#beam)" opacity="0.5"/>')
    # 中央大麦克风水印
    o.append(mic(540, 300, 1.02, rot=0, op=0.18))
    for r in (250, 320, 390):
        o.append(circle(540, 250, r, stroke="#9bc1d9", sw=1, op=0.18))
    # 舞台台面
    o.append(f'<ellipse cx="540" cy="438" rx="430" ry="46" fill="#ffffff" opacity="0.22"/>')
    o.append(f'<ellipse cx="540" cy="438" rx="430" ry="46" fill="none" stroke="#8fb6cf" stroke-width="1.4" opacity="0.45"/>')
    o.append(f'<ellipse cx="540" cy="438" rx="330" ry="30" fill="none" stroke="#ffffff" stroke-width="1.2" opacity="0.6"/>')
    o.append(clef(108, 330, 132, fill=ICE, op=0.25, rot=-8))
    o.append(note(880, 420, 1.15, fill=ICE_DEEP, op=0.38, rot=8, double=True))
    o.append(note(995, 480, 0.8, fill=ICE, op=0.38, rot=-15))
    o.append(sparkle(760, 130, 9, fill=WHITE, op=0.95))
    o.append(sparkle(1008, 250, 6, fill=WHITE, op=0.9))

    # 眉标
    o.append(line(306, 88, 390, 88, stroke=ICE_DEEP, sw=1.2, op=0.5))
    o.append(line(690, 88, 774, 88, stroke=ICE_DEEP, sw=1.2, op=0.5))
    o.append(T(540, 96, "着迷有声小馆 · 音乐活动", size=24, fill=INK2, weight=600, anchor="middle", ls=5))
    o.append(diamond(394, 88, 4, fill=ICE_DEEP, op=0.6))
    o.append(diamond(686, 88, 4, fill=ICE_DEEP, op=0.6))

    # 主标题（花字艺术字体）
    o.append(T(540, 226, "周三歌唱小比赛", size=116, fill=WHITE, weight=400, anchor="middle", font=ART_FUN, ls=2, stroke=WHITE, sw=9))
    o.append(T(540, 223, "周三歌唱小比赛", size=116, fill="url(#titleGrad)", weight=400, anchor="middle", font=ART_FUN, ls=2))
    o.append(T(540, 266, "WEDNESDAY  SINGING  CONTEST", size=18, fill=ICE_DEEP, weight=700, anchor="middle", ls=6))
    o.append(pill(540, 296, 430, 54, "每周三  20:00 – 22:00", size=28, color=INK, weight=700, ls=1))
    o.append(T(540, 378, "无主题挑战  ·  馆长主题  ·  现场打分", size=24, fill=MUT, weight=500, anchor="middle", ls=2))

    # 分隔
    o.append(line(80, 408, 380, 408, stroke=LINE, sw=1.2, op=0.55))
    o.append(line(700, 408, 1000, 408, stroke=LINE, sw=1.2, op=0.55))
    o.append(wave_bars(430, 388, 220, 36, n=18, fill=ICE_DEEP, op=0.35))
    o.append(diamond(540, 408, 5, fill=ICE_DEEP, op=0.45))

    # ===== 活动流程 =====
    sy = 460
    o.append(section(50, sy, "活动流程", "SCHEDULE", width=980, num="01"))
    card_y = sy + 42
    o.append(rect(50, card_y, 980, 148, 22, fill="url(#glass)", op=1, stroke=WHITE, sw=2))
    o.append(rect(52, card_y + 2, 976, 40, 20, fill=WHITE, op=0.22))
    flow = [
        ("20:00 – 20:30", "暖场小游戏互动", "热场破冰 · 轻松开麦", icon_clock),
        ("20:30 – 22:00", "正式歌唱比赛", "登台演唱 · 现场打分", icon_mic),
    ]
    for i, (time, name, sub, ic) in enumerate(flow):
        x = 62 + i * 488
        o.append(ic(x + 46, card_y + 76, 1.25, c=ICE_DEEP))
        o.append(circle(x + 46, card_y + 76, 34, stroke="#a9c9dc", sw=1, op=0.65))
        o.append(T(x + 94, card_y + 66, time, size=28, fill=ICE_DEEP, weight=800, font=SANS, ls=1))
        o.append(T(x + 94, card_y + 104, name, size=28, fill=INK, weight=700, ls=1))
        o.append(T(x + 94, card_y + 132, sub, size=20, fill=MUT))
        if i == 0:
            o.append(line(540, card_y + 22, 540, card_y + 126, stroke=LINE, sw=1, op=0.5))

    # ===== 比赛模式 =====
    my = 710
    o.append(section(50, my, "比赛模式", "HOW IT WORKS", width=980, num="02"))
    card_y = my + 42
    o.append(rect(50, card_y, 980, 126, 22, fill="url(#glassDeep)", op=1, stroke=WHITE, sw=2))
    o.append(icon_mic(94, card_y + 62, 1.45, c=ICE_DEEP))
    o.append(circle(94, card_y + 62, 38, stroke="#a9c9dc", sw=1, op=0.65))
    o.append(T(150, card_y + 56, "无主题 或 由馆长发布主题", size=30, fill=INK, weight=700, ls=1))
    o.append(T(150, card_y + 94, "按要求唱歌，并进行现场打分", size=24, fill=MUT))
    o.append(pill(940, card_y + 48, 118, 36, "现场演唱", size=18, color=ICE_DEEP))

    # ===== 投票计分规则 =====
    vy = 930
    o.append(section(50, vy, "投票计分规则", "VOTING & SCORING", width=980, num="03"))

    # 卡 1
    c1y = vy + 42
    o.append(rect(50, c1y, 980, 166, 22, fill="url(#glass)", op=1, stroke=WHITE, sw=2))
    o.append(T(80, c1y + 112, "01", size=86, fill=ICE, weight=900, font=SERIF, op=0.28))
    o.append(icon_ballot(122, c1y + 54, 1.25, c=ICE_DEEP))
    o.append(T(176, c1y + 48, "参赛人数充足", size=30, fill=INK, weight=700, ls=1))
    o.append(pill(830, c1y + 22, 168, 34, "开启群众投票", size=18, color=ICE_DEEP))
    o.append(T(176, c1y + 86, "开启投票，发放投票积分，抢到积分才可参与投票。", size=24, fill=MUT))
    o.append(T(176, c1y + 120, "每人 3 票，不可投给自己，最终按投票结果排名。", size=24, fill=MUT))
    o.append(T(176, c1y + 150, "公平开麦 · 让每一票都被看见", size=20, fill=SOFT, ls=1))

    # 卡 2
    c2y = c1y + 184
    o.append(rect(50, c2y, 980, 138, 22, fill="url(#glassDeep)", op=1, stroke=WHITE, sw=2))
    o.append(T(80, c2y + 108, "02", size=86, fill=ICE, weight=900, font=SERIF, op=0.24))
    o.append(icon_ballot(122, c2y + 48, 1.15, c=ICE_DEEP))
    o.append(T(176, c2y + 46, "参赛人数较少", size=30, fill=INK, weight=700, ls=1))
    o.append(pill(836, c2y + 20, 156, 34, "管理员打分", size=18, color=ICE_DEEP))
    o.append(T(176, c2y + 86, "不开启群众投票，由管理员统一按演唱表现打分。", size=24, fill=MUT))
    o.append(T(176, c2y + 118, "专注演唱本身，实力就是最好的答案。", size=20, fill=SOFT, ls=1))

    # ===== 三个关键词徽章 =====
    by = 1362
    badges = [("3 票", "每人投票权", icon_ballot), ("不可自投", "保持公平", icon_shield), ("现场打分", "实力说话", icon_star_badge)]
    for i, (big, small, ic) in enumerate(badges):
        cx = 200 + i * 340
        o.append(circle(cx, by + 56, 68, fill=WHITE, op=0.5, stroke=WHITE, sw=1.6))
        o.append(circle(cx, by + 56, 58, fill="none", stroke=ICE, sw=1, op=0.65, dash="3 5"))
        o.append(ic(cx, by + 28, 1.15, c=ICE_DEEP))
        o.append(T(cx, by + 76, big, size=28, fill=INK, weight=800, anchor="middle", ls=1))
        o.append(T(cx, by + 102, small, size=18, fill=SOFT, anchor="middle", ls=1))
    o.append(T(540, 1556, "以声会友 · 唱出你的高光时刻", size=38, fill=ICE_DEEP, weight=700, anchor="middle", font=SERIF, ls=3))
    o.append(line(380, 1580, 470, 1580, stroke=ICE_DEEP, sw=1, op=0.4))
    o.append(line(610, 1580, 700, 1580, stroke=ICE_DEEP, sw=1, op=0.4))
    o.append(diamond(540, 1580, 4, fill=ICE_DEEP, op=0.5))

    # 底部
    o.append(trophy(170, 1690, 1.0, op=0.75))
    o.append(note(860, 1676, 1.0, fill=ICE_DEEP, op=0.4, rot=10, double=True))
    o.append(sparkle(960, 1628, 8, fill=WHITE, op=0.9))
    o.append(wave_bars(360, 1660, 360, 46, n=24, fill=ICE_DEEP, op=0.32))
    o.append(T(540, 1804, "着迷有声小馆  ·  ZHAOMI  VOICE", size=18, fill=SOFT, weight=600, anchor="middle", ls=4))

    o.append(frame(W, H))
    o.append('</svg>')
    return "".join(o)


# ---------------------------------------------------------------- 海报三
def build_sunday():
    W, H = 1080, 1920
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="{W}" height="{H}" viewBox="0 0 {W} {H}">']
    o.append(defs(W, H))
    o.append(background(W, H, stars=True))

    # 夜空点缀（浅色系）
    o.append(circle(872, 250, 86, fill="#f6fbff", op=0.9))
    o.append(circle(872, 250, 86, fill="none", stroke="#a9c9de", sw=1.2, op=0.6))
    o.append(circle(900, 222, 64, fill="#dfeef9", op=0.95))
    o.append(sparkle(748, 180, 8, fill=WHITE, op=0.95))
    o.append(sparkle(1012, 350, 6, fill=WHITE, op=0.9))
    o.append(sparkle(120, 500, 5, fill=WHITE, op=0.85))
    o.append(clef(116, 330, 128, fill=ICE, op=0.24, rot=-8))

    # 眉标
    o.append(line(290, 88, 374, 88, stroke=ICE_DEEP, sw=1.2, op=0.5))
    o.append(line(706, 88, 790, 88, stroke=ICE_DEEP, sw=1.2, op=0.5))
    o.append(T(540, 96, "着迷有声小馆 · 夜晚音乐电台", size=24, fill=INK2, weight=600, anchor="middle", ls=5))
    o.append(diamond(378, 88, 4, fill=ICE_DEEP, op=0.6))
    o.append(diamond(702, 88, 4, fill=ICE_DEEP, op=0.6))

    # 主标题（花字艺术字体）
    o.append(T(540, 232, "周日小电台", size=136, fill=WHITE, weight=400, anchor="middle", font=ART_ELEGANT, ls=8, stroke=WHITE, sw=9))
    o.append(T(540, 229, "周日小电台", size=136, fill="url(#titleGrad)", weight=400, anchor="middle", font=ART_ELEGANT, ls=8))
    o.append(T(540, 272, "SUNDAY  NIGHT  RADIO", size=18, fill=ICE_DEEP, weight=700, anchor="middle", ls=7))
    o.append(pill(540, 296, 430, 54, "每周日  20:00 – 22:00", size=28, color=INK, weight=700, ls=1))

    # 收音机主视觉
    o.append(headphones(540, 470, 1.35, op=0.5))
    o.append(radio(540, 502, 0.95, op=1))
    for r in (180, 235, 290):
        o.append(circle(540, 498, r, stroke="#9bc1d9", sw=1, op=0.2))
    # 声波扩散
    for rr in (196, 228, 260):
        o.append(path(f"M 740 470 A {rr} {rr} 0 0 1 740 540", stroke=ICE, sw=1.3, op=0.3))
        o.append(path(f"M 340 470 A {rr} {rr} 0 0 0 340 540", stroke=ICE, sw=1.3, op=0.3))
    # ON AIR 灯牌
    o.append(pill(435, 420, 104, 30, "ON AIR", size=13, color=ICE_DEEP, weight=700, ls=2))
    o.append(circle(395, 435, 4, fill=ICE_DEEP, op=0.8))
    o.append(note(206, 618, 1.0, fill=ICE_DEEP, op=0.42, rot=-12))
    o.append(note(856, 612, 0.9, fill=ICE_DEEP, op=0.4, rot=10, double=True))
    o.append(sparkle(742, 662, 7, fill=WHITE, op=0.95))
    o.append(sparkle(300, 404, 5, fill=WHITE, op=0.9))

    # 分隔
    o.append(line(80, 690, 380, 690, stroke=LINE, sw=1.2, op=0.55))
    o.append(line(700, 690, 1000, 690, stroke=LINE, sw=1.2, op=0.55))
    o.append(wave_bars(430, 670, 220, 36, n=18, fill=ICE_DEEP, op=0.35))
    o.append(diamond(540, 690, 5, fill=ICE_DEEP, op=0.45))

    # ===== 活动流程 =====
    sy = 754
    o.append(section(50, sy, "活动流程", "SCHEDULE", width=980, num="01"))
    card_y = sy + 42
    o.append(rect(50, card_y, 980, 128, 22, fill="url(#glass)", op=1, stroke=WHITE, sw=2))
    o.append(rect(52, card_y + 2, 976, 36, 18, fill=WHITE, op=0.22))
    flow = [
        ("20:00 – 20:30", "暖场互动", icon_headphone),
        ("20:30 – 22:00", "正式挂麦歌唱", icon_mic),
    ]
    for i, (time, name, ic) in enumerate(flow):
        x = 62 + i * 488
        o.append(ic(x + 46, card_y + 66, 1.20, c=ICE_DEEP))
        o.append(circle(x + 46, card_y + 66, 32, stroke="#a9c9dc", sw=1, op=0.65))
        o.append(T(x + 94, card_y + 56, time, size=28, fill=ICE_DEEP, weight=800, ls=1))
        o.append(T(x + 94, card_y + 94, name, size=28, fill=INK, weight=700, ls=1))
        if i == 0:
            o.append(line(540, card_y + 18, 540, card_y + 110, stroke=LINE, sw=1, op=0.5))

    # ===== 参与规则 =====
    ry = 964
    o.append(section(50, ry, "参与规则", "HOW TO JOIN", width=980, num="02"))
    rules = [
        ("挂麦奖励", "挂麦满 20 分钟，截图发到小馆", "+200 灵石", icon_headphone),
        ("排麦演唱", "每唱完一首歌，即可获得奖励", "+100 灵石", icon_mic),
        ("主题点唱", "不定期开启 · 按关键词演唱\n完成可获额外灵石", "额外灵石", icon_star_badge),
        ("群友点歌", "可消耗灵石点歌\n接歌人完成演唱即可获得对应奖励", "点歌互动", icon_gift),
    ]
    for i, (title, body, tag, ic) in enumerate(rules):
        col = i % 2
        row = i // 2
        x = 50 + col * 500
        y = ry + 42 + row * 236
        w = 480
        h = 216
        o.append(rect(x, y, w, h, 20, fill="url(#glass)" if i % 2 == 0 else "url(#glassDeep)", op=1, stroke=WHITE, sw=2))
        o.append(rect(x + 1, y + 1, w - 2, 34, 18, fill=WHITE, op=0.18))
        o.append(circle(x + 52, y + 58, 30, fill=WHITE, op=0.55, stroke=WHITE, sw=1.4))
        o.append(ic(x + 52, y + 58, 1.15, c=ICE_DEEP))
        o.append(T(x + 98, y + 54, title, size=28, fill=INK, weight=700, ls=1))
        o.append(pill(x + w - 88, y + 32, 132, 34, tag, size=18, color=ICE_DEEP, weight=700))
        lines = body.split("\n") if "\n" in body else wrap(body, 24, w - 56)
        for j, ln in enumerate(lines[:3]):
            o.append(T(x + 28, y + 112 + j * 34, ln, size=24, fill=MUT))
        o.append(wave_bars(x + 28, y + h - 58, 150, 20, n=12, fill=ICE_DEEP, op=0.28))
        o.append(line(x + 28, y + h - 20, x + w - 28, y + h - 20, stroke=LINE, sw=0.8, op=0.4))
        o.append(diamond(x + w - 32, y + h - 20, 3.5, fill=ICE_DEEP, op=0.45))

    # ===== 活动须知 =====
    ny = 1472
    o.append(rect(50, ny, 980, 96, 20, fill="url(#levelGrad)", op=1, stroke=WHITE, sw=1.6))
    o.append(icon_warn(94, ny + 48, 1.0, c=WHITE))
    o.append(T(148, ny + 42, "活动须知", size=24, fill="#dff1fc", weight=700, ls=2))
    o.append(T(148, ny + 74, "文明上麦，不得干扰活动正常进行，遵守群内秩序。", size=24, fill=WHITE, weight=500))
    o.append(sparkle(1000, ny + 26, 7, fill=WHITE, op=0.85))

    # 结尾
    o.append(T(540, 1638, "让每一首歌，都被温柔听见", size=38, fill=ICE_DEEP, weight=700, anchor="middle", font=SERIF, ls=3))
    o.append(line(350, 1662, 462, 1662, stroke=ICE_DEEP, sw=1, op=0.4))
    o.append(line(618, 1662, 730, 1662, stroke=ICE_DEEP, sw=1, op=0.4))
    o.append(diamond(540, 1662, 4, fill=ICE_DEEP, op=0.5))

    o.append(note(150, 1748, 1.0, fill=ICE_DEEP, op=0.35, rot=-10, double=True))
    o.append(headphones(880, 1760, 0.8, op=0.35))
    o.append(wave_bars(330, 1720, 420, 50, n=26, fill=ICE_DEEP, op=0.3))
    o.append(T(540, 1812, "着迷有声小馆  ·  ZHAOMI  VOICE", size=18, fill=SOFT, weight=600, anchor="middle", ls=4))

    o.append(frame(W, H))
    o.append('</svg>')
    return "".join(o)


# ---------------------------------------------------------------- 输出
def export(svg, name, w, h, out_dir):
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = out_dir / f"_{name}@2x.png"
    cairosvg.svg2png(bytestring=svg.encode("utf-8"), write_to=str(tmp),
                     output_width=w * SCALE, output_height=h * SCALE)
    img = Image.open(tmp).convert("RGB")
    img = img.resize((w, h), Image.LANCZOS)
    final = out_dir / f"{name}.png"
    img.save(final, optimize=True)
    tmp.unlink(missing_ok=True)
    print(f"[输出] {final}  {w}×{h}")
    return final


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["1", "2", "3"], help="只生成指定海报")
    ap.add_argument("--out", default=str(OUTPUT), help="输出目录")
    args = ap.parse_args()
    out_dir = Path(args.out)

    if not (ASSETS / "qr_yinlang.png").exists():
        raise SystemExit("缺少二维码资源：assets/qr_yinlang.png")

    jobs = [("1", "有声小馆音浪榜", build_main, 1080, 2520),
            ("2", "周三歌唱小比赛", build_wednesday, 1080, 1920),
            ("3", "周日小电台", build_sunday, 1080, 1920)]
    for key, name, fn, w, h in jobs:
        if args.only and args.only != key:
            continue
        export(fn(), name, w, h, out_dir)


if __name__ == "__main__":
    main()
