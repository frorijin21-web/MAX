import telebot
import requests
import socket
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

# توكن البوت
bot = telebot.TeleBot("8420676859:AAGQ6ZgnTuUs648v_79hR_CEIw6VUqRE2B4")

# تخزين العمليات والنتائج
active_checks = {}
user_results = {}

MAX_THREADS = 50  # عدد الخيوط المتزامنة

# ------------------- لوحات المفاتيح -------------------
def create_main_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("/start"), KeyboardButton("/stop"))
    return keyboard

def create_check_keyboard():
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("فحص نص"), KeyboardButton("فحص رابط"))
    keyboard.add(KeyboardButton("/stop"))
    return keyboard

# ------------------- تنبيهات -------------------
def send_google_alert(chat_id, proxy_info):
    alert_text = f"""
🚨 **تنبيه Google النادر!** 🚨

📍 **IP:** `{proxy_info['ip']}:{proxy_info['port']}`
🏢 **المزود:** Google LLC
🆔 **ASN:** {proxy_info['ip_info']['asn']}
📍 **الموقع:** {proxy_info['ip_info']['city']}, {proxy_info['ip_info']['country']}

🔍 **نتائج الفحص:**
   🌐 HTTP: {proxy_info['http']}
   🔒 HTTPS: {proxy_info['https']}
   🔌 CONNECT 80: {proxy_info['connect_80']}

⚡ **بروكسي Google نادر وجودة عالية!**
"""
    bot.send_message(chat_id, alert_text, parse_mode='Markdown')

# ------------------- معلومات IP -------------------
def get_detailed_ip_info(ip):
    try:
        response = requests.get(f"http://ip-api.com/json/{ip}?fields=66846719", timeout=5)
        data = response.json()
        if data['status'] == 'success':
            risk_level = analyze_asn_risk(data.get('as', ''), data.get('isp', ''))
            return {
                'asn': data.get('as', 'غير معروف'),
                'isp': data.get('isp', 'غير معروف'),
                'country': data.get('country', 'غير معروف'),
                'city': data.get('city', 'غير معروف'),
                'org': data.get('org', 'غير معروف'),
                'risk_level': risk_level,
                'risk_emoji': get_risk_emoji(risk_level)
            }
    except:
        pass
    return None

def analyze_asn_risk(asn, isp):
    if 'google' in str(asn).lower() or 'google' in str(isp).lower():
        return 'high'
    return 'low'

def get_risk_emoji(risk_level):
    return {'high': '🔴🚨', 'medium': '🟡⚠️', 'low': '🟢✅'}.get(risk_level, '⚪❓')

# ------------------- فحص البروكسي -------------------
def check_single_proxy(proxy_ip, proxy_port, chat_id):
    proxy_url = f"{proxy_ip}:{proxy_port}"
    proxies = {"http": f"http://{proxy_url}", "https": f"http://{proxy_url}"}
    result = {
        "ip": proxy_ip,
        "port": proxy_port,
        "http": "❌",
        "https": "❌",
        "connect_80": "❌",
        "ip_info": None,
        "is_working": False
    }
    try:
        # CONNECT 80
        try:
            with socket.create_connection((proxy_ip, int(proxy_port)), timeout=2):
                result["connect_80"] = "✅"
        except:
            pass

        # HTTP Test
        try:
            r = requests.get("http://example.com", proxies=proxies, timeout=3)
            if r.status_code == 200 and "Example Domain" in r.text:
                result["http"] = "✅"
        except:
            pass

        # HTTPS Test
        try:
            r = requests.get("https://www.google.com", proxies=proxies, timeout=4, verify=False)
            if r.status_code == 200 and "Google" in r.text:
                result["https"] = "✅"
        except:
            pass

        # بيانات IP إذا البروكسي شغال
        if result["http"] == "✅" or result["https"] == "✅" or result["connect_80"] == "✅":
            result["is_working"] = True
            result["ip_info"] = get_detailed_ip_info(proxy_ip)
            if (result["ip_info"]
                and "AS396982" in result["ip_info"].get("asn", "")
                and "Google LLC" in result["ip_info"].get("isp", "")):
                send_google_alert(chat_id, result)

    except Exception as e:
        print(f"Proxy {proxy_url} failed: {e}")
    return result

