import telebot
import requests
import socket
import time
import concurrent.futures
import threading
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

# توكن البوت
bot = telebot.TeleBot("8420676859:AAGQ6ZgnTuUs648v_79hR_CEIw6VUqRE2B4")

# متغيرات التحكم في الفحص
scanning_active = {}
progress_counters = {}

def create_stop_keyboard():
    """إنشاء لوحة المفاتيح مع زر الإيقاف"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("⏹️ إيقاف الفحص"))
    return keyboard

def create_main_keyboard():
    """إنشاء لوحة المفاتيح الرئيسية"""
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True)
    keyboard.add(KeyboardButton("📋 فحص بروكسيات"))
    return keyboard

def extract_ip_port(proxy_text):
    """استخراج IP و PORT من النص"""
    try:
        proxy_text = proxy_text.strip()
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

def get_detailed_ip_info(ip):
    """
    الحصول على معلومات مفصلة عن الـ IP باستخدام ipinfo.io
    """
    try:
        response = requests.get(f"https://ipinfo.io/{ip}/json", timeout=5)
        if response.status_code == 200:
            data = response.json()
            
            country = data.get('country', 'Unknown')
            org = data.get('org', 'Unknown')
            
            if 'AS' in org:
                asn = org.split(' ')[0]
                isp = ' '.join(org.split(' ')[1:]) if len(org.split(' ')) > 1 else org
            else:
                asn = "ASUnknown"
                isp = org
            
            return {
                'country': country,
                'asn': asn,
                'isp': isp,
            }
        
    except Exception as e:
        print(f"Error fetching IP info for {ip}: {e}")
    
    return {
        'country': 'Unknown',
        'asn': 'ASUnknown',
        'isp': 'Unknown'
    }

def analyze_asn_risk(asn, isp):
    """تحليل مستوى خطر ASN"""
    asn_lower = str(asn).lower()
    isp_lower = str(isp).lower()
    
    high_risk = ['google', 'amazon', 'microsoft', 'cloudflare', 'facebook']
    medium_risk = ['ovh', 'digitalocean', 'linode', 'vultr', 'hetzner']
    
    for company in high_risk:
        if company in asn_lower or company in isp_lower:
            return 'high'
    
    for company in medium_risk:
        if company in asn_lower or company in isp_lower:
            return 'medium'
    
    return 'low'

def get_risk_icon(risk_level):
    """إرجاع أيقونة الخطر"""
    icons = {
        'high': '🔴🚨',
        'medium': '🟡⚠️', 
        'low': '⚪'
    }
    return icons.get(risk_level, '⚪')

def check_single_proxy(proxy_text, user_id, progress_key):
    """فحص بروكسي واحد مع تحديث التقدم"""
    if user_id in scanning_active and not scanning_active[user_id]:
        return None
    
    ip, port = extract_ip_port(proxy_text)
    if not ip or not port:
        return None
    
    try:
        # معلومات IP الأساسية
        ip_info = get_detailed_ip_info(ip)
        risk_level = analyze_asn_risk(ip_info['asn'], ip_info['isp'])
        risk_icon = get_risk_icon(risk_level)
        
        results = {
            'ip': ip,
            'port': port,
            'http': '❌',
            'https': '❌', 
            'connect': '❌',
            'is_working': False,
            'response_time': 0,
            'country': ip_info['country'],
            'asn': ip_info['asn'],
            'isp': ip_info['isp'],
            'risk_icon': risk_icon,
            'is_google': 'google' in ip_info['isp'].lower() or 'as396982' in ip_info['asn'].lower()
        }
        
        # فحص CONNECT أولاً (الأسرع)
        try:
            start_time = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)  # وقت أقل للسرعة
            result = sock.connect_ex((ip, port))
            connect_time = round((time.time() - start_time) * 1000, 2)
            
            if result == 0:
                results['connect'] = '✅'
                results['is_working'] = True
                results['response_time'] = connect_time
                sock.close()
                
                # تحديث العداد
                progress_counters[progress_key]['checked'] += 1
                progress_counters[progress_key]['working'] += 1
                return results
            sock.close()
        except:
            pass
        
        # فحص HTTP
        try:
            start_time = time.time()
            proxy_dict = {'http': f"http://{ip}:{port}"}
            response = requests.get(
                'http://httpbin.org/ip', 
                proxies=proxy_dict, 
                timeout=3,
                headers={'User-Agent': 'Mozilla/5.0'}
            )
            if response.status_code == 200:
                results['http'] = '✅'
                results['is_working'] = True
                results['response_time'] = round((time.time() - start_time) * 1000, 2)
                
                # تحديث العداد
                progress_counters[progress_key]['checked'] += 1
                progress_counters[progress_key]['working'] += 1
                return results
        except:
            pass
        
        # فحص HTTPS
        try:
            start_time = time.time()
            proxy_dict = {'https': f"https://{ip}:{port}"}
            response = requests.get(
                'https://httpbin.org/ip',
                proxies=proxy_dict, 
                timeout=3,
                headers={'User-Agent': 'Mozilla/5.0'},
                verify=False
            )
            if response.status_code == 200:
                results['https'] = '✅'
                results['is_working'] = True
                results['response_time'] = round((time.time() - start_time) * 1000, 2)
        except:
            pass
        
        # تحديث العداد حتى لو فشل
        progress_counters[progress_key]['checked'] += 1
        if results['is_working']:
            progress_counters[progress_key]['working'] += 1
            return results
        else:
            return None
            
    except Exception as e:
        print(f"Error checking proxy {proxy_text}: {e}")
        progress_counters[progress_key]['checked'] += 1
        return None

def update_progress_message(bot, chat_id, user_id, total, checked, working, message_id=None):
    """تحديث رسالة التقدم"""
    if user_id in scanning_active and not scanning_active[user_id]:
        return None
    
    progress = (checked / total) * 100 if total > 0 else 0
    progress_bar = "🟢" * int(progress / 20) + "⚪" * (5 - int(progress / 20))  # شريط أقصر
    
    progress_text = f"""
