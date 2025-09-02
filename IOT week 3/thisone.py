
import network, time, urequests, json, dht
from machine import Pin

# ---------- USER CONFIG ----------
WIFI_SSID     = "Robotic WIFI"
WIFI_PASSWORD = "rbtWIFI@2025"

BOT_TOKEN     = "7591180638:AAF7Kol0RyDsgbh3airP0NA7dEtF0i-FlGE"
ALLOWED_CHAT_IDS = {-4936918510}  

RELAY_PIN = 2
RELAY_ACTIVE_LOW = False
POLL_TIMEOUT_S = 30
DEBUG = True

TEMP_THRESHOLD = 24        # °C threshold for alerts
HIGH_TEMP_ALERT_INTERVAL = 5000  # ms between alerts when temp >= 30
# ---------------------------------

API = "https://api.telegram.org/bot" + BOT_TOKEN
relay = Pin(RELAY_PIN, Pin.OUT)

# ---- helpers ----
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
    t = (text or "").strip().lower()
    if t in ("/on", "on"):
        relay_on();  send_message(chat_id, "Relay: ON")
    elif t in ("/off", "off"):
        relay_off(); send_message(chat_id, "Relay: OFF")
    elif t in ("/status", "status"):
        send_message(chat_id, "Relay is " + ("ON" if relay_is_on() else "OFF"))
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
    last_high_temp_alert = 0
    high_temp_mode = False


# discard old updates
    old = get_updates(timeout=1)
    if old:
        last_id = old[-1]["update_id"]

    while True:
        # --- Telegram commands ---
        updates = get_updates(offset=(last_id+1) if last_id else None)
        for u in updates:
            last_id = u["update_id"]
            msg = u.get("message", {})
            chat_id = msg.get("chat", {}).get("id")
            text = msg.get("text")
            if chat_id in ALLOWED_CHAT_IDS:
                handle_cmd(chat_id, text)

        # --- check temperature ---
        temp, hum = temp_reader()
        now = time.ticks_ms()

        if temp is not None:
            if temp >= TEMP_THRESHOLD:
                high_temp_mode = True
                if time.ticks_diff(now, last_high_temp_alert) > HIGH_TEMP_ALERT_INTERVAL:
                    for chat_id in ALLOWED_CHAT_IDS:
                        send_message(chat_id, f"⚠️ ALERT: Temp {temp}°C, Humidity {hum}%")
                    last_high_temp_alert = now
            else:
                high_temp_mode = False
try:
    main()
except Exception as e:
    print("Fatal error:", e)
    time.sleep(5)
    reset()

                
                
                