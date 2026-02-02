# driver_display.py (안정 버전 + Pygame + 전체 화면 실행)

import time
import threading
import subprocess
import os
import sys
import textwrap
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from flask import Flask, request
import OPi.GPIO as GPIO 
import pygame 

# ───────────────── 설정 ─────────────────
HOST = "0.0.0.0"
PORT = 5000
TTS_DIR = "/home/pi/bus_detection/tts"
AMP_SD_PIN = 25

# ───────────────── GUI 디자인 설정 ─────────────────
BG_COLOR = (30, 30, 30)
CONTAINER_COLOR = (50, 50, 50)
TITLE_COLOR = (255, 255, 255)
TEXT_COLOR = (240, 240, 240)
CONFIRM_BTN_COLOR = (50, 150, 50) # 녹색
EXIT_BTN_COLOR = (100, 100, 100)
BTN_TEXT_COLOR = (255, 255, 255)

# 폰트 크기를 변수로 저장
FONT_SIZE_TITLE = 28
FONT_SIZE_TEXT = 22
FONT_SIZE_BUTTON = 24

# 폰트 로드
font_path = "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"
try:
    font_title = ImageFont.truetype(font_path, FONT_SIZE_TITLE)
    font_text = ImageFont.truetype(font_path, FONT_SIZE_TEXT)
    font_button = ImageFont.truetype(font_path, FONT_SIZE_BUTTON)
except IOError:
    print("[WARN] 나눔고딕 폰트 로드 실패. 기본 폰트를 사용합니다.")
    font_title = ImageFont.load_default()
    font_text = ImageFont.load_default()
    font_button = ImageFont.load_default()

# ───────────────── (수정) 버튼 위치 (480px 높이 기준) ─────────────────
CONFIRM_RECT = (50, 400, 250, 460)   # (y 370->400, y 430->460)
EXIT_RECT    = (550, 400, 750, 460)  # (y 370->400, y 430->460)
BUTTON_RADIUS = 15

# ───────────────── 전역 변수 ─────────────────
notifications = []
app = Flask(__name__)
play_lock = threading.Lock()
exit_requested = False

# ───────────────── TTS 함수 (Pygame + GPIO) ─────────────────
def play_tts(bus: str):
    # (변경 없음)
    ko_path = os.path.join(TTS_DIR, f"driver_{bus}_alert_ko.mp3")
    en_path = os.path.join(TTS_DIR, f"driver_{bus}_alert_en.mp3")

    files_to_play = []
    if os.path.isfile(ko_path):
        files_to_play.append(ko_path)
    if os.path.isfile(en_path):
        files_to_play.append(en_path)

    if files_to_play:
        with play_lock:
            try:
                GPIO.output(AMP_SD_PIN, GPIO.HIGH)
                time.sleep(0.05)
                for f in files_to_play:
                    s = pygame.mixer.Sound(f)
                    s.play()
                    while pygame.mixer.get_busy():
                        time.sleep(0.1)
            except Exception as e:
                print(f"[TTS-Pygame] 오디오 재생 중 오류: {e}")
            finally:
                GPIO.output(AMP_SD_PIN, GPIO.LOW)
    else:
        print(f"[WARN] TTS 파일 없음 for driver_{bus}")

# ───────────────── GUI 헬퍼 함수 ─────────────────
def draw_rounded_rectangle(draw, box, radius, fill):
    # (변경 없음)
    x1, y1, x2, y2 = box
    draw.rectangle([x1+radius, y1, x2-radius, y2], fill=fill)
    draw.rectangle([x1, y1+radius, x2, y2-radius], fill=fill)
    draw.pieslice([x1, y1, x1+2*radius, y1+2*radius], 180, 270, fill=fill)
    draw.pieslice([x2-2*radius, y1, x2, y1+2*radius], 270, 360, fill=fill)
    draw.pieslice([x2-2*radius, y2-2*radius, x2, y2], 0, 90, fill=fill)
    draw.pieslice([x1, y2-2*radius, x1+2*radius, y2], 90, 180, fill=fill)

def get_text_center_pos(draw, box, text, font):
    # (변경 없음)
    (left, top, right, bottom) = draw.textbbox((0,0), text, font=font) 
    tw = right - left
    th = bottom - top
    x1, y1, x2, y2 = box
    x = x1 + (x2 - x1 - tw) // 2
    y = y1 + (y2 - y1 - th) // 2 - (top) 
    return (x, y)

def on_mouse(event, x, y, flags, param):
    # (변경 없음)
    global exit_requested
    if event == cv2.EVENT_LBUTTONDOWN:
        if CONFIRM_RECT[0] <= x <= CONFIRM_RECT[2] and CONFIRM_RECT[1] <= y <= CONFIRM_RECT[3]:
            print("[GUI] '확인' 클릭. 알림 삭제.")
            notifications.clear()
        elif EXIT_RECT[0] <= x <= EXIT_RECT[2] and EXIT_RECT[1] <= y <= EXIT_RECT[3]:
            print("[GUI] '종료' 클릭.")
            exit_requested = True

