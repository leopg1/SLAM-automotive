import RPi.GPIO as GPIO
import time
import math
import json
import asyncio
import websockets
from threading import Thread, Lock

# Configurare GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# Configurare pini senzori ultrasonici
ULTRASONIC_PINS = [
    {"TRIG": 4, "ECHO": 17, "direction": "front"},
    {"TRIG": 22, "ECHO": 23, "direction": "right"},
    {"TRIG": 24, "ECHO": 25, "direction": "back"},
    {"TRIG": 5, "ECHO": 6, "direction": "left"}
]

# Configurare pini senzori Hall
HALL_SENSOR_1 = 27  # Senzor Hall stânga
HALL_SENSOR_2 = 8   # Senzor Hall dreapta

# Inițializare GPIO pentru senzori ultrasonici
for sensor in ULTRASONIC_PINS:
    GPIO.setup(sensor["TRIG"], GPIO.OUT)
    GPIO.setup(sensor["ECHO"], GPIO.IN)
    GPIO.output(sensor["TRIG"], False)

# Inițializare GPIO pentru senzori Hall
GPIO.setup(HALL_SENSOR_1, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(HALL_SENSOR_2, GPIO.IN, pull_up_down=GPIO.PUD_UP)

# Variabile pentru odometrie
hall_counter_1 = 0
hall_counter_2 = 0
hall_last_state_1 = GPIO.input(HALL_SENSOR_1)
hall_last_state_2 = GPIO.input(HALL_SENSOR_2)
hall_lock = Lock()

# Funcție pentru măsurare ultrasonică
def measure_distance(trig_pin, echo_pin):
    GPIO.output(trig_pin, True)
    time.sleep(0.00001)
    GPIO.output(trig_pin, False)
    
    start_time = time.time()
    stop_time = time.time()
    
    # Așteaptă start semnal
    timeout_start = time.time()
    while GPIO.input(echo_pin) == 0:
        start_time = time.time()
        if time.time() - timeout_start > 0.1:  # timeout de 100ms
            return -1
    
    # Așteaptă stop semnal
    timeout_start = time.time()
    while GPIO.input(echo_pin) == 1:
        stop_time = time.time()
        if time.time() - timeout_start > 0.1:  # timeout de 100ms
            return -1
    
    # Calculează distanța
    time_elapsed = stop_time - start_time
    distance = (time_elapsed * 34300) / 2  # în cm
    
    # Filtrare valori aberante
    if distance < 2 or distance > 100:  # Limitează la 1 metru (dimensiunea cutiei)
        return -1
    
    return distance

# Funcție pentru citirea tuturor senzorilor ultrasonici
def read_all_ultrasonic():
    measurements = []
    for sensor in ULTRASONIC_PINS:
        distance = measure_distance(sensor["TRIG"], sensor["ECHO"])
        if distance > 0:  # Verifică dacă măsurătoarea este validă
            measurements.append({
                "direction": sensor["direction"],
                "distance": distance
            })
        time.sleep(0.01)  # Mică pauză pentru a evita interferențele
    return measurements

# Funcții pentru tratarea senzorilor Hall
def hall_sensor_1_callback(channel):
    global hall_counter_1, hall_last_state_1
    current_state = GPIO.input(channel)
    if current_state != hall_last_state_1:
        with hall_lock:
            hall_counter_1 += 1
        hall_last_state_1 = current_state

def hall_sensor_2_callback(channel):
    global hall_counter_2, hall_last_state_2
    current_state = GPIO.input(channel)
    if current_state != hall_last_state_2:
        with hall_lock:
            hall_counter_2 += 1
        hall_last_state_2 = current_state

# Înregistrare callback-uri pentru senzori Hall
GPIO.add_event_detect(HALL_SENSOR_1, GPIO.BOTH, callback=hall_sensor_1_callback)
GPIO.add_event_detect(HALL_SENSOR_2, GPIO.BOTH, callback=hall_sensor_2_callback)

# Funcție pentru citirea contorilor Hall și resetarea lor
def read_hall_sensors():
    global hall_counter_1, hall_counter_2
    with hall_lock:
        count1 = hall_counter_1
        count2 = hall_counter_2
        hall_counter_1 = 0
        hall_counter_2 = 0
    return count1, count2

# Funcție pentru colectarea tuturor datelor
def collect_data():
    ultrasonic_data = read_all_ultrasonic()
    hall_counts = read_hall_sensors()
    
    data = {
        "timestamp": time.time(),
        "ultrasonic": ultrasonic_data,
        "hall_sensors": {
            "left_wheel": hall_counts[0],
            "right_wheel": hall_counts[1]
        }
    }
    return data

# WebSocket server
async def websocket_server(websocket, path):
    try:
        print("Client conectat")
        while True:
            data = collect_data()
            await websocket.send(json.dumps(data))
            await asyncio.sleep(0.1)  # Trimite date la fiecare 100ms
    except websockets.exceptions.ConnectionClosed:
        print("Conexiune închisă")

# Pornește serverul WebSocket
def start_websocket_server():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    start_server = websockets.serve(websocket_server, "0.0.0.0", 8765)
    loop.run_until_complete(start_server)
    loop.run_forever()

# Funcție de curățare pentru oprire
def cleanup():
    print("Curățare resurse...")
    GPIO.cleanup()

# Pornire server WebSocket în thread separat
websocket_thread = Thread(target=start_websocket_server)
websocket_thread.daemon = True
websocket_thread.start()

# Înregistrează funcția de curățare
import atexit
atexit.register(cleanup)

try:
    print("Server de date pornit. Aștept conexiuni...")
    print(f"Adresa IP: Rulează 'hostname -I' ca sa aflu IP-ul")
    print("Port: 8765")
    print("WebSocket URL: ws://IP_ADDRESS:8765")
    print("Pentru a opri serverul, apăsați Ctrl+C")
    
    # Ține scriptul rulând
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("Oprire server...")
    cleanup()