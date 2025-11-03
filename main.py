import telebot
import requests
import socket
import time
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

bot = telebot.TeleBot("8420676859:AAGQ6ZgnTuUs648v_79hR_CEIw6VUqRE2B4")

active_checks = {}
user_results = {}

def create_main_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    btn_start = KeyboardButton("/start")
    btn_stop = KeyboardButton("/stop")
    keyboard.add(btn_start, btn_stop)
    return keyboard

def create_check_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    btn_text = KeyboardButton("فحص نص")
    btn_url = KeyboardButton("فحص رابط")
    btn_back = KeyboardButton("/stop")
    keyboard.add(btn_text, btn_url)
    keyboard.add(btn_back)
    return keyboard

def send_google_alert(chat_id, proxy_info):
    alert_text = f"""🚨 **تنبيه Google النادر!** 🚨
📍 **IP:** `{proxy_info['ip']}:{proxy_info['port']}`
🏢 **المزود:** Google LLC
🆔 **ASN:** {proxy_info['ip_info']['asn']}
📍 **الموقع:** {proxy_info['ip_info']['city']}, {proxy_info['ip_info']['country']}"""
    bot.send_message(chat_id, alert_text, parse_mode='Markdown')

def get_detailed_ip_info(ip):
    try:
        response = requests.get(f"http://ip-api.com/json/{ip}", timeout=3)
        data = response.json()
        if data['status'] == 'success':
            risk_level = 'high' if 'google' in data.get('as', '').lower() else 'low'
            return {
                'asn': data.get('as', 'غير معروف'),
                'isp': data.get('isp', 'غير معروف'),
                'country': data.get('country', 'غير معروف'),
                'city': data.get('city', 'غير معروف'),
                'risk_level': risk_level,
                'risk_emoji': '🔴🚨' if risk_level == 'high' else '🟢✅'
            }
    except:
        pass
    return None

def check_single_proxy(proxy_ip, proxy_port, chat_id):
    try:
        proxy_dict = {
            'http': f"http://{proxy_ip}:{proxy_port}",
            'https': f"https://{proxy_ip}:{proxy_port}"
        }
        
        results = {
            'ip': proxy_ip, 'port': proxy_port,
            'http': '❌', 'https': '❌', 'connect_80': False,
            'ip_info': None, 'is_working': False
        }
        
        # فحص HTTP
        try:
            response = requests.get('http://httpbin.org/ip', proxies=proxy_dict, timeout=3)
            if response.status_code == 200:
                results['http'] = '✅'
        except: pass
        
        # فحص HTTPS
        try:
            response = requests.get('https://httpbin.org/ip', proxies=proxy_dict, timeout=3)
            if response.status_code == 200:
                results['https'] = '✅'
        except: pass
        
        # فحص CONNECT
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            results['connect_80'] = sock.connect_ex((proxy_ip, int(proxy_port))) == 0
            sock.close()
        except: pass
        
        results['ip_info'] = get_detailed_ip_info(proxy_ip)
        results['is_working'] = (results['http'] == '✅') or (results['https'] == '✅') or results['connect_80']
        
        # تنبيه Google فقط
        if (results['ip_info'] and results['is_working'] and 
            'AS396982' in results['ip_info'].get('asn', '') and 
            'Google LLC' in results['ip_info'].get('isp', '')):
            send_google_alert(chat_id, results)
        
        return results
    except:
        return None

@bot.message_handler(commands=['start'])
def start_command(message):
    bot.send_message(message.chat.id, "🎯 **بوت فحص البروكسيات**\nاختر نوع الفحص:", reply_markup=create_check_keyboard())

@bot.message_handler(commands=['stop'])
def stop_command(message):
    chat_id = message.chat.id
    active_checks[chat_id] = False
    if chat_id in user_results and user_results[chat_id]:
        show_final_results(chat_id, user_results[chat_id])
    else:
        bot.send_message(chat_id, "🛑 تم الإيقاف - لا نتائج", reply_markup=create_main_keyboard())

def show_final_results(chat_id, working_proxies):
    truly_working = [p for p in working_proxies if p.get('is_working', False)]
    if not truly_working:
        bot.send_message(chat_id, "❌ لا توجد بروكسيات شغالة")
        return
    
    results_text = f"📊 **النتائج:** {len(truly_working)} بروكسي شغال\n\n"
    for i, proxy in enumerate(truly_working[:10], 1):
        results_text += f"**{i}. {proxy['ip']}:{proxy['port']}**\n"
        if proxy['ip_info']:
            info = proxy['ip_info']
            results_text += f"   🏢 {info['isp']}\n   🆔 {info['asn']} {info['risk_emoji']}\n"
        results_text += f"   🌐 HTTP: {proxy['http']} | 🔒 HTTPS: {proxy['https']} | 🔌 CONNECT: {'✅' if proxy['connect_80'] else '❌'}\n\n"
    
    bot.send_message(chat_id, results_text, reply_markup=create_main_keyboard(), parse_mode='Markdown')
    if chat_id in user_results:
        del user_results[chat_id]

