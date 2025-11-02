import telebot
import requests
import socket
import time
import threading
from datetime import datetime
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# توكن البوت - ضعيه هنا
bot = telebot.TeleBot("8420676859:AAGQ6ZgnTuUs648v_79hR_CEIw6VUqRE2B4")

# تخزين العمليات والنتائج
active_checks = {}
user_results = {}

def create_main_keyboard():
    """لوحة المفاتيح الرئيسية - زرين فقط"""
    keyboard = ReplyKeyboardMarkup(
        resize_keyboard=True,
        one_time_keyboard=False
    )
    
    btn_start = KeyboardButton("/start")
    btn_stop = KeyboardButton("/stop")
    
    keyboard.add(btn_start, btn_stop)
    
    return keyboard

def create_check_keyboard():
    """لوحة فحص بعد الضغط على /start"""
    keyboard = ReplyKeyboardMarkup(
        resize_keyboard=True,
        one_time_keyboard=False
    )
    
    btn_text = KeyboardButton("فحص نص")
    btn_url = KeyboardButton("فحص رابط")
    btn_back = KeyboardButton("/stop")
    
    keyboard.add(btn_text, btn_url)
    keyboard.add(btn_back)
    
    return keyboard

def get_detailed_ip_info(ip):
    """معلومات IP مفصلة مع مخاطر ASN"""
    try:
        response = requests.get(f"http://ip-api.com/json/{ip}?fields=66846719", timeout=5)
        data = response.json()
        
        if data['status'] == 'success':
            # تحليل مخاطر ASN
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
    """تحليل مستوى خطر ASN"""
    risk_factors = {
        'high_risk': ['Google', 'Amazon', 'Microsoft', 'Cloudflare', 'Facebook'],
        'medium_risk': ['OVH', 'DigitalOcean', 'Linode', 'Vultr', 'Hetzner'],
        'low_risk': ['ISP', 'Telecom', 'Communications', 'Network']
    }
    
    asn_lower = str(asn).lower()
    isp_lower = str(isp).lower()
    
    # كشف高风险
    for company in risk_factors['high_risk']:
        if company.lower() in asn_lower or company.lower() in isp_lower:
            return 'high'
    
    # كشف متوسط风险
    for company in risk_factors['medium_risk']:
        if company.lower() in asn_lower or company.lower() in isp_lower:
            return 'medium'
    
    return 'low'

def get_risk_emoji(risk_level):
    """إيموجي حسب مستوى الخطورة"""
    emojis = {
        'high': '🔴🚨',
        'medium': '🟡⚠️', 
        'low': '🟢✅'
    }
    return emojis.get(risk_level, '⚪❓')

