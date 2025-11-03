import telebot
import requests
import socket
import time
import threading
from datetime import datetime
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
import concurrent.futures

# توكن البوت - ضعيه هنا
bot = telebot.TeleBot("8420676859:AAGQ6ZgnTuUs648v_79hR_CEIw6VUqRE2B4")

# قائمة المستخدمين المصرح لهم
authorized_users = []  # ضعي هنا أي دي المستخدمين المصرح لهم

def is_authorized(user_id):
    """التحقق من صلاحية المستخدم"""
    return user_id in authorized_users if authorized_users else True

def extract_ip_port(proxy_text):
    """استخراج IP و PORT من النص"""
    try:
        if ':' in proxy_text:
            parts = proxy_text.split(':')
            if len(parts) >= 2:
                ip = parts[0].strip()
                port = int(parts[1].strip())
                return ip, port
        return None, None
    except:
        return None, None

def get_asn_info(ip):
    """الحصول على معلومات ASN (مثال مبسط)"""
    try:
        # فحص إذا كان IP تابع لـ Google
        if ip.startswith(('34.', '35.', '104.', '108.', '130.', '140.', '142.', '143.', '144.', '146.', '148.', '172.', '173.', '174.', '209.')):
            return "Google LLC", "AS396982 Google LLC"
        
        # يمكن إضافة مزودين آخرين إذا تريدين
        hostname = socket.gethostbyaddr(ip)[0]
        if 'google' in hostname.lower():
            return "Google LLC", "AS396982 Google LLC"
        else:
            return "Unknown", "ASUnknown"
    except:
        return "Unknown", "ASUnknown"

def test_proxy_protocols(proxy_ip, proxy_port, timeout=10):
    """فحص البروكسي على جميع البروتوكولات"""
    proxy_url = f"{proxy_ip}:{proxy_port}"
    results = {
        'http': '❌',
        'https': '❌', 
        'connect': '❌',
        'working': False
    }
    
    # فحص HTTP
    try:
        proxies = {'http': f'http://{proxy_url}'}
        response = requests.get('http://httpbin.org/ip', proxies=proxies, timeout=timeout)
        if response.status_code == 200:
            results['http'] = '✅'
            results['working'] = True
    except:
        pass
    
    # فحص HTTPS
    try:
        proxies = {'https': f'https://{proxy_url}'}
        response = requests.get('https://httpbin.org/ip', proxies=proxies, timeout=timeout)
        if response.status_code == 200:
            results['https'] = '✅'
            results['working'] = True
    except:
        pass
    
    # فحص CONNECT (للمتصفح)
    try:
        proxies = {'https': f'https://{proxy_url}'}
        response = requests.get('https://www.google.com', proxies=proxies, timeout=timeout)
        if response.status_code == 200:
            results['connect'] = '✅'
            results['working'] = True
    except:
        pass
    
    return results

def check_single_proxy(proxy_text):
    """فحص بروكسي واحد"""
    ip, port = extract_ip_port(proxy_text)
    if not ip or not port:
        return None, "❌ تنسيق غير صحيح"
    
    # الحصول على معلومات ASN
    provider, asn = get_asn_info(ip)
    
    # فحص البروتوكولات
    protocols = test_proxy_protocols(ip, port)
    
    # نرجع البيانات فقط إذا كان البروكسي شغال
    if protocols['working']:
        return {
            'ip': ip,
            'port': port,
            'provider': provider,
            'asn': asn,
            'protocols': protocols,
            'text': proxy_text
        }, None
    else:
        return None, "❌ البروكسي غير شغال"

def check_multiple_proxies(proxies_list):
    """فحص قائمة بروكسيات - يرجع فقط الشغالة"""
    working_proxies = []
    google_proxies = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_proxy = {executor.submit(check_single_proxy, proxy): proxy for proxy in proxies_list}
        
        for future in concurrent.futures.as_completed(future_to_proxy):
            proxy_data, error = future.result()
            if proxy_data:  # فقط إذا كان شغال
                working_proxies.append(proxy_data)
                if 'google' in proxy_data['provider'].lower():
                    google_proxies.append(proxy_data)
    
    return working_proxies, google_proxies

@bot.message_handler(commands=['start'])
def send_welcome(message):
    """رسالة الترحيب"""
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "❌ غير مصرح لك باستخدام البوت")
        return
    
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("🔄 فحص بروكسي واحد"))
    keyboard.add(KeyboardButton("📋 فحص قائمة بروكسيات"))
    keyboard.add(KeyboardButton("ℹ️ معلومات البوت"))
    
    welcome_text = """
    🚀 أهلاً بك في بوت فحص البروكسيات المتقدم!
    
    ⚡ المميزات:
    • فحص HTTP/HTTPS/CONNECT
    • كشف بروكسيات Google النادرة 🚨
    • عرض البروكسيات الشغالة فقط ✅
    • فحص متعدد سريع
    
    📖 الأوامر المتاحة:
    /start - بدء الاستخدام
    /scan - فحص بروكسي
    /bulk - فحص قائمة
    """
    
    bot.send_message(message.chat.id, welcome_text, reply_markup=keyboard)

@bot.message_handler(commands=['scan'])
def scan_proxy_command(message):
    """فحص بروكسي واحد"""
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "❌ غير مصرح لك باستخدام البوت")
        return
    
    msg = bot.send_message(message.chat.id, "🔍 أرسل البروكسي للتفحص (مثال: 34.41.115.197:3128)")
    bot.register_next_step_handler(msg, process_single_proxy)

