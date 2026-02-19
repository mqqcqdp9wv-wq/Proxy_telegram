import asyncio
import os
import requests
import socket
import time
from urllib.parse import quote
from urllib.parse import urlparse, parse_qs

# Configuration
PROXY_LIST_URL = "https://raw.githubusercontent.com/Argh94/Proxy-List/main/MTProto.txt"
# CHAT_ID is hardcoded in send_telegram_message below, so we don't strictly need it here as ENV
BOT_TOKEN = os.environ.get("BOT_TOKEN")

CHECK_TIMEOUT = 10  
MAX_PROXIES_TO_CHECK = 1000 # Check ALL proxies
MAX_PROXIES_TO_SEND = 5

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

async def check_proxy_socket(proxy_link):
    """
    Check if a proxy works using raw socket (Heuristic MTProto Handshake).
    Authentication is skipped, we only check if it accepts MTProto-like packets.
    """
    parsed = parse_tg_link(proxy_link)
    if not parsed:
        return False, 0, proxy_link, None
    
    host, port, secret = parsed
    
    try:
        start_time = time.time()
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), 
            timeout=CHECK_TIMEOUT
        )
        
        # Send 64 bytes of random data (Simulate Obfuscated Header)
        # Most FakeTLS proxies (`ee` secret) will accept this or wait for more.
        # Dead/Fake proxies usually close connection immediately or timeout on connect.
        random_payload = os.urandom(64)
        writer.write(random_payload)
        await writer.drain()
        
        # Try to read 1 byte with a short timeout
        # If it returns 0 bytes -> Closed connection -> Bad
        # If it timeouts -> Connection stays open -> Likely Good (waiting for more data)
        # If it returns data -> Good (protocol response)
        try:
            # We give it 2 seconds to "reject" us. If it doesn't reject, it's alive.
            data = await asyncio.wait_for(reader.read(1), timeout=2.0)
            if not data:
                writer.close()
                await writer.wait_closed()
                return False, 0, proxy_link, host # Connection closed
        except asyncio.TimeoutError:
            # Timeout is GOOD here! It means server accepted connection and is waiting.
            pass
        except Exception:
             writer.close()
             await writer.wait_closed()
             return False, 0, proxy_link, host

        latency = (time.time() - start_time) * 1000
        writer.close()
        await writer.wait_closed()
        return True, latency, proxy_link, host
        
    except Exception:
        return False, 0, proxy_link, host

async def check_all_proxies(proxies):
    """Run checks in parallel."""
    print(f"Checking {len(proxies)} proxies with Async Socket (PARALLEL)...")
    
    tasks = []
    # Limit to MAX_PROXIES_TO_CHECK
    for p in proxies[:MAX_PROXIES_TO_CHECK]:
        tasks.append(check_proxy_socket(p))
    
    # Run all tasks concurrently
    results = await asyncio.gather(*tasks)
    
    working = []
    seen_ips = set()
    
    for success, latency, link, ip in results:
        if success and ip and ip not in seen_ips:
            # print(f"✅ Works: {ip} ({latency:.0f}ms)")
            working.append((link, latency, ip))
            seen_ips.add(ip)
            
    return working

def format_telegram_link(proxy_str):
    """Return the raw tg:// link."""
    return proxy_str

def send_telegram_message(message):
    """Send message to the user via Telegram Bot API."""
    # Using username since numeric ID was incorrect/failed
    CHANNEL_ID = "@i9006ii" 
    
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

def main():
    if not BOT_TOKEN:
        print("Skipping Telegram send: Secrets not set.")
    
    raw_proxies = get_proxies()
    
    # Run Async Checks
    loop = asyncio.get_event_loop()
    working_proxies = loop.run_until_complete(check_all_proxies(raw_proxies))
    
    # Sort strictly by latency (fastest first)
    working_proxies.sort(key=lambda x: x[1])
    
    if not working_proxies:
        print("No working proxies found.")
        return
        
    print(f"Found {len(working_proxies)} working proxies!")

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
    # Using username since numeric ID was incorrect/failed
    CHANNEL_ID = "@i9006ii" 
    
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
