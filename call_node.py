import threading
import time
import requests
import OPi.GPIO as GPIO
import subprocess, os
from flask import Flask, request

# ---------------- 설정 (물리 핀 번호 BOARD 기준) ----------------
# 주의: 보드의 실제 핀 번호를 확인하세요! 
# (예: BCM 25번 위치는 보통 BOARD 22번, BCM 27번 위치는 보통 BOARD 13번)
AMP_SD_PIN = 22  

# 버튼 핀 매핑 (예시: 보드 물리 핀 번호 기준)
BUTTON_PINS = {
    "03": 11,
    "47": 12,
    "77": 15,
    "177": 16
}

PI_STOP_URL   = "http://172.30.1.36:5000/call"
PI_DRIVER_URL = "http://172.30.1.45:5000/call"

# ---------------- 상태 ----------------
active_calls = set()
last_pressed = {} # 소프트웨어 디바운스용

# ---------------- TTS 재생 ----------------
TTS_DIR = "/home/pi/bus_detection/tts"
play_lock = threading.Lock()

def play_tts(bus, kind):
    files = []
    for lang in ("ko","en"):
        path = os.path.join(TTS_DIR, f"{bus}_{kind}_{lang}.mp3")
        if os.path.isfile(path):
            files.append(path)
    if files:
        with play_lock:
            try:
                GPIO.output(AMP_SD_PIN, GPIO.HIGH)
                time.sleep(0.05)
                # mpg123 재생
                subprocess.run(["mpg123", "-q"] + files, check=False)
            finally:
                GPIO.output(AMP_SD_PIN, GPIO.LOW)

# ---------------- 버튼 동작 ----------------
def on_button_pressed(bus):
    # 소프트웨어 디바운스 (0.3초 이내 중복 클릭 방지)
    current_time = time.time()
    if current_time - last_pressed.get(bus, 0) < 0.3:
        return
    last_pressed[bus] = current_time

    if bus in active_calls:
        print(f"[BUTTON] {bus} 이미 호출 중")
        play_tts(bus, "already")
        return

    print(f"[BUTTON] {bus} 새 호출 전송")
    active_calls.add(bus)
    play_tts(bus, "select")
    
    payload = {"type": "CALL", "bus": bus, "stop": "광주대학교 정류장"}
    for url in [PI_STOP_URL, PI_DRIVER_URL]:
        try:
            requests.post(url, json=payload, timeout=0.5)
        except:
            pass

# ---------------- Flask 서버 ----------------
app = Flask(__name__)

@app.route("/release", methods=["POST"])
def release_bus():
    data = request.get_json(force=True)
    bus = data.get("bus")
    if bus and bus in active_calls:
        active_calls.remove(bus)
        print(f"[RESET] {bus} 해제 완료")
    return {"ok": True}, 200

# ---------------- 메인 실행 ----------------
if __name__ == "__main__":
    # 1. 이전 설정 강제 초기화 (unexport)
    for pin in [AMP_SD_PIN] + list(BUTTON_PINS.values()):
        try:
            with open(f"/sys/class/gpio/unexport", "w") as f:
                f.write(str(pin))
        except:
            pass

    print("[READY] Pi-Call 시작 (Orange Pi Mode)")
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=5001), daemon=True).start()

    # 2. GPIO 초기화 (BOARD 모드)
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BOARD) 

    # 3. 앰프 핀 설정
    GPIO.setup(AMP_SD_PIN, GPIO.OUT, initial=GPIO.LOW)

    # 4. 버튼 핀 설정 (소프트웨어 풀업 미사용)
    for bus, pin in BUTTON_PINS.items():
        try:
            GPIO.setup(pin, GPIO.IN) # pull_up_down 옵션 제거
            # 디바운스 옵션 없이 이벤트 등록
            GPIO.add_event_detect(pin, GPIO.FALLING, 
                                  callback=lambda ch, b=bus: on_button_pressed(b))
            print(f"[GPIO] Pin {pin} ({bus}번) 설정 완료")
        except Exception as e:
            print(f"[ERROR] Pin {pin} 설정 실패: {e}")

    try:
        while True:
            time.sleep(1)
    finally:
        GPIO.cleanup()