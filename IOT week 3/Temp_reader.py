import network, time, urequests, json, dht, machine
from machine import Pin, reset

# ---------- USER CONFIG ----------
WIFI_SSID     = "Robotic WIFI"
WIFI_PASSWORD = "rbtWIFI@2025"

BOT_TOKEN     = " "
ALLOWED_CHAT_IDS = { }  

RELAY_PIN = 2
RELAY_ACTIVE_LOW = False
POLL_TIMEOUT_S = 22
DEBUG = True

temp_reader = True
tempAlert = True
ALERT_INTERVAL = 5000  # milliseconds between temp alerts
last_alert = 0
# ---------------------------------

API = "https://api.telegram.org/bot" + BOT_TOKEN
relay = Pin(RELAY_PIN, Pin.OUT)

def _urlencode(d):
    parts = []
    for k, v in d.items():
        if isinstance(v, int):
            v = str(v)
        s = str(v)
        s = s.replace("%", "%25").replace(" ", "%20").replace("\n", "%0A")
        s = s.replace("&", "%26").replace("?", "%3F").replace("=", "%3D")
        parts.append(str(k) + "=" + s)
    return "&".join(parts)

def log(*args):
    if DEBUG:
        print(*args)

# ---- relay control ----
def relay_on():  relay.value(0 if RELAY_ACTIVE_LOW else 1)
def relay_off(): relay.value(1 if RELAY_ACTIVE_LOW else 0)
def relay_is_on(): return (relay.value() == 0) if RELAY_ACTIVE_LOW else (relay.value() == 1)

# ---- DHT reader ----
def temp_reader():
    sensor = dht.DHT11(Pin(4))
    try:
        sensor.measure()
        temp = sensor.temperature()
        hum = sensor.humidity()
        print("Temperature: {:.2f}°C".format(temp))
        print("Humidity: {:.2f}%".format(hum))
        return temp, hum
    except OSError as e:
        print("Failed to read sensor:", e)
        return None, None

# ---- Wi-Fi ----
def connect_wifi():
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print("Connecting Wi-Fi...")
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        t0 = time.time()
        while not wlan.isconnected():
            if time.time() - t0 > 25:
                raise RuntimeError("Wi-Fi connect timeout")
            time.sleep(0.25)
    print("Wi-Fi OK:", wlan.ifconfig())
    return wlan

# ---- Telegram API ----
def send_message(chat_id, text):
    try:
        url = API + "/sendMessage?" + _urlencode({"chat_id": chat_id, "text": text})
        r = urequests.get(url)
        _ = r.text
        r.close()
        log("send_message OK to", chat_id)
    except Exception as e:
        print("send_message error:", e)

def get_updates(offset=None, timeout=POLL_TIMEOUT_S):
    qs = {"timeout": timeout}
    if offset is not None:
        qs["offset"] = offset
    url = API + "/getUpdates?" + _urlencode(qs)
    try:
        r = urequests.get(url)
        data = r.json()
        r.close()
        if not data.get("ok"):
            print("getUpdates not ok:", data)
            return []
        return data.get("result", [])
    except Exception as e:
        print("get_updates error:", e)
        return []

# ---- Command handler ----
def handle_cmd(chat_id, text):
    global tempAlert
    t = (text or "").strip().lower()
    if t in ("/on", "on"):
        if temp_reader == True:
            tempAlert = False;  send_message(chat_id, "TEMPERATURE ALERT STOPPED")
        else :
            temp_reader = True; send_message(chat_id, "Sensor is reading temperature...")
        
    elif t in ("/off", "off"):
        temp_reader = False; send_message(chat_id, "Sensor stopped")
    
    elif t in ("/status", "status"):
        send_message(chat_id, "Relay is " + ("ON" if temp_reader == True else "OFF"))
        
    elif t in ("/temp", "temp"):
        temp, hum = temp_reader()
        if temp is not None:
            send_message(chat_id, f"🌡 Temp: {temp}°C, 💧 Hum: {hum}%")
        else:
            send_message(chat_id, "Failed to read sensor.")
    elif t in ("/whoami", "whoami"):
        send_message(chat_id, "Your chat id is: {}".format(chat_id))
    elif t in ("/start", "/help", "help"):
        send_message(chat_id, "Commands:\n/on\n/off\n/status\n/temp\n/whoami")
    else:
        send_message(chat_id, "Unknown. Try /on, /off, /status, /temp, /whoami")

# ---- Main loop ----
def main():
    connect_wifi()
    relay_off()
    last_id = None
    last_temp_alert = 0  # to avoid spamming alerts

    old = get_updates(timeout=1)
    if old:
        last_id = old[-1]["update_id"]

    print("Bot running. Waiting for commands…")
    global ALLOWED_CHAT_IDS
    global last_alert
    global tempAlert
    global temp_reader

    while True:
        # --- check Wi-Fi ---
        try:
            if not network.WLAN(network.STA_IF).isconnected():
                connect_wifi()
        except:
            pass

        # --- process Telegram messages ---
        updates = get_updates(offset=(last_id + 1) if last_id is not None else None)
        for u in updates:
            last_id = u["update_id"]
            msg = u.get("message") or u.get("edited_message")
            if not msg:
                continue
            chat_id = msg["chat"]["id"]
            text = msg.get("text", "")
            log("From", chat_id, ":", text)

            if not ALLOWED_CHAT_IDS:
                ALLOWED_CHAT_IDS = {chat_id}
                log("Learned ALLOWED_CHAT_IDS =", ALLOWED_CHAT_IDS)
                send_message(chat_id, "Authorized. You can now control the relay.")

            if chat_id not in ALLOWED_CHAT_IDS:
                send_message(chat_id, "Not authorized.")
                continue

            handle_cmd(chat_id, text)

        # --- check temperature automatically ---
        if temp_reader == true:
            temp, hum = temp_reader()
            if temp is not None and temp >= 30 and tempAlert == True:
                now = time.ticks_ms()
                if time.ticks_diff(now, last_alert) >= ALERT_INTERVAL:
                    for chat_id in ALLOWED_CHAT_IDS:
                        send_message(chat_id, f"⚠️ Temperature HIGH: {temp}°C ")
                    last_alert = now
            elif tempAlert == False and temp < 30:
                send_message(chat_id, f"🌡 Temp is below 30°C, Relay: auto-off, Temp:{temp}°C, 💧 Hum: {hum}%")
                tempAlert = True
                    
            time.sleep(1)
       
        

try:
    main()
except Exception as e:
    print("Fatal error:", e)
    time.sleep(5)
    reset()

