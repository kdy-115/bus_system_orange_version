"""
tts_pregen_assist.py

/home/pi/bus_detection/tts 폴더에
현장에서 쓸 모든 안내 음성을 미리 mp3로 생성

상황별 음성:
1) 버튼 처음 눌렀을 때 (select)
   - "수완 03번 버스를 선택하셨습니다." / "You have selected bus number zero three."
   -> 승객 안내용 (Pi-Call)

2) 이미 눌린 버스를 또 눌렀을 때 (already)
   - "수완 03번 버스는 이미 선택된 버스입니다. 현재 호출 중입니다." / "Bus number zero three is already selected and currently being called."
   -> 승객 안내용 (Pi-Call), 중복 클릭 대응

3) 버스가 정류장에 실제로 들어올 때 (arrival)
   - "수완 03번 버스가 정류장에 들어오고 있습니다. 승차를 준비해 주세요."
   - "Bus number zero three is arriving at the stop. Please prepare to board."
   -> 정류장 안내 / 카메라 감지 쪽 (예: stop_node 쪽)

4) 기사 단말(운전석 디스플레이) 알림 (driver_alert)
   - "광주대 정류장에서 도움이 필요한 승객이 수완 03번 버스를 탑승할 예정입니다."
   - "A passenger requiring assistance will board bus number zero three at Gwangju University bus stop."
   -> driver_display 단말에서 기사님에게 들려줄 음성

생성 결과 파일 예:
    03_select_ko.mp3
    03_select_en.mp3
    03_already_ko.mp3
    03_already_en.mp3
    03_arrival_ko.mp3
    03_arrival_en.mp3
    driver_03_alert_ko.mp3
    driver_03_alert_en.mp3
등등 버스별 전부 생성.
"""

import os
from gtts import gTTS

# -----------------------------------------
# 출력 경로
# -----------------------------------------
OUT_DIR = "/home/pi/bus_detection/tts"
os.makedirs(OUT_DIR, exist_ok=True)

# -----------------------------------------
# 정류장 이름 (현장에 맞게 커스터마이즈)
# -----------------------------------------
STOP_NAME_KO = "광주대 정류장"
STOP_NAME_EN = "Gwangju University bus stop"

# -----------------------------------------
# 버스 노선/번호 음성용 매핑
# route_ko: 한국어로 자연스럽게 부르는 표현
# route_en: 영어 TTS용. 숫자는 천천히 읽히도록 풀어서 적는 게 안정적
# -----------------------------------------
ROUTE_INFO = {
    "03":  ("수완 03번 버스",    "bus number zero three"),
    "47":  ("송암 47번 버스",    "bus number forty seven"),
    "77":  ("진월 77번 버스",    "bus number seventy seven"),
    "177": ("진월 177번 버스",   "bus number one seven seven"),
}

# -----------------------------------------
# 문구 템플릿 (상황별)
# -----------------------------------------

# 1) 버튼 처음 눌렀을 때 ("선택하셨습니다")
def make_select_ko(route_ko: str) -> str:
    return f"{route_ko}를 선택하셨습니다."

def make_select_en(route_en: str) -> str:
    return f"You have selected {route_en}."

# 2) 이미 눌린 버스를 또 눌렀을 때 ("이미 선택된 버스입니다")
def make_already_ko(route_ko: str) -> str:
    return f"{route_ko}는 이미 선택된 버스입니다. 현재 호출 중입니다."

def make_already_en(route_en: str) -> str:
    return f"{route_en} is already selected and currently being called."

# 3) 버스가 정류장에 실제로 들어올 때 ("승차를 준비해 주세요")
def make_arrival_ko(route_ko: str) -> str:
    return f"{route_ko}가 정류장에 들어오고 있습니다. 승차를 준비해 주세요."

def make_arrival_en(route_en: str) -> str:
    return f"{route_en} is arriving at the stop. Please prepare to board."

# 4) 기사 단말 알림 ("광주대 정류장에서 ... 탑승 예정")
def make_driver_ko(route_ko: str) -> str:
    return f"{STOP_NAME_KO}에서 도움이 필요한 승객이 {route_ko}를 탑승할 예정입니다."

def make_driver_en(route_en: str) -> str:
    return f"A passenger requiring assistance will board {route_en} at {STOP_NAME_EN}."

# -----------------------------------------
# gTTS 저장 함수
# -----------------------------------------
def save_tts(text: str, lang: str, path: str):
    print(f"[TTS] {path}")
    tts = gTTS(text=text, lang=lang, slow=False)
    tts.save(path)

# -----------------------------------------
# 메인 로직
# -----------------------------------------
if __name__ == "__main__":
    for bus_id, (route_ko, route_en) in ROUTE_INFO.items():
        # 1) 선택 안내(select)
        sel_ko = make_select_ko(route_ko)
        sel_en = make_select_en(route_en)
        save_tts(sel_ko, "ko",
                 os.path.join(OUT_DIR, f"{bus_id}_select_ko.mp3"))
        save_tts(sel_en, "en",
                 os.path.join(OUT_DIR, f"{bus_id}_select_en.mp3"))

        # 2) 이미 선택 안내(already)
        already_ko = make_already_ko(route_ko)
        already_en = make_already_en(route_en)
        save_tts(already_ko, "ko",
                 os.path.join(OUT_DIR, f"{bus_id}_already_ko.mp3"))
        save_tts(already_en, "en",
                 os.path.join(OUT_DIR, f"{bus_id}_already_en.mp3"))

        # 3) 정류장 진입 안내(arrival)
        arr_ko = make_arrival_ko(route_ko)
        arr_en = make_arrival_en(route_en)
        save_tts(arr_ko, "ko",
                 os.path.join(OUT_DIR, f"{bus_id}_arrival_ko.mp3"))
        save_tts(arr_en, "en",
                 os.path.join(OUT_DIR, f"{bus_id}_arrival_en.mp3"))

        # 4) 기사 안내(driver alert)
        drv_ko = make_driver_ko(route_ko)
        drv_en = make_driver_en(route_en)
        save_tts(drv_ko, "ko",
                 os.path.join(OUT_DIR, f"driver_{bus_id}_alert_ko.mp3"))
        save_tts(drv_en, "en",
                 os.path.join(OUT_DIR, f"driver_{bus_id}_alert_en.mp3"))

    print()
    print("모든 mp3 생성 완료")
    print(f"   경로: {OUT_DIR}")