⏳ جاري الفحص...
{progress_bar} {progress:.1f}%

📊 التقدم:
• تم فحص: {checked}/{total}
• الشغالة: {working}
• المتبقي: {total - checked}
    """
    
    try:
        if message_id:
            bot.edit_message_text(progress_text, chat_id, message_id, reply_markup=create_stop_keyboard())
            return message_id
        else:
            msg = bot.send_message(chat_id, progress_text, reply_markup=create_stop_keyboard())
            return msg.message_id
    except:
        return message_id

def progress_updater(bot, chat_id, user_id, total, progress_key, progress_message_id):
    """محدث التقدم المستمر"""
    last_checked = 0
    
    while scanning_active.get(user_id, False):
        current_checked = progress_counters[progress_key]['checked']
        current_working = progress_counters[progress_key]['working']
        
        # تحديث فقط إذا تغيرت القيم
        if current_checked != last_checked:
            progress_message_id = update_progress_message(
                bot, chat_id, user_id, total, current_checked, current_working, progress_message_id
            )
            last_checked = current_checked
        
        # إذا انتهى الفحص، خروج
        if current_checked >= total:
            break
            
        time.sleep(1)  # تحديث كل ثانية

def check_proxies_list(proxies_list, user_id, chat_id, bot):
    """فحص قائمة بروكسيات مع تحديث التقدم"""
    working_proxies = []
    google_proxies = []
    
    total = len(proxies_list)
    
    # مفتاح فريد للتقدم
    progress_key = f"{user_id}_{int(time.time())}"
    progress_counters[progress_key] = {'checked': 0, 'working': 0}
    
    # بدء رسالة التقدم
    progress_message_id = update_progress_message(bot, chat_id, user_id, total, 0, 0)
    
    # بدء محدث التقدم في خيط منفصل
    progress_thread = threading.Thread(
        target=progress_updater,
        args=(bot, chat_id, user_id, total, progress_key, progress_message_id)
    )
    progress_thread.daemon = True
    progress_thread.start()
    
    # الفحص المتوازي
    with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
        future_to_proxy = {
            executor.submit(check_single_proxy, proxy, user_id, progress_key): proxy 
            for proxy in proxies_list
        }
        
        for future in concurrent.futures.as_completed(future_to_proxy):
            if user_id in scanning_active and not scanning_active[user_id]:
                executor.shutdown(wait=False)
                break
                
            proxy_data = future.result()
            if proxy_data:
                working_proxies.append(proxy_data)
                if proxy_data['is_google']:
                    google_proxies.append(proxy_data)
    
    # الانتظار قليلاً للتأكد من آخر تحديث
    time.sleep(1)
    
    # تنظيف
    if progress_key in progress_counters:
        del progress_counters[progress_key]
    
    return working_proxies, google_proxies

def format_proxy_result(proxy, index):
    """تنسيق نتيجة البروكسي"""
    google_flag = "🔴🚨" if proxy['is_google'] else proxy['risk_icon']
    response_time = f"⚡ {proxy['response_time']}ms" if proxy['response_time'] > 0 else ""
    
    # تحديد البروتوكول الناجح
    protocol_port = ""
    if proxy['http'] == '✅':
        protocol_port = f"HTTP✅{proxy['port']}"
    elif proxy['https'] == '✅':
        protocol_port = f"HTTPS✅{proxy['port']}" 
    elif proxy['connect'] == '✅':
        protocol_port = f"CONNECT✅{proxy['port']}"
    
    return f"""
{index}. **{proxy['ip']}:{proxy['port']}** {google_flag}
   🌍 **البلد:** {proxy['country']}
   🏢 **المزود:** {proxy['isp']}
   🆔 **ASN:** {proxy['asn']}
   {response_time} • {protocol_port}
    """

@bot.message_handler(commands=['start'])
def send_welcome(message):
    """رسالة الترحيب"""
    welcome_text = """
