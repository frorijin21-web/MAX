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

# متغيرات التحكم في الفحص
scanning_active = {}
scan_results = {}

def is_authorized(user_id):
    """التحقق من صلاحية المستخدم"""
    return user_id in authorized_users if authorized_users else True

def extract_ip_port(proxy_text):
    """استخراج IP و PORT من النص"""
    try:
        proxy_text = proxy_text.strip()
        # إزالة أي بروتوكول مسبق
        proxy_text = proxy_text.replace('http://', '').replace('https://', '').replace('socks://', '').replace('socks5://', '')
        
        if ':' in proxy_text:
            parts = proxy_text.split(':')
            if len(parts) >= 2:
                ip = parts[0].strip()
                port = int(parts[1].strip())
                if 1 <= port <= 65535:
                    return ip, port
        return None, None
    except:
        return None, None

def get_asn_info(ip):
    """الحصول على معلومات ASN"""
    try:
        # نطاقات IPs الخاصة بجوجل
        google_ranges = [
            '8.8.', '8.34.', '8.35.', '23.236.', '23.251.', '34.0.', '34.1.', '34.2.', '34.3.', 
            '34.4.', '34.16.', '34.32.', '34.64.', '34.96.', '34.128.', '34.160.', '34.192.', 
            '35.184.', '35.188.', '35.192.', '35.196.', '35.200.', '35.204.', '35.208.', '35.212.',
            '104.154.', '104.196.', '107.167.', '107.178.', '108.59.', '108.170.', '108.177.',
            '130.211.', '136.112.', '142.250.', '142.251.', '146.148.', '162.216.', '162.222.',
            '172.217.', '172.253.', '173.194.', '173.255.', '192.158.', '192.178.', '199.192.',
            '199.223.', '207.223.', '208.46.', '208.68.', '208.81.', '208.127.', '209.85.'
        ]
        
        for range_ip in google_ranges:
            if ip.startswith(range_ip):
                return "Google LLC", "AS396982 Google LLC"
        
        return "Unknown", "ASUnknown"
    except:
        return "Unknown", "ASUnknown"

