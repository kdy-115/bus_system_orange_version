# MAX7219 도트 매트릭스 (8x32) 연동 - Pi A 통합 시스템용
# 버튼으로 선택된 버스 번호를 표시하고, 도착 시 제거
# Pi A (버튼, 스피커, OCR 감지) 시스템 연동 기반

from luma.core.interface.serial import spi, noop
from luma.led_matrix.device import max7219
from luma.core.render import canvas
from luma.core.legacy.font import proportional, LCD_FONT
from luma.core.legacy import text
from PIL import Image, ImageDraw
import time
import threading

# ─────────────────────────────
# 도트매트릭스 초기화
serial = spi(port=0, device=0, gpio=noop())
device = max7219(
    serial,
    cascaded=4,
    block_orientation=90,
    rotate=0,
    reverse_order=True  # ← [4][3][2][1] 순서로 설정
)

device.contrast(16)
font = proportional(LCD_FONT)
pressed_buses = []
pressed_lock = threading.Lock()

# 텍스트 이미지를 만들기
def render_text_image(msg, font):
    width = sum([5 if c != ' ' else 2 for c in msg]) + 1
    image = Image.new("1", (width, 8))
    draw = ImageDraw.Draw(image)
    text(draw, (0, 0), msg, font=font, fill=1)
    return image

# LED 출력 루프
def display_loop():
    last_message = ""
    while True:
        with pressed_lock:
            if not pressed_buses:
                # 빈 메시지일 경우 화면 지우기
                with canvas(device) as draw:
                    draw.rectangle(device.bounding_box, outline=0, fill=0)
                time.sleep(0.5)
                last_message = ""
                continue
            message = ", ".join(pressed_buses) + "   "
    
        if message != last_message:
            print(f"[LED] 현재 표시 메시지: {message}")
            last_message = message
    
        text_img = render_text_image(message, font)
        img_width = text_img.width
    
        if img_width <= 32:
            sub_img = text_img.crop((0, 0, 32, 8))
            with canvas(device) as draw:
                for i in range(4):
                    tile = sub_img.crop((i * 8, 0, (i + 1) * 8, 8))
                    draw.bitmap((24 - i * 8, 0), tile, fill=1)
            time.sleep(1)
        else:
            for offset in range(img_width - 32 + 1):
                sub_img = text_img.crop((offset, 0, offset + 32, 8))
                with canvas(device) as draw:
                    for i in range(4):
                        tile = sub_img.crop((i * 8, 0, (i + 1) * 8, 8))
                        draw.bitmap((24 - i * 8, 0), tile, fill=1)
                time.sleep(0.15)


# 외부에서 호출될 함수 (bus_station.py 등에서 사용)
def start_led_display():
    threading.Thread(target=display_loop, daemon=True).start()
    print("[LED] 디스플레이 루프 실행 중 - OCR 및 버튼과 연동하여 표시")

def add_bus(bus):
    with pressed_lock:
        if bus not in pressed_buses:
            pressed_buses.append(bus)
            print(f"[LED] 추가된 버스: {bus} → {pressed_buses}")

def remove_bus(bus):
    with pressed_lock:
        if bus in pressed_buses:
            pressed_buses.remove(bus)
            print(f"[LED] 제거된 버스: {bus} → {pressed_buses}")
            
def is_bus_pressed(bus):
    with pressed_lock:
        return bus in pressed_buses

def rebuild_display_from_pending(pending_calls_set):
    # 예: pending_calls_set == {"77"} 면 LED에는 "77"만 남겨라
    with display_lock:
        display_buses.clear()
        display_buses.extend(sorted(pending_calls_set))
