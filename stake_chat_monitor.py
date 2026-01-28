import socket
socket.setdefaulttimeout(10)
import asyncio
import json
import os
import time
from collections import deque
from datetime import datetime
import websockets
import requests

# Environment variables
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

# Stake WebSocket URL
STAKE_WS_URL = "wss://stake.com/_api/websockets"

# Monitoring settings
NORMAL_MSG_RATE = 15  # Normal messages per minute
SPIKE_THRESHOLD = 35  # Alert if messages per minute exceeds this
TIME_WINDOW = 60  # Time window in seconds to calculate rate
TARGET_USER = "777aldo"
KEYWORDS = [
    "parlay", "kazandı", "won", "gg", "wp", "congrats", 
    "tebrikler", "tebrikler abi", "tebrik", "helal", "helal olsun",
    "geldi", "tuttu", "tutmuş", "kazanmış", 
    "efsane", "süper", "müthiş", "harika",
    "rain geliyor", "rain gelir", "rain yakında", "rain var",
    "kupon tuttu", "parlay tuttu", "kupon geldi",
    "777", "aldo", "başardı", "yaptı", "kazandın"
]

# Message tracking
message_timestamps = deque(maxlen=100)
last_alert_time = 0
ALERT_COOLDOWN = 300  # Don't spam alerts - wait 5 minutes between alerts

def send_telegram_message(message):
    """Send a message to Telegram"""
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML"
        }
        response = requests.post(url, json=data, timeout=10)
        if response.status_code == 200:
            print(f"✅ Telegram message sent!")
        else:
            print(f"❌ Telegram error: {response.text}")
    except Exception as e:
        print(f"❌ Failed to send Telegram: {e}")

def calculate_message_rate():
    """Calculate messages per minute in the time window"""
    if not message_timestamps:
        return 0
    
    current_time = time.time()
    # Count messages in the last TIME_WINDOW seconds
    recent_messages = [ts for ts in message_timestamps if current_time - ts <= TIME_WINDOW]
    
    # Convert to messages per minute
    if len(recent_messages) == 0:
        return 0
    
    rate = (len(recent_messages) / TIME_WINDOW) * 60
    return rate

def check_for_alert(username, message_text):
    """Check if we should send an alert"""
    global last_alert_time
    
    current_time = time.time()
    rate = calculate_message_rate()
    
    # Check if it's a spike
    is_spike = rate > SPIKE_THRESHOLD
    
    # Check if 777aldo is mentioned
    mentions_target = TARGET_USER.lower() in username.lower() or TARGET_USER.lower() in message_text.lower()
    
    # Check if keywords are present
    has_keywords = any(keyword.lower() in message_text.lower() for keyword in KEYWORDS)
    
    # Only alert if there's a spike AND (777aldo mentioned OR relevant keywords)
    if is_spike and (mentions_target or has_keywords):
        # Check cooldown
        if current_time - last_alert_time > ALERT_COOLDOWN:
            alert_msg = f"""
🚨 <b>STAKE CHAT ALERT!</b> 🚨

📊 <b>Mesaj hızı:</b> {rate:.1f} mesaj/dakika
⚡ <b>Normal hız:</b> {NORMAL_MSG_RATE} mesaj/dakika

"""
            if mentions_target:
                alert_msg += f"👤 <b>777aldo bahsedildi!</b>\n"
            
            if has_keywords:
                found_keywords = [kw for kw in KEYWORDS if kw.lower() in message_text.lower()]
                alert_msg += f"🔑 <b>Anahtar kelimeler:</b> {', '.join(found_keywords)}\n"
            
            alert_msg += f"\n💬 <b>Son mesaj:</b> {username}: {message_text[:100]}"
            alert_msg += f"\n\n⏰ <b>Zaman:</b> {datetime.now().strftime('%H:%M:%S')}"
            alert_msg += f"\n\n💰 <b>Rain gelebilir, chat'e gir!</b>"
            
            send_telegram_message(alert_msg)
            last_alert_time = current_time
            return True
    
    return False

