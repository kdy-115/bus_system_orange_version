# stop_node.py  (Pi-Stop: 정류장 본체, 카메라 + 도트매트릭스)
# Pygame 속도 + GPIO 앰프 제어(노이즈 제거) + 순서 보장

import threading, time, subprocess, os
import cv2
import numpy as np
import pytesseract
import onnxruntime as ort
import requests
from flask import Flask, request
from dotmatrix_display import start_led_display, add_bus, remove_bus
import pygame
import OPi.GPIO as GPIO 

# ───────────────── 설정값 ─────────────────
TTS_DIR        = "/home/pi/bus_detection/tts"
MODEL_PATH     = "/home/pi/bus_detection/models/bus_number.onnx"
CONF_THRESHOLD = 0.30
GAMMA          = 0.8
SATURATION     = 1.3
OCR_CONFIG     = "--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789"

HOST           = "0.0.0.0"
PORT           = 5000

AMP_SD_PIN = 25  # 앰프 SD 핀에 연결한 GPIO 번호 (BCM 기준)

# ───────────────── 초기화 ─────────────────
pending_calls = set()
session    = ort.InferenceSession(MODEL_PATH, providers=["CPUExecutionProvider"])
input_name = session.get_inputs()[0].name
app = Flask(__name__)

# ───────────────── 유틸 (TTS) ─────────────────
play_lock = threading.Lock()

def play_tts(bus: str, event: str):
    ko_path = os.path.join(TTS_DIR, f"{bus}_{event}_ko.mp3")
    en_path = os.path.join(TTS_DIR, f"{bus}_{event}_en.mp3")

    with play_lock:
        try:
            # 앰프 켜기
            GPIO.output(AMP_SD_PIN, GPIO.HIGH)
            time.sleep(0.05) # 앰프가 켜질 때까지 잠시 대기

            # 1. 한국어 재생
            if os.path.isfile(ko_path):
                s_ko = pygame.mixer.Sound(ko_path)
                s_ko.play()
                # 재생이 끝날 때까지 대기
                while pygame.mixer.get_busy():
                    time.sleep(0.1)
            
            # 2. 영어 재생
            if os.path.isfile(en_path):
                s_en = pygame.mixer.Sound(en_path)
                s_en.play()
                # 재생이 끝날 때까지 대기
                while pygame.mixer.get_busy():
                    time.sleep(0.1)
                    
        except Exception as e:
            print(f"[TTS-Pygame] 오디오 재생 중 오류 발생: {e}")
        finally:
            # 재생이 끝나면 앰프 끄기
            GPIO.output(AMP_SD_PIN, GPIO.LOW)

# ───────────────── 유틸 (CV/OCR) ─────────────────
def adjust_gamma(img_rgb):
    inv = 1.0 / GAMMA
    table = np.array([((i/255.0)**inv)*255 for i in range(256)], dtype=np.uint8)
    return cv2.LUT(img_rgb, table)

def adjust_saturation(img_rgb):
    hsv = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2HSV).astype(np.float32)
    h, s, v = cv2.split(hsv)
    s = np.clip(s * SATURATION, 0, 255)
    hsv = cv2.merge([h, s, v]).astype(np.uint8)
    return cv2.cvtColor(hsv, cv2.COLOR_HSV2RGB)