# ------------------- عرض النتائج -------------------
def show_final_results(chat_id, working_proxies):
    truly_working = [p for p in working_proxies if p.get('is_working', False)]
    if not truly_working:
        bot.send_message(chat_id, "❌ لم أعثر على أي بروكسيات شغالة")
        return

    results_text = f"📊 **نتائج الفحص المتقدم**\n\n"
    results_text += f"✅ **تم العثور على {len(truly_working)} بروكسي شغال**\n\n"

    for i, proxy in enumerate(truly_working[:15], 1):
        results_text += f"**{i}. {proxy['ip']}:{proxy['port']}**\n"
        if proxy['ip_info']:
            info = proxy['ip_info']
            results_text += f"   🏢 **ISP:** {info['isp']}\n"
            results_text += f"   🆔 **ASN:** {info['asn']} {info['risk_emoji']}\n"
            results_text += f"   📍 **الموقع:** {info['city']}, {info['country']}\n"
        results_text += f"   🌐 **HTTP:** {proxy['http']}\n"
        results_text += f"   🔒 **HTTPS:** {proxy['https']}\n"
        results_text += f"   🔌 **CONNECT 80:** {proxy['connect_80']}\n"
        results_text += "─" * 40 + "\n\n"

    if len(truly_working) > 0:
        http_count = sum(1 for p in truly_working if p['http'] == '✅')
        https_count = sum(1 for p in truly_working if p['https'] == '✅')
        connect_80_count = sum(1 for p in truly_working if p['connect_80'] == '✅')
        results_text += f"📈 **إحصائيات عامة:**\n"
        results_text += f"   • بروكسيات تدعم HTTP: **{http_count}**\n"
        results_text += f"   • بروكسيات تدعم HTTPS: **{https_count}**\n"
        results_text += f"   • بروكسيات تدعم CONNECT 80: **{connect_80_count}**\n"

    if len(truly_working) > 15:
        results_text += f"\n📁 **و {len(truly_working) - 15} بروكسي إضافي...**"

    results_text += "\n🛑 **تم إيقاف البحث بناءً على طلبك**"
    bot.send_message(chat_id, results_text, reply_markup=create_main_keyboard(), parse_mode='Markdown')
    if chat_id in user_results:
        del user_results[chat_id]

# ------------------- أوامر البوت -------------------
@bot.message_handler(commands=['start'])
def start_command(message):
    welcome_text = """
🎯 **بوت فحص البروكسيات المتقدم** 🛡️

⚡ **المميزات:**
• فحص HTTP/HTTPS/CONNECT 80
• كشف مزودي الخدمة
• تحليل مخاطر متقدم
• سرعة فحص عالية
• تنبيهات لبروكسيات Google النادرة

🎮 **اختر نوع الفحص:**
"""
    bot.send_message(message.chat.id, welcome_text, reply_markup=create_check_keyboard())

@bot.message_handler(commands=['stop'])
def stop_command(message):
    chat_id = message.chat.id
    if chat_id in active_checks:
        active_checks[chat_id] = False
    if chat_id in user_results and user_results[chat_id]:
        show_final_results(chat_id, user_results[chat_id])
    else:
        bot.send_message(chat_id, "🛑 تم إيقاف البحث\n❌ لا توجد نتائج لعرضها", reply_markup=create_main_keyboard())

# ------------------- معالجة فحص النص -------------------
def process_text_check(message):
    chat_id = message.chat.id
    active_checks[chat_id] = True
    user_results[chat_id] = []

    lines = [l.strip() for l in message.text.strip().splitlines() if ":" in l]
    proxies = [(l.split(":")[0], l.split(":")[1]) for l in lines if l]

    if not proxies:
        bot.send_message(chat_id, "❌ لم أجد أي بروكسيات صالحة")
        return

    if len(proxies) > 1000:
        proxies = proxies[:1000]
        bot.send_message(chat_id, "⚠️ سيتم فحص أول 1000 بروكسي فقط")

    bot.send_message(chat_id, f"🚀 بدء فحص {len(proxies)} بروكسي بسرعة عالية...")

    working_proxies = []
    with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
        future_to_proxy = {executor.submit(check_single_proxy, ip, port, chat_id): (ip, port) for ip, port in proxies}
        checked = 0
        for future in as_completed(future_to_proxy):
            if not active_checks.get(chat_id, True):
                break
            result = future.result()
            checked += 1
            if result and result["is_working"]:
                working_proxies.append(result)
                user_results[chat_id] = working_proxies
            if checked % 20 == 0:
                bot.send_message(chat_id, f"⏱️ فُحص {checked}/{len(proxies)} — ✅ {len(working_proxies)} شغال")

    show_final_results(chat_id, working_proxies)

# ------------------- تشغيل البوت -------------------
if __name__ == "__main__":
    print("🟢 بدء تشغيل بوت فحص البروكسيات المتقدم...")
    bot.infinity_polling()