async def connect_and_monitor():
    """Connect to Stake WebSocket and monitor chat"""
    print("🔌 Stake.com chat'e bağlanıyor...")
    
    try:
        async with websockets.connect(
            STAKE_WS_URL,
            subprotocols=["graphql-transport-ws"],
            extra_headers={
                "Origin": "https://stake.com",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
        ) as websocket:
            
            # Step 1: Send connection_init
            await websocket.send(json.dumps({"type": "connection_init"}))
            print("📤 Connection init gönderildi")
            
            # Wait for connection_ack
            response = await websocket.recv()
            msg = json.loads(response)
            print(f"📥 Yanıt: {msg.get('type')}")
            
            if msg.get('type') == 'connection_ack':
                print("✅ WebSocket bağlantısı başarılı!")
                
                # Step 2: Subscribe to chat messages
                subscribe_payload = {
                    "id": "chat-subscription",
                    "type": "subscribe",
                    "payload": {
                        "query": """
                            subscription {
                                chatMessages {
                                    id
                                    createdAt
                                    data {
                                        __typename
                                        ... on ChatMessageDataText {
                                            message
                                        }
                                    }
                                    user {
                                        name
                                        id
                                    }
                                }
                            }
                        """,
                        "variables": {}
                    }
                }
                
                await websocket.send(json.dumps(subscribe_payload))
                print("📤 Chat subscription gönderildi")
                print("👀 Mesajlar izleniyor...\n")
                
                # Step 3: Listen for messages
                while True:
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=30)
                        data = json.loads(message)
                        
                        # Handle different message types
                        if data.get('type') == 'next':
                            payload = data.get('payload', {})
                            chat_data = payload.get('data', {}).get('chatMessages', {})
                            
                            if chat_data:
                                username = chat_data.get('user', {}).get('name', 'Unknown')
                                message_data = chat_data.get('data', {})
                                message_text = message_data.get('message', '')
                                
                                if message_text:
                                    # Track message timestamp
                                    message_timestamps.append(time.time())
                                    
                                    # Calculate current rate
                                    rate = calculate_message_rate()
                                    
                                    # Log message
                                    timestamp = datetime.now().strftime('%H:%M:%S')
                                    print(f"[{timestamp}] [{rate:.1f} msg/min] {username}: {message_text[:50]}")
                                    
                                    # Check for alert
                                    check_for_alert(username, message_text)
                        
                        elif data.get('type') == 'ping':
                            # Respond to ping with pong
                            await websocket.send(json.dumps({"type": "pong"}))
                        
                    except asyncio.TimeoutError:
                        # Send ping to keep connection alive
                        await websocket.send(json.dumps({"type": "ping"}))
                        print("💓 Ping gönderildi...")
                        
    except Exception as e:
        print(f"❌ Hata oluştu: {e}")
        print("🔄 5 saniye sonra yeniden bağlanılıyor...")
        await asyncio.sleep(5)

async def main():
    """Main loop with auto-reconnect"""
    print("=" * 60)
    print("🎰 STAKE.COM CHAT MONITOR - 777ALDO RAIN DETECTOR 🎰")
    print("=" * 60)
    print(f"📊 Normal hız eşiği: {NORMAL_MSG_RATE} mesaj/dakika")
    print(f"⚡ Uyarı eşiği: {SPIKE_THRESHOLD} mesaj/dakika")
    print(f"👤 Hedef kullanıcı: {TARGET_USER}")
    print(f"🔑 Anahtar kelimeler: {', '.join(KEYWORDS)}")
    print("=" * 60)
    print()
    
    while True:
        try:
            await connect_and_monitor()
        except KeyboardInterrupt:
            print("\n👋 Program sonlandırılıyor...")
            break
        except Exception as e:
            print(f"❌ Ana döngü hatası: {e}")
            print("🔄 10 saniye sonra yeniden başlatılıyor...")
            await asyncio.sleep(10)

if __name__ == "__main__":
    # Check if environment variables are set
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ HATA: Telegram bilgileri ayarlanmamış!")
        print("TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID environment variable'larını ayarlayın.")
        exit(1)
    
    # Run the monitor
    asyncio.run(main())