def preprocess_for_ocr(roi_rgb):
    gray = cv2.cvtColor(roi_rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    _, thr = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    inv = cv2.bitwise_not(thr)
    return inv

def run_yolo_and_ocr(frame_bgr):
    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
    rgb = adjust_gamma(rgb)
    rgb = adjust_saturation(rgb)
    blob = cv2.dnn.blobFromImage(rgb, 1/255.0, (640, 640), swapRB=True, crop=False)
    outs  = session.run(None, {input_name: blob})[0].squeeze()

    if outs.size == 0:
        return ""
    best = max(outs, key=lambda x: float(x[4]))
    conf = float(best[4])
    if conf < CONF_THRESHOLD:
        return ""
    cx, cy, w, h = best[:4]
    x1 = max(0, int(cx - w/2))
    y1 = max(0, int(cy - h/2))
    x2 = min(rgb.shape[1]-1, int(cx + w/2))
    y2 = min(rgb.shape[0]-1, int(cy + h/2))
    roi = rgb[y1:y2, x1:x2]
    if roi.size == 0:
        return ""
    proc = preprocess_for_ocr(roi)
    raw  = pytesseract.image_to_string(proc, config=OCR_CONFIG).strip()
    digits_only = "".join(filter(str.isdigit, raw))
    return digits_only


# ───────────────── Flask 엔드포인트 ─────────────────
@app.route("/call", methods=["POST"])
def handle_call():
    data = request.get_json(force=True)
    bus = data.get("bus", "")
    if not bus:
        return {"ok": False, "error": "no bus"}, 400
    print(f"[CALL] bus {bus} 요청 등록")
    pending_calls.add(bus)
    add_bus(bus)
    return {"ok": True}, 200

def run_flask():
    """ Flask 서버를 스레드로 돌리기 위한 함수 """
    app.run(host=HOST, port=PORT, debug=False, use_reloader=False)


# ───────────────── 도착 처리 (순서 보장) ─────────────────
def handle_arrival_sequence(bus):
    """
    (백그라운드 스레드에서 실행됨)
    TTS 재생이 끝난 후 LED 제거 및 Pi-Call 알림을 순차적으로 실행
    """
    
    # 1) 도착 음성 (Pygame으로 즉시 시작, 끝날 때까지 대기)
    print(f"[ARRIVAL-THREAD] {bus}번 TTS 재생 시작...")
    play_tts(bus, "arrival")
    print(f"[ARRIVAL-THREAD] {bus}번 TTS 재생 완료.")

    # 2) 도트 매트릭스에서 제거
    remove_bus(bus)
    
    # 3) Pi-Call에게 "이 버스 다시 눌러도 돼"라고 알려주기
    try:
        requests.post(
            "http://172.30.1.100:5001/release",   # Pi-Call 주소/포트
            json={"bus": bus},
            timeout=1
        )
        print(f"[NOTIFY] {bus} 해제 알림을 Pi-Call로 전송 완료")
    except Exception as e:
        print(f"[WARN] Pi-Call 해제 전송 실패: {e}")


# ───────────────── 카메라 루프 ─────────────────
def camera_loop():
    # 0번 웹캠 열기
    cap = cv2.VideoCapture(0)
    # 해상도 설정 (YOLO 입력에 맞게 640x480 등 설정)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    if not cap.isOpened():
        print("[ERROR] 웹캠을 열 수 없습니다.")
        return

    try:
        while True:
            ret, frame_bgr = cap.read()
            if not ret: break

            cv2.imshow("Stop Cam", frame_bgr)
            detected_num = run_yolo_and_ocr(frame_bgr)

            if detected_num and (detected_num in pending_calls):
                print(f"[ARRIVAL] {detected_num}번 도착")
                pending_calls.discard(detected_num) 
                threading.Thread(target=handle_arrival_sequence, args=(detected_num,), daemon=True).start()

            if cv2.waitKey(1) & 0xFF == 27: break
    finally:
        cap.release()
        cv2.destroyAllWindows()
        
# ───────────────── 메인 ─────────────────
if __name__ == "__main__":
    print("[READY] Pi-Stop 시작 (정류장 본체: Flask + Camera + LED)")

    try:
        # 1. GPIO 초기화
        GPIO.setwarnings(False) # 다른 스크립트와 충돌 방지
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(AMP_SD_PIN, GPIO.OUT, initial=GPIO.LOW) # 앰프를 끈 상태(LOW)로 시작
        print(f"[GPIO] 앰프 셧다운 핀(GPIO {AMP_SD_PIN}) 초기화 완료 (LOW)")

        # 2. Pygame 믹서 초기화 (시스템 기본 장치 사용)
        pygame.mixer.init() 
        print(f"[Pygame] 오디오 장치 초기화 성공 (시스템 기본 장치 사용)")
        
    except Exception as e:
        print(f"[ERROR] 하드웨어 초기화 실패: {e}")
        GPIO.cleanup() # 실패 시 GPIO 정리
        exit() # 종료

    # 스레드 기동
    threading.Thread(target=start_led_display, daemon=True).start()
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=camera_loop, daemon=True).start()
    
    print("[MAIN] 모든 스레드 시작. 메인 스레드 대기 중...")
    
    # 메인 스레드 대기 + 종료 시 GPIO 정리
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[MAIN] 종료 중...")
    finally:
        GPIO.cleanup() # Ctrl+C 종료 시 GPIO 핀 초기화