def test_proxy_advanced(proxy_ip, proxy_port, timeout=4):
    """فحص متقدم للبروكسي مع محاولات متعددة وفحص تدريجي"""
    proxy_url = f"{proxy_ip}:{proxy_port}"
    results = {
        'http': '❌',
        'https': '❌', 
        'connect': '❌',
        'working': False,
        'response_time': 0
    }
    
    # 1. فحص HTTP أولاً (الأسرع عادة)
    try:
        start_time = time.time()
        proxies_http = {'http': f'http://{proxy_url}', 'https': f'https://{proxy_url}'}
        response = requests.get(
            'http://httpbin.org/ip', 
            proxies=proxies_http, 
            timeout=timeout,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        response_time = round((time.time() - start_time) * 1000, 2)
        
        if response.status_code == 200:
            results['http'] = '✅'
            results['working'] = True
            results['response_time'] = response_time
            # إذا شغال HTTP، نعود مباشرة لتوفير الوقت
            return results
    except:
        pass
    
    # 2. فحص HTTPS ثانياً
    try:
        start_time = time.time()
        proxies_https = {'https': f'https://{proxy_url}', 'http': f'http://{proxy_url}'}
        response = requests.get(
            'https://httpbin.org/ip', 
            proxies=proxies_https, 
            timeout=timeout,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        response_time = round((time.time() - start_time) * 1000, 2)
        
        if response.status_code == 200:
            results['https'] = '✅'
            results['working'] = True
            results['response_time'] = response_time
            return results
    except:
        pass
    
    # 3. فحص CONNECT أخيراً (للمتصفح)
    try:
        start_time = time.time()
        proxies_connect = {'https': f'https://{proxy_url}', 'http': f'http://{proxy_url}'}
        response = requests.get(
            'https://www.google.com', 
            proxies=proxies_connect, 
            timeout=timeout,
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        )
        response_time = round((time.time() - start_time) * 1000, 2)
        
        if response.status_code == 200:
            results['connect'] = '✅'
            results['working'] = True
            results['response_time'] = response_time
    except:
        pass
    
    return results

def check_single_proxy(proxy_text, user_id):
    """فحص بروكسي واحد مع التحقق من التوقف"""
    if user_id in scanning_active and not scanning_active[user_id]:
        return None, "⏹️ تم إيقاف الفحص"
    
    ip, port = extract_ip_port(proxy_text)
    if not ip or not port:
        return None, "❌ تنسيق غير صحيح"
    
    # الحصول على معلومات ASN
    provider, asn = get_asn_info(ip)
    
    # فحص البروتوكولات
    protocols = test_proxy_advanced(ip, port)
    
    # نرجع البيانات فقط إذا كان البروكسي شغال
    if protocols['working']:
        return {
            'ip': ip,
            'port': port,
            'provider': provider,
            'asn': asn,
            'protocols': protocols,
            'text': proxy_text,
            'response_time': protocols['response_time']
        }, None
    else:
        return None, None

def update_progress_message(bot, chat_id, user_id, total, checked, working, message_id=None):
    """تحديث رسالة التقدم"""
    if user_id in scanning_active and not scanning_active[user_id]:
        return None
    
    progress = (checked / total) * 100 if total > 0 else 0
    progress_bar = "🟢" * int(progress / 10) + "⚪" * (10 - int(progress / 10))
    
    progress_text = f"""
⏳ جاري الفحص...
{progress_bar} {progress:.1f}%

📊 التقدم:
• 📋 الإجمالي: {total}
• 🔍 تم فحص: {checked}
• ✅ الشغالة: {working}
• ⏳ المتبقي: {total - checked}
    """
    
    try:
        if message_id:
            bot.edit_message_text(
                progress_text, 
                chat_id, 
                message_id,
                reply_markup=create_stop_keyboard()
            )
            return message_id
        else:
            msg = bot.send_message(
                chat_id, 
                progress_text,
                reply_markup=create_stop_keyboard()
            )
            return msg.message_id
    except:
        return message_id

def create_stop_keyboard():
    """إنشاء زر إيقاف"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("⏹️ إيقاف الفحص"))
    return keyboard

def create_main_keyboard():
    """إنشاء لوحة المفاتيح الرئيسية"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("📋 فحص قائمة بروكسيات"))
    keyboard.add(KeyboardButton("ℹ️ معلومات البوت"))
    return keyboard

def check_proxies_list(proxies_list, user_id, chat_id, bot):
    """فحص قائمة بروكسيات مع تحديث التقدم"""
    working_proxies = []
    google_proxies = []
    
    total = len(proxies_list)
    checked = 0
    working = 0
    
    # إرسال رسالة التقدم الأولى
    progress_message_id = update_progress_message(bot, chat_id, user_id, total, checked, working)
    last_update = time.time()
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=25) as executor:
        future_to_proxy = {executor.submit(check_single_proxy, proxy, user_id): proxy for proxy in proxies_list}
        
        for future in concurrent.futures.as_completed(future_to_proxy):
            if user_id in scanning_active and not scanning_active[user_id]:
                for f in future_to_proxy:
                    f.cancel()
                executor.shutdown(wait=False)
                break
                
            proxy_data, error = future.result()
            checked += 1
            
            if proxy_data:
                working += 1
                working_proxies.append(proxy_data)
                if 'google' in proxy_data['provider'].lower():
                    google_proxies.append(proxy_data)
            
            # تحديث العداد كل ثانيتين كحد أدنى أو عند انتهاء 10% من العمل
            current_time = time.time()
            if current_time - last_update > 2 or checked % max(1, total//10) == 0 or checked == total:
                progress_message_id = update_progress_message(
                    bot, chat_id, user_id, total, checked, working, progress_message_id
                )
                last_update = current_time
    
    return working_proxies, google_proxies

@bot.message_handler(commands=['start'])
def send_welcome(message):
    """رسالة الترحيب"""
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "❌ غير مصرح لك باستخدام البوت")
        return
    
    welcome_text = """
    🚀 أهلاً بك في بوت فحص البروكسيات المتقدم!
    
    ⚡ المميزات:
    • فحص تلقائي (مفرد/متعدد)
    • كشف بروكسيات Google النادرة 🚨
    • عرض البروكسيات الشغالة فقط ✅
    • عداد تقدم متقدم ⏳
    • إيقاف فوري أثناء العمل ⏹️
    
    🎯 طريقة الاستخدام:
    فقط أرسل البروكسي أو قائمة البروكسيات
    مثال:
    192.168.1.1:8080
    34.41.115.197:3128
    
    وسيبدأ الفحص تلقائياً!
    """
    
    bot.send_message(message.chat.id, welcome_text, reply_markup=create_main_keyboard())

def process_scan_request(message):
    """معالجة طلب الفحص التلقائي"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    try:
        text = message.text.strip()
        
        # فصل البروكسيات (سطر جديد أو فاصلة أو مسافة)
        proxies_list = []
        for line in text.split('\n'):
            for item in line.split(','):
                for proxy in item.split():
                    if ':' in proxy and any(char.isdigit() for char in proxy):
                        proxies_list.append(proxy.strip())
        
        if not proxies_list:
            bot.send_message(chat_id, "❌ لم يتم العثور على بروكسيات صالحة")
            return
        
        if len(proxies_list) > 500:
            bot.send_message(chat_id, "❌ الحد الأقصى 500 بروكسي")
            return
        
        # بدء الفحص
        scanning_active[user_id] = True
        scan_results[user_id] = {'working': [], 'google': []}
        
        # فحص البروكسيات
        working_proxies, google_proxies = check_proxies_list(proxies_list, user_id, chat_id, bot)
        
        # إرسال النتائج
        send_scan_results(bot, chat_id, user_id, len(proxies_list), working_proxies, google_proxies)
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ حدث خطأ: {str(e)}")
    finally:
        if user_id in scanning_active:
            scanning_active[user_id] = False

def send_scan_results(bot, chat_id, user_id, total_proxies, working_proxies, google_proxies):
    """إرسال نتائج الفحص"""
    
    # إذا تم الإيقاف
    if user_id in scanning_active and not scanning_active[user_id]:
        result_text = f"""
⏹️ تم إيقاف الفحص

📊 النتائج حتى الآن:
• 📋 الإجمالي: {total_proxies}
• ✅ الشغالة: {len(working_proxies)}
• 🚨 Google: {len(google_proxies)}
        """
        bot.send_message(chat_id, result_text, reply_markup=create_main_keyboard())
        return
    
    # إذا لا توجد بروكسيات شغالة
    if not working_proxies:
        bot.send_message(chat_id, "❌ لا توجد بروكسيات شغالة في القائمة", reply_markup=create_main_keyboard())
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
   ⚡ {proxy['response_time']}ms
            """
        
        bot.send_message(chat_id, alert_text)
    
    # إرسال النتائج النهائية
    result_text = f"""
📊 نتائج الفحص النهائية:

• 📋 الإجمالي المفحوص: {total_proxies}
• ✅ البروكسيات الشغالة: {len(working_proxies)}
• 🚨 بروكسيات Google: {len(google_proxies)}
• ⚡ نسبة النجاح: {(len(working_proxies)/total_proxies)*100:.1f}%

📋 البروكسيات الشغالة:
    """
    
    for i, proxy in enumerate(working_proxies, 1):
        google_flag = "🔴🚨" if 'google' in proxy['provider'].lower() else ""
        response_time = f"⚡ {proxy['response_time']}ms" if proxy['response_time'] > 0 else ""
        
        result_text += f"""
{i}. {proxy['ip']}:{proxy['port']} {google_flag}
   🏢 {proxy['provider']} {response_time}
   🌐 HTTP: {proxy['protocols']['http']} | HTTPS: {proxy['protocols']['https']} | CONNECT: {proxy['protocols']['connect']}
        """
    
    # تقسيم الرسالة إذا كانت طويلة
    if len(result_text) > 4096:
        parts = [result_text[i:i+4096] for i in range(0, len(result_text), 4096)]
        for part in parts:
            bot.send_message(chat_id, part)
    else:
        bot.send_message(chat_id, result_text, reply_markup=create_main_keyboard())

@bot.message_handler(func=lambda message: message.text == "⏹️ إيقاف الفحص")
def stop_scan(message):
    """إيقاف الفحص"""
    user_id = message.from_user.id
    if user_id in scanning_active:
        scanning_active[user_id] = False
        bot.send_message(message.chat.id, "⏹️ تم إيقاف الفحص بنجاح!", reply_markup=create_main_keyboard())

@bot.message_handler(func=lambda message: message.text == "📋 فحص قائمة بروكسيات")
def bulk_scan_button(message):
    """زر فحص القائمة"""
    msg = bot.send_message(message.chat.id, "📋 أرسل قائمة البروكسيات (واحد أو أكثر في كل سطر)")
    bot.register_next_step_handler(msg, process_scan_request)

@bot.message_handler(func=lambda message: message.text == "ℹ️ معلومات البوت")
def bot_info(message):
    """معلومات البوت"""
    bot_info_text = """
🤖 بوت فحص البروكسيات المتقدم - الإصدار المحسن

⚡ المميزات الجديدة:
• فحص متسلسل سريع (HTTP → HTTPS → CONNECT)
• 25 عملية فحص متوازية
• وقت استجابة محسن (4 ثواني)
• تحديث حي ومستمر للعداد
• إيقاف فوري

🎯 الخصائص التقنية:
• السرعة: 25 بروكسي في نفس الوقت
• الدقة: فحص تدريجي متسلسل
• الكفاءة: توقف عند أول نجاح
• السعة: حتى 500 بروكسي
    """
    bot.send_message(message.chat.id, bot_info_text)

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    """معالجة جميع الرسائل تلقائياً"""
    if not is_authorized(message.from_user.id):
        bot.reply_to(message, "❌ غير مصرح لك باستخدام البوت")
        return
    
    text = message.text
    
    # إذا كان يبدو كبروكسي، فحصه تلقائياً
    if ':' in text and any(char.isdigit() for char in text):
        process_scan_request(message)
    elif text not in ["📋 فحص قائمة بروكسيات", "ℹ️ معلومات البوت", "⏹️ إيقاف الفحص"]:
        bot.send_message(message.chat.id, 
                       "🎯 أرسل البروكسيات للفحص التلقائي\n\n" +
                       "📝 مثال:\n192.168.1.1:8080\n34.41.115.197:3128\n\n" +
                       "أو استخدم الأزرار أدناه 👇", 
                       reply_markup=create_main_keyboard())

if __name__ == "__main__":
    print("🟢 بدء تشغيل بوت فحص البروكسيات المتقدم...")
    print("⚡ المميزات: فحص تدريجي سريع، 25 عملية متوازية، تحديث حي")
    print("🎯 البوت جاهز لاستقبال الطلبات...")
    bot.infinity_polling()
