import json
import wifi
import ssl
import gc
import time
import socketpool
import adafruit_requests
import board
import random
from person_sensor import PersonSensor, MODE_CONTINUOUS
from adafruit_ht16k33.segments import Seg7x4

wifi_ssid = "your_wifi"
wifi_pwd = "your_password"
time_zone = "est5edt" # for all possibilities: http://worldtimeapi.org/api/timezone.txt
web_time_sync_seconds = 300

fake_time = None

i2c = board.STEMMA_I2C()
display = Seg7x4(i2c)
person_sensor = PersonSensor(i2c, auto_delay=False)

# for glitch animation
random_digits = [0b10110101, 0b01011010, 0b00110111, 0b11010111, 0b00100100]

pool = socketpool.SocketPool(wifi.radio)
time_last_fetched = 0.0
(hr, mins, sec) = (0, 0, 0)
display.print("0.0.0.0")

def get_formatted_time(time_tuple, include_colon=True):
    (thr, tmin, _) = time_tuple
    shr = str(thr) if thr > 9 else f'0{str(thr)}'
    smin = str(tmin) if tmin > 9 else f'0{str(tmin)}'
    c = ":" if include_colon else ""
    return f'{shr}{c}{smin}'

# glitch animation, ending on time_tuple
def animate_to_time(time_tuple):
    display.colon = True
    formatted_time = get_formatted_time(time_tuple, include_colon=False)
    for i in range(4):
        iv = 4-i
        for r in random_digits:
            for j in range(iv):          
                display.set_digit_raw(j, r)
                time.sleep(0.01)
            for k in range(4 - iv):
                offset = 3-k
                display[offset] = formatted_time[offset]
            time.sleep(0.02)
    display[0] = formatted_time[0]

def display_time(time_tuple):
    display.print(get_formatted_time(time_tuple))
    
def seconds_to_clock_time(seconds):
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return (hours, minutes, seconds)

# estimated time right now, as (h, m, s)
def calcuate_estimated_time():
    # get h/m/s since we last fetched the time from the internet
    (hs, ms, ss) = seconds_to_clock_time(time.time() - time_last_fetched)
    add_minute = 0
    add_hour = 0

    # add that elapsed time to the last time that was fetched
    adj_seconds = ss + int(sec)
    if adj_seconds > 59:
        adj_seconds -= 60
        add_minute = 1
    adj_min = ms + int(mins) + add_minute
    if adj_min > 59:
        adj_min -= 60
        add_hour = 1
    adj_hour = (hs + int(hr) + add_hour) % 12
    if adj_hour == 0:
        adj_hour = 12
    return (adj_hour, adj_min, adj_seconds)

def random_fake_time():
    (hn, mn, sn) = calcuate_estimated_time()
    hf = random.randint(1, 12)
    while hf == hn:
        hf = random.randint(1, 12)
    mf = random.randint(0, 59)
    while mf == mn:
        mf = random.randint(0, 59)
    return (hf, mf, sn)

def await_connection(max_retries=-1):
    retries = 0
    while not wifi.radio.ipv4_address and (max_retries < 0 or retries < max_retries):
        print("Connecting to WiFi...")
        try:
            wifi.radio.connect(wifi_ssid, wifi_pwd)
            print("Connected!\n")
        except ConnectionError as e:
            print("Connection Error:", e)
        time.sleep(5)
        gc.collect()
        retries += 1

await_connection()
requests = adafruit_requests.Session(pool, ssl.create_default_context())

while True:
    # does the person detector see any faces that are looking at the camera, and is it very confident?
    face_detected = any(f.is_facing and (f.box_confidence > 0.97) for f in person_sensor.get_faces())
    if face_detected and fake_time is None:
        # fake_time = (5, 0, 0) # optional, hardcode a time - it's 5'clock somewhere!
        fake_time = random_fake_time()
    elif not face_detected and fake_time is not None:
        fake_time = None
        animate_to_time(calcuate_estimated_time())
    
    # if we haven't fetched the time from the internet in {web_time_sync_seconds}, try to refresh
    if time.time() - time_last_fetched > web_time_sync_seconds:
        try:
            response = requests.get(url=f'https://worldtimeapi.org/api/timezone/{time_zone}').json()
            (hr, mins, sec) = tuple(response["datetime"].split("T")[-1].split(".")[0].split(":"))
            print("fetched time", hr, mins, sec)
            # assume half a second of lag time
            time_last_fetched = time.time()
        except Exception as e:
            print("Connection Error:", e)
            time.sleep(5)

    time_to_show = fake_time if fake_time is not None else calcuate_estimated_time()
    display_time(time_to_show)
    # give the person sensor some time
    time.sleep(0.21)
    await_connection(5)