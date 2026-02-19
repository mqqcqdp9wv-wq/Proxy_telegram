import os
import requests
import socket
import time
from urllib.parse import quote
from urllib.parse import urlparse, parse_qs

# Configuration
PROXY_LIST_URL = "https://raw.githubusercontent.com/Argh94/Proxy-List/main/MTProto.txt"
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
CHECK_TIMEOUT = 2  # Seconds to wait for a connection
MAX_PROXIES_TO_CHECK = 200 # Check more proxies to find the absolute fastest
MAX_PROXIES_TO_SEND = 5   # Send top 5

def get_proxies():
    """Fetch raw proxy list from GitHub."""
    print(f"Fetching proxies from {PROXY_LIST_URL}...")
    try:
        response = requests.get(PROXY_LIST_URL)
        response.raise_for_status()
        proxies = response.text.strip().split('\n')
        print(f"Got {len(proxies)} proxies.")
        return proxies
    except Exception as e:
        print(f"Error fetching proxies: {e}")
        return []

def parse_tg_link(link):
    """Extract server, port, secret from tg:// link."""
    try:
        # Link format: tg://proxy?server=...&port=...&secret=...
        if not link.startswith("tg://"):
            return None
            
        parsed = urlparse(link)
        params = parse_qs(parsed.query)
        
        server = params.get('server', [None])[0]
        port = params.get('port', [None])[0]
        secret = params.get('secret', [None])[0]
        
        if server and port and secret:
            return server, int(port), secret
        return None
    except Exception:
        return None

def check_proxy(proxy_str):
    """
    Check if a proxy is alive.
    Input: tg://proxy link
    """
    parsed = parse_tg_link(proxy_str)
    if not parsed:
        return False, 0
    
    host, port, _ = parsed
    
    try:
        start_time = time.time()
        with socket.create_connection((host, port), timeout=CHECK_TIMEOUT):
            latency = (time.time() - start_time) * 1000
            return True, latency
    except Exception:
        return False, 0

def format_telegram_link(proxy_str):
    """Return the raw tg:// link since it is already formatted."""
    return proxy_str

def send_telegram_message(message):
    """Send message to the user via Telegram Bot API."""
    if not BOT_TOKEN or not CHAT_ID:
        print("Error: BOT_TOKEN or CHAT_ID not found in environment variables.")
        return

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print("Message sent successfully!")
    except Exception as e:
        print(f"Error sending message: {e}")

def main():
    if not BOT_TOKEN or not CHAT_ID:
        print("Skipping Telegram send: Secrets not set.")
        # We allow running without secrets for testing fetching/checking logic locally
    
    raw_proxies = get_proxies()
    working_proxies = [] # List of tuples: (proxy_str, latency, ip)
    seen_ips = set()

    print(f"Checking first {MAX_PROXIES_TO_CHECK} proxies for best ping...")
    
    # Check more candidates to find low latency ones
    for p in raw_proxies[:MAX_PROXIES_TO_CHECK]:
        is_working, latency = check_proxy(p)
        if is_working:
            parsed = parse_tg_link(p)
            if parsed:
                ip = parsed[0]
                if ip not in seen_ips:
                    # print(f"✅ Works: {ip} ({latency:.0f}ms)")
                    working_proxies.append((p, latency, ip))
                    seen_ips.add(ip)
        
        # We don't break early anymore, we want to check the full sample to find the FASTEST
    
    # Sort strictly by latency (fastest first)
    working_proxies.sort(key=lambda x: x[1])
    
    if not working_proxies:
        print("No working proxies found.")
        return

    # Prepare message (Final User Version)
    current_time_msk = time.strftime('%d.%m.%Y в %H:%M по МСК')
    
    message = "📱 <b>Для стабильной загрузки фото и видео в Telegram</b>\n\n"
    message += "Если настройки сбились — нужно выбрать следующую ссылку из списка.\n\n"
    message += "Настройки обновляются автоматически каждые 3 часа.\n\n"
    message += f"Последнее обновление: {current_time_msk}\n\n"
    
    # Take top 5 distinct IPs
    count = 0
    for p, latency, ip in working_proxies:
        if count >= MAX_PROXIES_TO_SEND:
            break
            
        link = format_telegram_link(p)
        if link:
            # Format: 🔗 Применить настройки #1
            message += f"🔗 <a href='{link}'>Применить настройки #{count+1}</a>\n"
            count += 1
    
    print("\nGenerated Message:")
    print(message)
    
    send_telegram_message(message)

def send_telegram_message(message):
    """Send message to the user via Telegram Bot API."""
    # Using numeric ID for stability (immune to username changes)
    CHANNEL_ID = "-1002347714881" 
    
    if not BOT_TOKEN:
        print("Error: BOT_TOKEN not found.")
        return

    # We use editMessageText because we want to update the SAME post forever
    # But if we can't find it, we fallback to sending a new one (auto-recovery)
    # The 'Eternal Post' ID is hardcoded here based on previous successful run
    ETERNAL_MESSAGE_ID = 2 

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText"
    payload = {
        "chat_id": CHANNEL_ID,
        "message_id": ETERNAL_MESSAGE_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        print(f"Eternal Post (ID {ETERNAL_MESSAGE_ID}) updated successfully!")
    except Exception as e:
        print(f"Error editing message: {e}")
        # Only if really necessary, we could uncomment this to send a new one
        # print("Attempting to SEND a new message instead...")
        # send_new_message(message, CHANNEL_ID)


if __name__ == "__main__":
    main()
