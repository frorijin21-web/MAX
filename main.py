import telebot
import requests
import socket
import time
import concurrent.futures

# توكن البوت
bot = telebot.TeleBot("8420676859:AAGQ6ZgnTuUs648v_79hR_CEIw6VUqRE2B4")

# متغيرات التحكم في الفحص
scanning_active = {}

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

def get_asn_info(ip):
    """الحصول على معلومات ASN والمزود"""
    try:
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

def check_single_proxy(proxy_text, user_id):
    """فحص بروكسي واحد مع التحقق من التوقف - النسخة المحسنة"""
    if user_id in scanning_active and not scanning_active[user_id]:
        return None, "⏹️ تم إيقاف الفحص"
    
    ip, port = extract_ip_port(proxy_text)
    if not ip or not port:
        return None, "❌ تنسيق غير صحيح"
    
    try:
        results = {
            'ip': ip,
            'port': port,
            'http': '❌',
            'https': '❌', 
            'connect': '❌',
            'provider': 'Unknown',
            'asn': 'ASUnknown',
            'is_working': False,
            'response_time': 0,
            'text': proxy_text
        }
        
        # --- فحص CONNECT 80 أولاً (الأسرع والأكثر كفاءة) ---
        try:
            start_time = time.time()
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((ip, port))
            connect_time = round((time.time() - start_time) * 1000, 2)
            
            if result == 0:
                results['connect'] = '✅'
                results['is_working'] = True
                results['response_time'] = connect_time
                # إذا نجح CONNECT، نعتبره شغال ونتخطى الباقي لتوفير الوقت
                provider, asn = get_asn_info(ip)
                results['provider'] = provider
                results['asn'] = asn
                sock.close()
                return results, None
            sock.close()
        except:
            pass
        
        # --- فحص HTTP (إذا لم ينجح CONNECT) ---
        try:
            start_time = time.time()
            proxy_dict = {'http': f"http://{ip}:{port}", 'https': f"https://{ip}:{port}"}
            response = requests.get(
                'http://httpbin.org/ip', 
                proxies=proxy_dict, 
                timeout=4,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            http_time = round((time.time() - start_time) * 1000, 2)
            
            if response.status_code == 200:
                results['http'] = '✅'
                results['is_working'] = True
                results['response_time'] = http_time
                # إذا نجح HTTP، نتخطى HTTPS لتوفير الوقت
                provider, asn = get_asn_info(ip)
                results['provider'] = provider
                results['asn'] = asn
                return results, None
        except:
            pass
        
        # --- فحص HTTPS (إذا لم ينجح HTTP) ---
        try:
            start_time = time.time()
            proxy_dict = {'https': f"https://{ip}:{port}", 'http': f"http://{ip}:{port}"}
            response = requests.get(
                'https://httpbin.org/ip',
                proxies=proxy_dict, 
                timeout=4,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'},
                verify=False
            )
            https_time = round((time.time() - start_time) * 1000, 2)
            
            if response.status_code == 200:
                results['https'] = '✅'
                results['is_working'] = True
                results['response_time'] = https_time
        except:
            pass
        
        # --- معلومات ASN والمزود (فقط إذا كان شغال) ---
        if results['is_working']:
            provider, asn = get_asn_info(ip)
            results['provider'] = provider
            results['asn'] = asn
            return results, None
        else:
            return None, None
            
    except Exception as e:
        return None, f"❌ خطأ في الفحص: {str(e)}"

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
            bot.edit_message_text(progress_text, chat_id, message_id)
            return message_id
        else:
            msg = bot.send_message(chat_id, progress_text)
            return msg.message_id
    except:
        return message_id

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
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        future_to_proxy = {executor.submit(check_single_proxy, proxy, user_id): proxy for proxy in proxies_list}
        
        for future in concurrent.futures.as_completed(future_to_proxy):
            if user_id in scanning_active and not scanning_active[user_id]:
                for f in future_to_proxy:
                    f.cancel()
                break
                
            proxy_data, error = future.result()
            checked += 1
            
            if proxy_data:
                working += 1
                working_proxies.append(proxy_data)
                if 'google' in proxy_data['provider'].lower():
                    google_proxies.append(proxy_data)
            
            # تحديث العداد كل ثانيتين أو عند انتهاء 10% من العمل
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
    welcome_text = """
🚀 أهلاً بك في بوت فحص البروكسيات المتقدم!

⚡ المميزات:
• فحص HTTP/HTTPS/CONNECT 80
• كشف بروكسيات Google النادرة 🚨
• فحص متعدد سريع
• عداد تقدم حي

📝 كيفية الاستخدام:
أرسل قائمة البروكسيات (واحد أو أكثر)
مثال:
34.41.115.197:3128
192.168.1.1:8080
    """
    bot.send_message(message.chat.id, welcome_text)

@bot.message_handler(commands=['stop'])
def stop_scan(message):
    """إيقاف الفحص"""
    user_id = message.from_user.id
    if user_id in scanning_active:
        scanning_active[user_id] = False
        bot.send_message(message.chat.id, "⏹️ تم إيقاف الفحص")

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    """معالجة جميع الرسائل تلقائياً"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    
    try:
        text = message.text.strip()
        
        # فصل البروكسيات
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
        
        bot.send_message(chat_id, f"🔍 بدء فحص {len(proxies_list)} بروكسي...")
        
        # فحص البروكسيات
        working_proxies, google_proxies = check_proxies_list(proxies_list, user_id, chat_id, bot)
        
        # إرسال النتائج
        if not working_proxies:
            bot.send_message(chat_id, "❌ لا توجد بروكسيات شغالة في القائمة")
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

• 📋 الإجمالي المفحوص: {len(proxies_list)}
• ✅ البروكسيات الشغالة: {len(working_proxies)}
• 🚨 بروكسيات Google: {len(google_proxies)}
• ⚡ نسبة النجاح: {(len(working_proxies)/len(proxies_list))*100:.1f}%

📋 البروكسيات الشغالة:
        """
        
        for i, proxy in enumerate(working_proxies, 1):
            google_flag = "🔴🚨" if 'google' in proxy['provider'].lower() else ""
            response_time = f"⚡ {proxy['response_time']}ms" if proxy['response_time'] > 0 else ""
            
            result_text += f"""
{i}. {proxy['ip']}:{proxy['port']} {google_flag}
   🏢 {proxy['provider']} {response_time}
   🌐 HTTP: {proxy['http']} | HTTPS: {proxy['https']} | CONNECT: {proxy['connect']}
            """
        
        # تقسيم الرسالة إذا كانت طويلة
        if len(result_text) > 4096:
            parts = [result_text[i:i+4096] for i in range(0, len(result_text), 4096)]
            for part in parts:
                bot.send_message(chat_id, part)
        else:
            bot.send_message(chat_id, result_text)
            
    except Exception as e:
        bot.send_message(chat_id, f"❌ حدث خطأ: {str(e)}")
    finally:
        if user_id in scanning_active:
            scanning_active[user_id] = False

if __name__ == "__main__":
    print("🟢 بدء تشغيل بوت فحص البروكسيات المتقدم...")
    print("⚡ المميزات: فحص HTTP/HTTPS/CONNECT، كشف Google، فحص متعدد")
    bot.infinity_polling()