# ───────────────── Flask 서버 (백그라운드 실행) ─────────────────
@app.route("/call", methods=["POST"])
def handle_call():
    # (변경 없음)
    data = request.get_json(force=True)
    bus  = data.get("bus", "")
    stop = data.get("stop", "정류장")

    if not bus:
        return {"ok": False, "error": "no bus"}, 400

    msg_ko = f"{stop}에서 도움이 필요한 승객이 {bus}번 버스를 탑승할 예정입니다."
    msg_en = f"A passenger requiring assistance will board bus {bus} at {stop}."

    notifications.append((msg_ko, time.time()))
    notifications.append((msg_en, time.time()))
    print(f"[RECEIVED] {bus}번 호출 수신")
    
    threading.Thread(target=play_tts, args=(bus,), daemon=True).start()
    return {"ok": True}, 200

def run_flask():
    print(f"[*] /call 대기 중: http://{HOST}:{PORT}/call")
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)

# ───────────────── 메인 (GUI 루프) ─────────────────
def main():
    global exit_requested
    print("[READY] Pi-Driver (GUI mode) 시작")

    try:
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(AMP_SD_PIN, GPIO.OUT, initial=GPIO.LOW)
        print(f"[GPIO] 앰프 셧다운 핀(GPIO {AMP_SD_PIN}) 초기화 완료 (LOW)")
        
        pygame.mixer.init() 
        print(f"[Pygame] 오디오 장치 초기화 성공 (시스템 기본 장치 사용)")
        
    except Exception as e:
        print(f"[ERROR] 하드웨어 초기화 실패: {e}")
        GPIO.cleanup()
        sys.exit(1)

    threading.Thread(target=run_flask, daemon=True).start()

    WINDOW = 'Pi-Driver Display'
    # ───────────────── (수정) 전체 화면 설정 ─────────────────
    cv2.namedWindow(WINDOW, cv2.WND_PROP_FULLSCREEN)
    cv2.setWindowProperty(WINDOW, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    # ─────────────────
    
    cv2.setMouseCallback(WINDOW, on_mouse)

    try:
        while True:
            # 1. (수정) 배경 생성 (높이 480px)
            frame = np.full((480, 800, 3), BG_COLOR, dtype=np.uint8)
            pil = Image.fromarray(frame)
            draw = ImageDraw.Draw(pil)

            # 2. 제목 그리기 ("탑승 예정 알림")
            title_text = "탑승 예정 알림"
            (tx, ty) = get_text_center_pos(draw, (0, 0, 800, 50), title_text, font_title)
            draw.text((tx, 15), title_text, font=font_title, fill=TITLE_COLOR)

            # 3. (수정) 알림 메시지 컨테이너 (높이 380px)
            draw_rounded_rectangle(draw, (20, 60, 780, 380), 10, fill=CONTAINER_COLOR)

            # 4. 알림 목록 그리기
            y = 75
            for text, ts in notifications:
                wrapped = textwrap.fill(text, width=55) 
                draw.multiline_text((40, y), wrapped, font=font_text, fill=TEXT_COLOR)
                
                (l, t, r, b) = draw.textbbox((40, y), wrapped, font=font_text)
                y += (b - t) + 15 
                
                # 5. (수정) 알림창 밖으로 나가지 않도록 y좌표 제한 (360px)
                if y > 360:
                    break 

            # 6. '확인'/'종료' 버튼 그리기 (480px 기준 Y 좌표 사용)
            draw_rounded_rectangle(draw, CONFIRM_RECT, BUTTON_RADIUS, fill=CONFIRM_BTN_COLOR)
            txt = '알림 지우기'
            (tx, ty) = get_text_center_pos(draw, CONFIRM_RECT, txt, font_button)
            draw.text((tx, ty), txt, font=font_button, fill=BTN_TEXT_COLOR)

            draw_rounded_rectangle(draw, EXIT_RECT, BUTTON_RADIUS, fill=EXIT_BTN_COLOR)
            txt = '프로그램 종료'
            (tx, ty) = get_text_center_pos(draw, EXIT_RECT, txt, font_button)
            draw.text((tx, ty), txt, font=font_button, fill=BTN_TEXT_COLOR)

            frame = np.array(pil)
            cv2.imshow(WINDOW, frame)
            
            if (cv2.waitKey(100) & 0xFF == 27) or exit_requested:
                print("[MAIN] 종료 요청 수신...")
                break

    finally:
        cv2.destroyAllWindows()
        GPIO.cleanup()
        print("[MAIN] Pi-Driver 종료.")
        sys.exit(0)

if __name__ == "__main__":
    main()