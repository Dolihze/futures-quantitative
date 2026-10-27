"""生成应用图标：深蓝圆角底 + 上涨 K 线（红涨绿跌，符合国内期货习惯）。

输出：
  src-tauri/icons/icon.ico            多尺寸 ico（窗口/任务栏/exe 图标）
  src-tauri/icons/icon.png            512x512 png
  src-tauri/icons/32x32.png, 128x128.png, 128x128@2x.png
  frontend/public/favicon.ico         网页 favicon
用法：python scripts/gen-icon.py
"""
import os
from PIL import Image, ImageDraw

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')
ICON_DIR = os.path.join(ROOT, 'src-tauri', 'icons')
PUBLIC_DIR = os.path.join(ROOT, 'frontend', 'public')

SIZE = 1024  # 超采样绘制，再缩放以获得平滑边缘
BG_TOP = (30, 58, 138)
BG_BOTTOM = (15, 23, 42)
UP = (239, 68, 68)      # 红：涨
DOWN = (34, 197, 94)    # 绿：跌
LINE = (250, 204, 21)   # 金色趋势线


def rounded_gradient_tile(size):
    grad = Image.new('RGBA', (size, size))
    px = grad.load()
    for y in range(size):
        t = y / (size - 1)
        c = tuple(int(BG_TOP[i] + (BG_BOTTOM[i] - BG_TOP[i]) * t) for i in range(3)) + (255,)
        for x in range(size):
            px[x, y] = c
    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size - 1, size - 1), radius=int(size * 0.22), fill=255)
    tile = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    tile.paste(grad, (0, 0), mask)
    return tile


def draw_icon(size=SIZE):
    img = rounded_gradient_tile(size)
    d = ImageDraw.Draw(img)

    # (开, 收, 高, 低) 数值越大位置越高，整体呈上涨趋势
    candles = [
        (0.30, 0.38, 0.42, 0.26, DOWN),
        (0.38, 0.30, 0.42, 0.26, UP),
        (0.40, 0.52, 0.56, 0.36, UP),
        (0.52, 0.46, 0.58, 0.42, DOWN),
        (0.50, 0.66, 0.70, 0.46, UP),
        (0.66, 0.80, 0.84, 0.62, UP),
    ]
    left = size * 0.16
    right = size * 0.84
    n = len(candles)
    step = (right - left) / n
    body_w = step * 0.52
    base_y = size * 0.86
    span = size * 0.78

    def y_of(v):
        return base_y - v * span

    centers = []
    for i, (o, c, h, l, color) in enumerate(candles):
        cx = left + step * (i + 0.5)
        centers.append((cx, y_of(c)))
        wick_w = max(int(size * 0.016), 2)
        d.rectangle((cx - wick_w, y_of(h), cx + wick_w, y_of(l)), fill=color)
        top, bot = sorted((y_of(o), y_of(c)))
        d.rounded_rectangle((cx - body_w / 2, top, cx + body_w / 2, max(bot, top + size * 0.02)),
                            radius=int(size * 0.012), fill=color)

    # 金色趋势线 + 箭头
    pts = [(centers[0][0], centers[0][1] + size * 0.02)] + centers[1:]
    d.line(pts, fill=LINE, width=int(size * 0.028), joint='curve')
    ax, ay = pts[-1]
    d.polygon([(ax + size * 0.075, ay - size * 0.075),
               (ax - size * 0.01, ay - size * 0.062),
               (ax + size * 0.062, ay + size * 0.01)], fill=LINE)
    return img


def main():
    os.makedirs(ICON_DIR, exist_ok=True)
    os.makedirs(PUBLIC_DIR, exist_ok=True)
    big = draw_icon()

    def resized(px):
        return big.resize((px, px), Image.LANCZOS)

    ico_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    resized(256).save(os.path.join(ICON_DIR, 'icon.ico'), format='ICO', sizes=ico_sizes)
    resized(512).save(os.path.join(ICON_DIR, 'icon.png'))
    resized(32).save(os.path.join(ICON_DIR, '32x32.png'))
    resized(128).save(os.path.join(ICON_DIR, '128x128.png'))
    resized(256).save(os.path.join(ICON_DIR, '128x128@2x.png'))
    resized(64).save(os.path.join(PUBLIC_DIR, 'favicon.ico'), format='ICO',
                     sizes=[(16, 16), (32, 32), (48, 48), (64, 64)])
    print('icons generated in', os.path.normpath(ICON_DIR))


if __name__ == '__main__':
    main()