🚀 أهلاً بك في بوت فحص البروكسيات الذكي!

📝 أرسل قائمة البروكسيات للبدء...
مثال:
192.168.1.1:8080
34.41.115.197:3128
    """
    bot.send_message(message.chat.id, welcome_text, reply_markup=create_main_keyboard())

@bot.message_handler(func=lambda message: message.text == "📋 فحص بروكسيات")
def scan_button(message):
    """زر فحص البروكسيات"""
    msg = bot.send_message(message.chat.id, "📋 أرسل قائمة البروكسيات", reply_markup=create_main_keyboard())
    bot.register_next_step_handler(msg, process_scan_request)

@bot.message_handler(func=lambda message: message.text == "⏹️ إيقاف الفحص")
def stop_scan(message):
    """إيقاف الفحص"""
    user_id = message.from_user.id
    if user_id in scanning_active:
        scanning_active[user_id] = False
        bot.send_message(message.chat.id, "⏹️ جاري إيقاف الفحص...", reply_markup=create_main_keyboard())

def process_scan_request(message):
    """معالجة طلب الفحص"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    try:
        text = message.text.strip()
        
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
        
        scanning_active[user_id] = True
        bot.send_message(chat_id, f"🔍 بدء فحص {len(proxies_list)} بروكسي...", reply_markup=create_stop_keyboard())
        
        working_proxies, google_proxies = check_proxies_list(proxies_list, user_id, chat_id, bot)
        
        # عرض النتائج
        send_final_results(bot, chat_id, user_id, len(proxies_list), working_proxies, google_proxies)
            
    except Exception as e:
        bot.send_message(chat_id, f"❌ حدث خطأ: {str(e)}")
    finally:
        if user_id in scanning_active:
            scanning_active[user_id] = False

def send_final_results(bot, chat_id, user_id, total_proxies, working_proxies, google_proxies):
    """إرسال النتائج النهائية"""
    
    if not working_proxies:
        bot.send_message(chat_id, "❌ لا توجد بروكسيات شغالة في القائمة", reply_markup=create_main_keyboard())
        return
    
    result_text = f"""
📊 **نتائج الفحص** • تم فحص {total_proxies} بروكسي

✅ **الشغالة:** {len(working_proxies)}
🚨 **Google:** {len(google_proxies)}
⚡ **النسبة:** {(len(working_proxies)/total_proxies)*100:.1f}%

"""
    
    # إرسال تنبيه Google إذا وجد
    if google_proxies:
        alert_text = f"🚨 **تم العثور على {len(google_proxies)} بروكسي Google** 🔴🚨\n\n"
        bot.send_message(chat_id, alert_text)
    
    # إرسال النتائج
    for i, proxy in enumerate(working_proxies, 1):
        result_text += format_proxy_result(proxy, i)
    
    if len(result_text) > 4096:
        parts = [result_text[i:i+4096] for i in range(0, len(result_text), 4096)]
        for part in parts:
            bot.send_message(chat_id, part, reply_markup=create_main_keyboard())
    else:
        bot.send_message(chat_id, result_text, reply_markup=create_main_keyboard())

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    """معالجة جميع الرسائل تلقائياً"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    text = message.text
    if ':' in text and any(char.isdigit() for char in text) and text not in ["📋 فحص بروكسيات", "⏹️ إيقاف الفحص"]:
        process_scan_request(message)
    elif text not in ["📋 فحص بروكسيات", "⏹️ إيقاف الفحص"]:
        bot.send_message(chat_id, "📝 أرسل قائمة البروكسيات للفحص", reply_markup=create_main_keyboard())

if __name__ == "__main__":
    print("🟢 بدء تشغيل بوت فحص البروكسيات المحسن...")
    print("⚡ تم إصلاح مشكلة العداد والتحديث الحي")
    bot.infinity_polling()