def process_single_proxy(message):
    """معالجة فحص بروكسي واحد"""
    try:
        proxy_text = message.text.strip()
        bot.send_message(message.chat.id, "⏳ جاري الفحص...")
        
        proxy_data, error = check_single_proxy(proxy_text)
        
        if error:
            bot.send_message(message.chat.id, error)
            return
        
        # بناء رسالة النتيجة
        result_text = f"""
📊 نتيجة فحص البروكسي:

📍 العنوان: {proxy_data['ip']}:{proxy_data['port']}
🏢 المزود: {proxy_data['provider']}
🆔 ASN: {proxy_data['asn']} {'🔴🚨' if 'google' in proxy_data['provider'].lower() else ''}

🌐 البروتوكولات:
• HTTP: {proxy_data['protocols']['http']}
• HTTPS: {proxy_data['protocols']['https']}
• CONNECT: {proxy_data['protocols']['connect']}
        """
        
        # إرسال تنبيه إذا كان Google
        if 'google' in proxy_data['provider'].lower():
            alert_text = f"""
🚨 تنبيه Google النادر! 🚨

📍 IP: {proxy_data['ip']}:{proxy_data['port']}
🏢 المزود: {proxy_data['provider']}
🆔 ASN: {proxy_data['asn']} 🔴🚨

🎯 تم العثور على بروكسي Google نادر وشغال!
            """
            bot.send_message(message.chat.id, alert_text)
        
        bot.send_message(message.chat.id, result_text)
        
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ حدث خطأ: {str(e)}")

@bot.message_handler(commands=['bulk'])
def bulk_scan_command(message):
    """فحص قائمة بروكسيات"""
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "❌ غير مصرح لك باستخدام البوت")
        return
    
    msg = bot.send_message(message.chat.id, "📋 أرسل قائمة البروكسيات (كل بروكسي في سطر) - الحد 500")
    bot.register_next_step_handler(msg, process_bulk_scan)

def process_bulk_scan(message):
    """معالجة فحص القائمة"""
    try:
        proxies_text = message.text.strip()
        proxies_list = [p.strip() for p in proxies_text.split('\n') if p.strip()]
        
        if len(proxies_list) > 500:
            bot.send_message(message.chat.id, "❌ الحد الأقصى 500 بروكسي")
            return
        
        bot.send_message(message.chat.id, f"⏳ جاري فحص {len(proxies_list)} بروكسي...")
        
        working_proxies, google_proxies = check_multiple_proxies(proxies_list[:500])
        
        # إذا ما في بروكسيات شغالة
        if not working_proxies:
            bot.send_message(message.chat.id, "❌ لا توجد بروكسيات شغالة في القائمة")
            return
        
        # إرسال تنبيه Google إذا وجد
        if google_proxies:
            alert_text = f"""
🚨 تنبيه Google النادر! 🚨

تم العثور على {len(google_proxies)} بروكسي Google شغال

📋 قائمة بروكسيات Google:
            """
            for i, proxy in enumerate(google_proxies, 1):
                alert_text += f"""
{i}. {proxy['ip']}:{proxy['port']}
   🏢 {proxy['provider']}
   🆔 {proxy['asn']} 🔴🚨
                """
            
            bot.send_message(message.chat.id, alert_text)
        
        # إرسال النتائج النهائية (فقط البروكسيات الشغالة)
        result_text = f"""
📊 نتائج الفحص الشامل:

🔍 العدد المفحوص: {len(proxies_list)}
✅ البروكسيات الشغالة: {len(working_proxies)}
🚨 بروكسيات Google: {len(google_proxies)}

📋 قائمة البروكسيات الشغالة فقط:
        """
        
        for i, proxy in enumerate(working_proxies, 1):
            google_flag = "🔴🚨" if 'google' in proxy['provider'].lower() else ""
            result_text += f"""
{i}. {proxy['ip']}:{proxy['port']}
   🏢 {proxy['provider']} {google_flag}
   🌐 HTTP: {proxy['protocols']['http']} | HTTPS: {proxy['protocols']['https']} | CONNECT: {proxy['protocols']['connect']}
            """
        
        # تقسيم الرسالة إذا كانت طويلة
        if len(result_text) > 4096:
            parts = [result_text[i:i+4096] for i in range(0, len(result_text), 4096)]
            for part in parts:
                bot.send_message(message.chat.id, part)
        else:
            bot.send_message(message.chat.id, result_text)
            
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ حدث خطأ: {str(e)}")

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    """معالجة جميع الرسائل"""
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "❌ غير مصرح لك باستخدام البوت")
        return
    
    text = message.text
    
    if text == "🔄 فحص بروكسي واحد":
        scan_proxy_command(message)
    elif text == "📋 فحص قائمة بروكسيات":
        bulk_scan_command(message)
    elif text == "ℹ️ معلومات البوت":
        bot_info = """
🤖 بوت فحص البروكسيات المتقدم

⚡ المميزات:
• فحص سريع ومتعدد الخيوط
• كشف بروكسيات Google النادرة 🚨
• عرض البروكسيات الشغالة فقط ✅
• دعم 3 بروتوكولات

🎯 الإعدادات:
• سرعة فحص: حتى 500 بروكسي
• يعرض: الشغالة فقط
• تنبيهات: Google خاصة
        """
        bot.send_message(message.chat.id, bot_info)
    else:
        # إذا كان يبدو كبروكسي، فحصه تلقائياً
        if ':' in text and any(char.isdigit() for char in text):
            process_single_proxy(message)
        else:
            bot.send_message(message.chat.id, "❌ أمر غير معروف، استخدم الأزرار أو /start")

if __name__ == "__main__":
    print("🟢 بدء تشغيل بوت فحص البروكسيات المتقدم...")
    print("⚡ المميزات: فحص HTTP/HTTPS/CONNECT، كشف ASN، تحليل مخاطر")
    print("🎯 البوت جاهز لاستقبال الطلبات...")
    bot.infinity_polling()