@bot.message_handler(func=lambda message: message.text == "فحص نص")
def check_text_handler(message):
    msg = bot.send_message(message.chat.id, "📝 أرسل قائمة البروكسيات:", reply_markup=create_check_keyboard())
    bot.register_next_step_handler(msg, process_text_check)

@bot.message_handler(func=lambda message: message.text == "فحص رابط")
def check_url_handler(message):
    msg = bot.send_message(message.chat.id, "🔗 أرسل رابط الملف:", reply_markup=create_check_keyboard())
    bot.register_next_step_handler(msg, process_url_check)

def process_text_check(message):
    chat_id = message.chat.id
    active_checks[chat_id] = True
    user_results[chat_id] = []
    
    proxies = []
    for line in message.text.split('\n'):
        line = line.strip()
        if ':' in line:
            parts = line.split(':')
            if len(parts) >= 2:
                ip, port = parts[0].strip(), parts[1].strip()
                port = ''.join(filter(str.isdigit, port))
                if port: proxies.append((ip, port))
    
    if not proxies:
        bot.send_message(chat_id, "❌ لا توجد بروكسيات")
        return
    
    if len(proxies) > 1000:
        proxies = proxies[:1000]
        bot.send_message(chat_id, f"⚠️ فحص أول 1000 بروكسي")
    
    progress_msg = bot.send_message(chat_id, f"🔍 فحص {len(proxies)} بروكسي...")
    working_proxies = []
    
    for i, (ip, port) in enumerate(proxies, 1):
        if not active_checks.get(chat_id, True): break
        
        if i % 10 == 0:
            try:
                bot.edit_message_text(f"🔍 {i}/{len(proxies)} - ✅ {len(working_proxies)}", chat_id, progress_msg.message_id)
            except: pass
        
        result = check_single_proxy(ip, port, chat_id)
        if result and result['is_working']:
            working_proxies.append(result)
            user_results[chat_id] = working_proxies
        
        time.sleep(0.1)
    
    if active_checks.get(chat_id, True):
        try: bot.delete_message(chat_id, progress_msg.message_id)
        except: pass
        show_final_results(chat_id, working_proxies)
        active_checks[chat_id] = False

def process_url_check(message):
    chat_id = message.chat.id
    active_checks[chat_id] = True
    user_results[chat_id] = []
    
    try:
        response = requests.get(message.text, timeout=10)
        proxies = []
        for line in response.text.split('\n'):
            if ':' in line and '.' in line:
                parts = line.split(':')
                if len(parts) >= 2:
                    ip, port = parts[0].strip(), parts[1].strip()
                    port = ''.join(filter(str.isdigit, port))
                    if port: proxies.append((ip, port))
        
        if not proxies:
            bot.send_message(chat_id, "❌ لا توجد بروكسيات")
            return
        
        if len(proxies) > 1000:
            proxies = proxies[:1000]
            bot.send_message(chat_id, f"⚠️ فحص أول 1000 بروكسي")
        
        progress_msg = bot.send_message(chat_id, f"🔍 فحص {len(proxies)} بروكسي...")
        working_proxies = []
        
        for i, (ip, port) in enumerate(proxies, 1):
            if not active_checks.get(chat_id, True): break
            
            if i % 10 == 0:
                try:
                    bot.edit_message_text(f"🔍 {i}/{len(proxies)} - ✅ {len(working_proxies)}", chat_id, progress_msg.message_id)
                except: pass
            
            result = check_single_proxy(ip, port, chat_id)
            if result and result['is_working']:
                working_proxies.append(result)
                user_results[chat_id] = working_proxies
            
            time.sleep(0.1)
        
        if active_checks.get(chat_id, True):
            try: bot.delete_message(chat_id, progress_msg.message_id)
            except: pass
            show_final_results(chat_id, working_proxies)
            active_checks[chat_id] = False
            
    except Exception as e:
        bot.send_message(chat_id, f"❌ خطأ: {str(e)}")

if __name__ == "__main__":
    print("🟢 البوت يعمل...")
    bot.infinity_polling()