def check_single_proxy(proxy_ip, proxy_port, chat_id):
    """فحص HTTP/HTTPS/CONNECT فقط"""
    try:
        proxy_dict = {
            'http': f"http://{proxy_ip}:{proxy_port}",
            'https': f"https://{proxy_ip}:{proxy_port}"
        }
        
        results = {
            'ip': proxy_ip,
            'port': proxy_port,
            'http': '❌',
            'https': '❌',
            'connect_80': False,
            'ip_info': None,
            'is_working': False
        }
        
        # فحص HTTP
        try:
            response = requests.get(
                'http://httpbin.org/ip', 
                proxies=proxy_dict, 
                timeout=3,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            if response.status_code == 200:
                results['http'] = '✅'
        except:
            pass
        
        # فحص HTTPS
        try:
            response = requests.get(
                'https://httpbin.org/ip',
                proxies=proxy_dict, 
                timeout=3,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
            )
            if response.status_code == 200:
                results['https'] = '✅'
        except:
            pass
        
        # فحص CONNECT 80
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(3)
            result = sock.connect_ex((proxy_ip, int(proxy_port)))
            results['connect_80'] = result == 0
            sock.close()
        except:
            results['connect_80'] = False
        
        # معلومات IP
        results['ip_info'] = get_detailed_ip_info(proxy_ip)
        
        # اعتبار البروكسي شغال إذا نجح في أي فحص
        working_checks = sum(1 for check in [results['http'], results['https']] if check == '✅')
        results['is_working'] = (working_checks >= 1) or results['connect_80']
        
        return results
        
    except Exception as e:
        print(f"Error checking proxy: {e}")
        return None

@bot.message_handler(commands=['start'])
def start_command(message):
    """عند الضغط على /start"""
    welcome_text = """
🎯 **بوت فحص البروكسيات المتقدم** 🛡️

⚡ **المميزات:**
• فحص HTTP/HTTPS/CONNECT
• كشف مزودي الخدمة (Google, Amazon)
• تحليل مخاطر متقدم
• سرعة فحص عالية

🎮 **اختر نوع الفحص:**
    """
    
    bot.send_message(
        message.chat.id,
        welcome_text,
        reply_markup=create_check_keyboard()
    )

@bot.message_handler(commands=['stop'])
def stop_command(message):
    """عند الضغط على /stop - يتوقف ويعرض النتائج"""
    chat_id = message.chat.id
    
    # إيقاف أي عملية جارية
    if chat_id in active_checks:
        active_checks[chat_id] = False
    
    # عرض النتائج إذا كانت موجودة
    if chat_id in user_results and user_results[chat_id]:
        results = user_results[chat_id]
        show_final_results(chat_id, results)
    else:
        bot.send_message(
            chat_id,
            "🛑 تم إيقاف البحث\n❌ لا توجد نتائج لعرضها",
            reply_markup=create_main_keyboard()
        )

def show_final_results(chat_id, working_proxies):
    """عرض نتائج مفصلة"""
    truly_working = [p for p in working_proxies if p.get('is_working', False)]
    
    if not truly_working:
        bot.send_message(chat_id, "❌ لم أعثر على أي بروكسيات شغالة")
        return
    
    results_text = f"📊 **نتائج الفحص المتقدم**\n\n"
    results_text += f"✅ **تم العثور على {len(truly_working)} بروكسي شغال**\n\n"
    
    for i, proxy in enumerate(truly_working[:15], 1):
        results_text += f"**{i}. {proxy['ip']}:{proxy['port']}**\n"
        
        # معلومات IP والمخاطر
        if proxy['ip_info']:
            info = proxy['ip_info']
            results_text += f"   🏢 **ISP:** {info['isp']}\n"
            results_text += f"   🆔 **ASN:** {info['asn']} {info['risk_emoji']}\n"
            results_text += f"   📍 **الموقع:** {info['city']}, {info['country']}\n"
        
        # نتائج الفحص
        results_text += f"   🌐 **HTTP:** {proxy['http']}\n"
        results_text += f"   🔒 **HTTPS:** {proxy['https']}\n"
        results_text += f"   🔌 **CONNECT 80:** {'✅' if proxy['connect_80'] else '❌'}\n"
        results_text += "─" * 40 + "\n\n"
    
    # إحصائيات عامة
    if len(truly_working) > 0:
        http_count = sum(1 for p in truly_working if p['http'] == '✅')
        https_count = sum(1 for p in truly_working if p['https'] == '✅')
        connect_count = sum(1 for p in truly_working if p['connect_80'])
        
        results_text += f"📈 **إحصائيات عامة:**\n"
        results_text += f"   • بروكسيات تدعم HTTP: **{http_count}**\n"
        results_text += f"   • بروكسيات تدعم HTTPS: **{https_count}**\n"
        results_text += f"   • بروكسيات تدعم CONNECT: **{connect_count}**\n"
    
    if len(truly_working) > 15:
        results_text += f"\n📁 **و {len(truly_working) - 15} بروكسي إضافي...**"
    
    results_text += "\n🛑 **تم إيقاف البحث بناءً على طلبك**"
    
    bot.send_message(
        chat_id,
        results_text,
        reply_markup=create_main_keyboard(),
        parse_mode='Markdown'
    )
    
    # مسح النتائج بعد العرض
    if chat_id in user_results:
        del user_results[chat_id]

@bot.message_handler(func=lambda message: message.text == "فحص نص")
def check_text_handler(message):
    """عند الضغط على فحص نص"""
    msg = bot.send_message(
        message.chat.id, 
        "📝 أرسلي IP:Port أو قائمة بروكسيات\n\n**مثال:**\n`192.168.1.1:8080`\n`192.168.1.2:8080`\n`194.56.78.90:3128`",
        reply_markup=create_check_keyboard(),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(msg, process_text_check)

@bot.message_handler(func=lambda message: message.text == "فحص رابط")
def check_url_handler(message):
    """عند الضغط على فحص رابط"""
    msg = bot.send_message(
        message.chat.id,
        "🔗 أرسلي رابط ملف البروكسيات\n\n**مثال:**\n`https://example.com/proxies.txt`\n`http://site.com/proxy-list.txt`",
        reply_markup=create_check_keyboard(),
        parse_mode='Markdown'
    )
    bot.register_next_step_handler(msg, process_url_check)

def process_text_check(message):
    """معالجة فحص النص مع حفظ النتائج"""
    chat_id = message.chat.id
    active_checks[chat_id] = True
    user_results[chat_id] = []
    
    # تحليل النص المدخل
    proxies = []
    for line in message.text.split('\n'):
        line = line.strip()
        if ':' in line:
            parts = line.split(':')
            if len(parts) >= 2:
                ip = parts[0].strip()
                port = parts[1].strip()
                port = ''.join(filter(str.isdigit, port))
                if port:
                    proxies.append((ip, port))
    
    if not proxies:
        bot.send_message(chat_id, "❌ لم أجد أي بروكسيات صالحة في النص")
        return
    
    if len(proxies) > 50:
        bot.send_message(chat_id, f"⚠️ سيتم فحص أول 50 بروكسي من أصل {len(proxies)}")
        proxies = proxies[:50]
    
    progress_msg = bot.send_message(chat_id, f"🔍 بدء فحص {len(proxies)} بروكسي...\n⚡ جاري الفحص المتقدم")
    
    # فحص جميع البروكسيات
    working_proxies = []
    checked_count = 0
    
    for ip, port in proxies:
        if not active_checks.get(chat_id, True):
            break
        
        checked_count += 1
        if checked_count % 5 == 0:
            try:
                bot.edit_message_text(
                    f"🔍 جاري الفحص... {checked_count}/{len(proxies)}\n✅ وجدنا {len(working_proxies)} بروكسي شغال",
                    chat_id,
                    progress_msg.message_id
                )
            except:
                pass
        
        result = check_single_proxy(ip, port, chat_id)
        if result and result['is_working']:
            working_proxies.append(result)
            user_results[chat_id] = working_proxies
        
        time.sleep(0.5)
    
    # إذا لم يتم إيقاف البحث، عرض النتائج تلقائياً
    if active_checks.get(chat_id, True):
        show_final_results(chat_id, working_proxies)
        active_checks[chat_id] = False
    else:
        bot.send_message(
            chat_id,
            f"🛑 تم إيقاف البحث\n✅ تم فحص {checked_count} بروكسي - وجدنا {len(working_proxies)} شغال",
            reply_markup=create_main_keyboard()
        )

def process_url_check(message):
    """معالجة فحص الرابط مع حفظ النتائج"""
    chat_id = message.chat.id
    active_checks[chat_id] = True
    user_results[chat_id] = []
    
    try:
        bot.send_message(chat_id, "⏬ جاري تحميل البروكسيات من الرابط...")
        
        response = requests.get(message.text, timeout=10)
        content = response.text
        
        proxies = []
        for line in content.split('\n'):
            line = line.strip()
            if ':' in line and '.' in line:
                parts = line.split(':')
                if len(parts) >= 2:
                    ip = parts[0].strip()
                    port = parts[1].strip()
                    port = ''.join(filter(str.isdigit, port))
                    if port and ip.replace('.', '').isdigit():
                        proxies.append((ip, port))
        
        if not proxies:
            bot.send_message(chat_id, "❌ لم أجد أي بروكسيات في الرابط")
            return
        
        if len(proxies) > 50:
            bot.send_message(chat_id, f"⚠️ سيتم فحص أول 50 بروكسي من أصل {len(proxies)}")
            proxies = proxies[:50]
        
        progress_msg = bot.send_message(chat_id, f"🔍 بدء فحص {len(proxies)} بروكسي...\n⚡ جاري الفحص المتقدم")
        
        working_proxies = []
        checked_count = 0
        
        for ip, port in proxies:
            if not active_checks.get(chat_id, True):
                break
            
            checked_count += 1
            if checked_count % 5 == 0:
                try:
                    bot.edit_message_text(
                        f"🔍 جاري الفحص... {checked_count}/{len(proxies)}\n✅ وجدنا {len(working_proxies)} بروكسي شغال",
                        chat_id,
                        progress_msg.message_id
                    )
                except:
                    pass
            
            result = check_single_proxy(ip, port, chat_id)
            if result and result['is_working']:
                working_proxies.append(result)
                user_results[chat_id] = working_proxies
            
            time.sleep(0.5)
        
        # إذا لم يتم إيقاف البحث، عرض النتائج تلقائياً
        if active_checks.get(chat_id, True):
            show_final_results(chat_id, working_proxies)
            active_checks[chat_id] = False
        else:
            bot.send_message(
                chat_id,
                f"🛑 تم إيقاف البحث\n✅ تم فحص {checked_count} بروكسي - وجدنا {len(working_proxies)} شغال",
                reply_markup=create_main_keyboard()
            )
        
    except Exception as e:
        bot.send_message(chat_id, f"❌ خطأ في تحميل الرابط: {str(e)}")

# تشغيل البوت
if __name__ == "__main__":
    print("🟢 بدء تشغيل بوت فحص البروكسيات المتقدم...")
    print("⚡ المميزات: فحص HTTP/HTTPS/CONNECT، كشف ASN، تحليل مخاطر")
    print("🎯 البوت جاهز لاستقبال الطلبات...")
    bot.infinity_polling()
