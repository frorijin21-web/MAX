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

def get_detailed_ip_info(ip):
    """
    الحصول على معلومات مفصلة عن الـ IP باستخدام ipapi.co
    """
    try:
        response = requests.get(f"http://ipapi.co/{ip}/json/", timeout=5)
        data = response.json()
        
        # استخراج المعلومات الأساسية
        country = data.get('country_name', 'Unknown')
        region = data.get('region', 'Unknown')
        city = data.get('city', 'Unknown')
        asn = data.get('asn', '')
        isp = data.get('org', data.get('asn', 'Unknown'))
        
        # تنظيف وتنسيق بيانات ASN
        asn_clean = f"AS{asn}" if asn else "ASUnknown"
        
        return {
            'country': country,
            'region': region, 
            'city': city,
            'asn': asn_clean,
            'isp': isp,
            'raw_data': data
        }
        
    except Exception as e:
        print(f"Error fetching IP info for {ip}: {e}")
        return {
            'country': 'Unknown',
            'region': 'Unknown',
            'city': 'Unknown', 
            'asn': 'ASUnknown',
            'isp': 'Unknown'
        }

def analyze_asn_risk(asn, isp):
    """تحليل مستوى خطر ASN"""
    risk_factors = {
        'high_risk': ['Google', 'Amazon', 'Microsoft', 'Cloudflare', 'Facebook'],
        'medium_risk': ['OVH', 'DigitalOcean', 'Linode', 'Vultr', 'Hetzner'],
        'low_risk': ['ISP', 'Telecom', 'Communications', 'Network']
    }
    
    asn_lower = str(asn).lower()
    isp_lower = str(isp).lower()
    
    # كشف عالي الخطورة
    for company in risk_factors['high_risk']:
        if company.lower() in asn_lower or company.lower() in isp_lower:
            return 'high'
    
    # كشف متوسط الخطورة
    for company in risk_factors['medium_risk']:
        if company.lower() in asn_lower or company.lower() in isp_lower:
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

def check_single_proxy(proxy_text, user_id):
    """فحص بروكسي واحد مع معلومات مفصلة"""
    if user_id in scanning_active and not scanning_active[user_id]:
        return None, "⏹️ تم إيقاف الفحص"
    
    ip, port = extract_ip_port(proxy_text)
    if not ip or not port:
        return None, "❌ تنسيق غير صحيح"
    
    try:
        # الحصول على المعلومات المفصلة أولاً
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
            'text': proxy_text,
            # المعلومات المفصلة
            'country': ip_info['country'],
            'region': ip_info['region'],
            'city': ip_info['city'],
            'asn': ip_info['asn'],
            'isp': ip_info['isp'],
            'risk_level': risk_level,
            'risk_icon': risk_icon,
            'is_google': 'Google' in ip_info['isp'] or 'AS396982' in ip_info['asn']
        }
        
        # --- فحص CONNECT 80 أولاً ---
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
                sock.close()
                return results, None
            sock.close()
        except:
            pass
        
        # --- فحص HTTP ---
        try:
            start_time = time.time()
            proxy_dict = {'http': f"http://{ip}:{port}"}
            response = requests.get(
                'http://httpbin.org/ip', 
                proxies=proxy_dict, 
                timeout=4
            )
            http_time = round((time.time() - start_time) * 1000, 2)
            
            if response.status_code == 200:
                results['http'] = '✅'
                results['is_working'] = True
                results['response_time'] = http_time
                return results, None
        except:
            pass
        
        # --- فحص HTTPS ---
        try:
            start_time = time.time()
            proxy_dict = {'https': f"https://{ip}:{port}"}
            response = requests.get(
                'https://httpbin.org/ip',
                proxies=proxy_dict, 
                timeout=4,
                verify=False
            )
            https_time = round((time.time() - start_time) * 1000, 2)
            
            if response.status_code == 200:
                results['https'] = '✅'
                results['is_working'] = True
                results['response_time'] = https_time
        except:
            pass
        
        return results if results['is_working'] else None, None
            
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
                if proxy_data['is_google']:
                    google_proxies.append(proxy_data)
            
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
🚀 أهلاً بك في بوت فحص البروكسيات الذكي!

⚡ المميزات الجديدة:
• تحليل مفصل لكل بروكسي (البلد، المنطقة، ASN، ISP)
• كشف بروكسيات Google النادرة 🚨
• تحليل مستوى الخطر (🔴🚨 عالي، 🟡⚠️ متوسط، ⚪ منخفض)
• فحص HTTP/HTTPS/CONNECT 80

📝 أرسل قائمة البروكسيات للبدء...
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
        bot.send_message(chat_id, f"🔍 بدء فحص {len(proxies_list)} بروكسي...")
        
        working_proxies, google_proxies = check_proxies_list(proxies_list, user_id, chat_id, bot)
        
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
   🏢 {proxy['isp']}
   🆔 {proxy['asn']} 🔴🚨
   🌍 {proxy['country']} | {proxy['region']}
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
            google_flag = "🔴🚨" if proxy['is_google'] else proxy['risk_icon']
            
            result_text += f"""
{i}. **IP:** {proxy['ip']}:{proxy['port']}
   🌍 **البلد:** {proxy['country']}
   🏞️ **المنطقة:** {proxy['region']}
   🏙️ **المدينة:** {proxy['city']}
   🆔 **ASN:** {proxy['asn']} {google_flag}
   📡 **ISP:** {proxy['isp']}
   ⚡ **الاستجابة:** {proxy['response_time']}ms
   🌐 **البروتوكولات:** HTTP: {proxy['http']} | HTTPS: {proxy['https']} | CONNECT: {proxy['connect']}
            """
        
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
    print("🟢 بدء تشغيل بوت فحص البروكسيات الذكي...")
    print("⚡ المميزات: تحليل مفصل، كشف Google، تحليل خطر")
    bot.infinity_polling()
