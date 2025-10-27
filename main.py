import telebot
import requests
import socket
from concurrent.futures import ThreadPoolExecutor
import threading
import time
import json
import random
import re
import asyncio
import logging

# ---------- إعدادات السكريبت ----------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ssh_bot")

# إعدادات SSH
SSH_API_URL = "https://painel.meowssh.shop:5000/test_ssh_public"
SSH_PAYLOAD = {"store_owner_id": 1}
SSH_HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}

# إعدادات البوت (استبدل التوكن بالتوكن الحقيقي عند الحاجة)
TOKEN = '8420676859:AAGQ6ZgnTuUs648v_79hR_CEIw6VUqRE2B4'
bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

criticalASN = 'AS396982'
defaultPorts = [80, 443, 8080, 8443, 3128]
MAX_FAST_PORTS = 20
MAX_DISPLAY_OPEN = 20
MAX_IPS_PER_MSG = 300
MAX_FILE_IPS = 1000
HTTP_TIMEOUT = 2
SCAN_CONCURRENCY = 200
TOTAL_PORTS = 65535
UPDATE_INTERVAL = 3

# مصادر البروكسيات التلقائية
PROXY_SOURCES = [
    "https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
    "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
    "https://raw.githubusercontent.com/jetkai/proxy-list/main/online-proxies/txt/proxies-http.txt"
]

# إدارة العمليات
waitingFull = set()
file_upload_mode = set()
user_operations = {}
waiting_proxy_url = set()

# ---------------- دوال مساعدة ----------------
def validate_ip(ip):
    try:
        parts = ip.split('.')
        if len(parts) != 4:
            return False
        for part in parts:
            p = int(part)
            if not 0 <= p <= 255:
                return False
        return True
    except:
        return False

def create_progress_bar(percentage, length=20):
    filled = int(length * percentage / 100)
    empty = length - filled
    bar = "█" * filled + "░" * empty
    return f"[{bar}]"

def start_operation(chat_id, operation_type):
    user_operations[chat_id] = {'stop': False, 'type': operation_type}

def end_operation(chat_id):
    if chat_id in user_operations:
        del user_operations[chat_id]

def stop_user_operations(chat_id):
    if chat_id in user_operations:
        user_operations[chat_id]['stop'] = True
    file_upload_mode.discard(chat_id)
    waitingFull.discard(chat_id)
    waiting_proxy_url.discard(chat_id)

def should_stop(chat_id):
    if chat_id in user_operations:
        return user_operations[chat_id].get('stop', False)
    return False

# ---------------- دوال شبكات / API ----------------
def fetch_proxies_from_url(url):
    """جلب البروكسيات من رابط معين (مزامن — يُنادى عادة من Thread)"""
    try:
        r = requests.get(url, timeout=10)
        if r.status_code == 200:
            proxies = []
            lines = r.text.splitlines()
            for line in lines:
                line = line.strip()
                if ':' in line and '.' in line:
                    parts = line.split(':')
                    if len(parts) >= 2:
                        ip = parts[0].strip()
                        port = parts[1].strip()
                        if validate_ip(ip) and port.isdigit() and 1 <= int(port) <= 65535:
                            proxies.append(f"{ip}:{port}")
            return list(set(proxies))
    except Exception as e:
        logger.warning("fetch_proxies_from_url error for %s: %s", url, e)
    return []

def query_ip_api(ip):
    """استعلام عن معلومات IP (مزامن — يُنادى عادة من Thread)"""
    try:
        r = requests.get(
            f'http://ip-api.com/json/{ip}?fields=status,message,query,country,regionName,isp,as,org',
            timeout=5
        )
        return r.json()
    except Exception as e:
        logger.debug("query_ip_api error for %s: %s", ip, e)
        return None

def check_connect_proxy(proxy_host, proxy_port, target_host="www.google.com", target_port=443):
    """فحص بروتوكول CONNECT للبروكسي"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(HTTP_TIMEOUT)
        sock.connect((proxy_host, proxy_port))
        
        # إرسال طلب CONNECT
        connect_msg = f"CONNECT {target_host}:{target_port} HTTP/1.1\r\nHost: {target_host}\r\n\r\n"
        sock.send(connect_msg.encode())
        
        response = sock.recv(4096).decode()
        sock.close()
        
        if "200" in response or "Connection established" in response:
            return True
        else:
            return False
            
    except Exception as e:
        return False

def check_port_http(ip, port):
    """فحص HTTP/HTTPS/CONNECT (مزامن)"""
    # الفحص العادي HTTP/HTTPS
    try:
        protocol = 'https' if port in [443, 8443] else 'http'
        r = requests.get(f'{protocol}://{ip}:{port}', timeout=HTTP_TIMEOUT)
        if r.status_code < 400:
            return True
    except:
        pass
    
    # فحص CONNECT 80
    try:
        if port == 80:
            if check_connect_proxy(ip, port):
                return True
    except:
        pass
    
    return False

def check_port_tcp(ip, port, timeout=1):
    """فحص TCP (مزامن)"""
    try:
        sock = socket.create_connection((ip, port), timeout=timeout)
        sock.close()
        return True
    except:
        return False

# ---------------- جلب وتصفيّة بروكسيات Google ----------------
def filter_google_proxies_with_progress(chat_id, progress_msg, proxies):
    google_proxies = []
    total_proxies = len(proxies)

    def check_proxy(proxy):
        try:
            ip = proxy.split(':')[0]
            ip_data = query_ip_api(ip)
            if ip_data and ip_data.get('status') == 'success':
                as_raw = ip_data.get('as', '')
                if criticalASN in as_raw or 'Google' in as_raw:
                    return proxy
        except:
            pass
        return None

    for i in range(0, total_proxies, 20):
        if should_stop(chat_id):
            return google_proxies
        batch = proxies[i:i+20]
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(check_proxy, batch))
        google_proxies.extend([p for p in results if p is not None])
        percentage = ((i + len(batch)) / total_proxies) * 100
        try:
            bot.edit_message_text(
                f"🔍 جاري تصفية بروكسيات Google فقط...\n📊 تم فحص: {i + len(batch)}/{total_proxies}\n🟢 وجدت: {len(google_proxies)} بروكسي\n📈 التقدم: {percentage:.1f}%",
                chat_id, progress_msg.message_id
            )
        except:
            pass
        time.sleep(0.5)
    return google_proxies

def fetch_and_filter_google_proxies(chat_id, custom_url=None):
    """جلب وتصفية بروكسيات Google مع التقدّم"""
    try:
        progress_msg = bot.send_message(chat_id, "🔍 جاري البحث عن بروكسيات Google...\n📊 التقدم: 0%")
        all_proxies = []
        urls_to_check = [custom_url] if custom_url else PROXY_SOURCES
        total_urls = len(urls_to_check)
        for index, url in enumerate(urls_to_check):
            if should_stop(chat_id):
                try:
                    bot.edit_message_text("⏹️ تم إيقاف البحث عن البروكسيات", chat_id, progress_msg.message_id)
                except:
                    pass
                return []
            percentage = (index / total_urls) * 100
            try:
                bot.edit_message_text(
                    f"🔍 جاري البحث عن بروكسيات Google...\n📥 جاري من: {url[:50]}...\n📊 التقدم: {percentage:.1f}%",
                    chat_id, progress_msg.message_id
                )
            except:
                pass
            proxies = fetch_proxies_from_url(url)
            all_proxies.extend(proxies)
            time.sleep(1)
        if not all_proxies:
            try:
                bot.edit_message_text("❌ لم يتم العثور على بروكسيات في المصادر المحددة", chat_id, progress_msg.message_id)
            except:
                pass
            return []
        try:
            bot.edit_message_text("🔍 جاري تصفية بروكسيات Google فقط...\n📊 تم فحص: 0/0", chat_id, progress_msg.message_id)
        except:
            pass
        google_proxies = filter_google_proxies_with_progress(chat_id, progress_msg, all_proxies)
        if not google_proxies:
            try:
                bot.edit_message_text("❌ لم يتم العثور على بروكسيات تابعة لـ Google", chat_id, progress_msg.message_id)
            except:
                pass
            return []
        # تحضير النص للعرض
        proxy_text = "🌐 **بروكسيات Google التي تم العثور عليها:**\n\n```\n"
        for proxy in google_proxies[:50]:
            proxy_text += proxy + "\n"
        proxy_text += "```"
        if len(google_proxies) > 50:
            proxy_text += f"\n📊 ... وإجمالي {len(google_proxies)} بروكسي Google"
        try:
            bot.delete_message(chat_id, progress_msg.message_id)
        except:
            pass
        bot.send_message(chat_id, proxy_text)
        return google_proxies
    except Exception as e:
        bot.send_message(chat_id, f"❌ خطأ في جلب البروكسيات: {str(e)}")
        return []

def process_google_proxies_scan(chat_id, custom_url=None):
    """معالجة فحص بروكسيات Google مع دعم الإيقاف"""
    start_operation(chat_id, 'google_proxies_scan')
    try:
        google_proxies = fetch_and_filter_google_proxies(chat_id, custom_url)
        if not google_proxies:
            end_operation(chat_id)
            return
        ip_list = []
        for proxy in google_proxies:
            parts = proxy.split(':')
            if len(parts) >= 2:
                ip = parts[0]
                port = parts[1]
                if validate_ip(ip):
                    ip_list.append({'ip': ip, 'ports': [int(port)]})
        if not ip_list:
            bot.send_message(chat_id, "❌ لا توجد بروكسيات صالحة للفحص")
            end_operation(chat_id)
            return
        bot.send_message(chat_id, f"🚀 بدء الفحص التلقائي لـ {len(ip_list)} بروكسي Google...")
        active_count = 0
        scanned_count = 0
        progress_msg = bot.send_message(
            chat_id,
            f"🔍 **جاري فحص بروكسيات Google**\n\n📊 تم فحص: 0/{len(ip_list)}\n🟢 النشطة: 0\n⏳ الباقي: {len(ip_list)}\n📈 النسبة: 0%\n[░░░░░░░░░░░░░░░░░░░░]"
        )
        for i, item in enumerate(ip_list):
            if should_stop(chat_id):
                break
            ip, ports = item['ip'], item['ports']
            is_active = perform_quick_scan(chat_id, ip, ports, "Google", show_failures=False)
            scanned_count = i + 1
            if is_active:
                active_count += 1
            if scanned_count % 5 == 0 or scanned_count == len(ip_list):
                percentage = (scanned_count / len(ip_list)) * 100
                remaining = len(ip_list) - scanned_count
                progress_bar = create_progress_bar(percentage, 20)
                try:
                    bot.edit_message_text(
                        f"🔍 **جاري فحص بروكسيات Google**\n\n📊 تم فحص: {scanned_count}/{len(ip_list)}\n🟢 النشطة: {active_count}\n⏳ الباقي: {remaining}\n📈 النسبة: {percentage:.1f}%\n{progress_bar}",
                        chat_id, progress_msg.message_id
                    )
                except:
                    pass
        try:
            bot.delete_message(chat_id, progress_msg.message_id)
        except:
            pass
        # ملخص نهائي
        summary = (
            f"✅ **تم الانتهاء من فحص بروكسيات Google**\n\n"
            f"📊 **النتائج النهائية:**\n"
            f"• 🔢 الإجمالي: {len(ip_list)} بروكسي\n"
            f"• 🟢 النشطة: {active_count}\n"
            f"• 📈 نسبة النجاح: {(active_count/len(ip_list))*100:.1f}%\n\n"
            f"🌐 **ASN: {criticalASN} - Google**"
        )
        bot.send_message(chat_id, summary)
    except Exception as e:
        bot.send_message(chat_id, f"❌ خطأ في فحص بروكسيات Google: {str(e)}")
    finally:
        end_operation(chat_id)

# ---------------- دوال SSH ----------------
def get_ssh_account_sync():
    """استدعاء API جلب SSH (مزامن — يُنادى عادة من Thread)"""
    try:
        r = requests.post(SSH_API_URL, json=SSH_PAYLOAD, headers=SSH_HEADERS, timeout=10)
        if r.status_code in [200, 201]:
            data = r.json()
            usuario = data.get("Usuario")
            senha = data.get("Senha")
            return f"👤 <b>Usuario:</b> <code>{usuario}</code>\n🔑 <b>Senha:</b> <code>{senha}</code>"
        else:
            return f"❌ خطأ {r.status_code}"
    except Exception as e:
        return f"🚨 خطأ بالاتصال:\n{str(e)}"

def show_ssh_menu(chat_id):
    ssh_message = """
🔷 **SSH Account Generator**

🚀 **مولد حسابات SSH مجانية**

📝 **الأوامر المتاحة:**
• /ssh - لاستخراج حساب SSH جديد

⚡ **انقر على الزر أدناه لاستخراج حساب SSH:**
"""
    inline_kb = telebot.types.InlineKeyboardMarkup()
    inline_kb.row(telebot.types.InlineKeyboardButton("🔑 استخراج SSH", callback_data='ssh_generate'))
    inline_kb.row(telebot.types.InlineKeyboardButton("🔙 رجوع", callback_data='back_main'))
    bot.send_message(chat_id, ssh_message, reply_markup=inline_kb)

def handle_ssh_generate(chat_id):
    """تشغيل استدعاء SSH في Thread لتجنب تعليق البوت"""
    def job():
        bot.send_message(chat_id, "🔑 جاري استخراج حساب SSH...")
        result = get_ssh_account_sync()
        bot.send_message(chat_id, result)
        inline_kb = telebot.types.InlineKeyboardMarkup()
        inline_kb.row(telebot.types.InlineKeyboardButton("🔑 استخراج آخر", callback_data='ssh_generate'))
        inline_kb.row(telebot.types.InlineKeyboardButton("🔙 رجوع للقائمة", callback_data='back_main'))
        bot.send_message(chat_id, "🔄 اختر الإجراء التالي:", reply_markup=inline_kb)
    threading.Thread(target=job, daemon=True).start()

# ---------------- الفحص السريع والمحسّن ----------------
def perform_quick_scan(chat_id, ip, ports=None, scan_type="سريع", show_failures=False):
    if ports is None:
        ports = defaultPorts.copy()
    try:
        ip_data = query_ip_api(ip)
        if not ip_data or ip_data.get('status') != 'success':
            return False
        as_raw = ip_data.get('as', 'N/A')
        as_code = as_raw.split()[0] if 'AS' in as_raw else 'N/A'
        is_critical = as_code == criticalASN
        results = []
        is_active = False
        for port in ports:
            if should_stop(chat_id):
                break
            port_status = check_port_http(ip, port)
            if port_status:
                results.append(f'Port {port}: ✅ مفتوح')
                is_active = True
            elif show_failures:
                results.append(f'Port {port}: ❌ مغلق/timeout')
        if not is_active and not show_failures:
            return False
        as_badge = '🔴🚨' if is_critical else '⚪'
        as_line = f'ASN: {as_raw} {as_badge}'
        text_out = (
            f'IP: {ip_data.get("query")}\n'
            f'Country: {ip_data.get("country")}\n'
            f'Region: {ip_data.get("regionName")}\n'
            f'{as_line}\n'
            f'ISP: {ip_data.get("isp", "N/A")}\n\n' + '\n'.join(results)
        )
        bot.send_message(chat_id, text_out)
        if is_critical:
            bot.send_message(chat_id, f'🚨🚨 تنبيه عاجل! وجد بروكسي ضمن ASN المهم جداً {criticalASN} — IP: {ip_data.get("query")}')
        return is_active
    except Exception as e:
        logger.debug("perform_quick_scan error: %s", e)
        return False

# ---------------- الفحص الشامل ----------------
def perform_full_scan(chat_id, ip):
    start_operation(chat_id, 'full_scan')
    try:
        status_msg = bot.send_message(chat_id, f'🔍 بدء الفحص الشامل TCP على {ip}...\n⏳ الرجاء الانتظار — الفحص جاري الآن.')
        open_ports = []
        scanned_ports = 0
        start_time = time.time()
        stop_requested = False

        def updater():
            last_update = time.time()
            while scanned_ports < TOTAL_PORTS and not should_stop(chat_id):
                current_time = time.time()
                if current_time - last_update >= UPDATE_INTERVAL:
                    remaining = TOTAL_PORTS - scanned_ports
                    preview = ', '.join(map(str, sorted(open_ports)[:MAX_DISPLAY_OPEN]))
                    more = f', ...(+{len(open_ports)-MAX_DISPLAY_OPEN})' if len(open_ports) > MAX_DISPLAY_OPEN else ''
                    txt = (
                        f'🔎 الفحص الشامل TCP على {ip}\n'
                        f'Scanned: {scanned_ports}/{TOTAL_PORTS}\n'
                        f'Remaining: {remaining}\n'
                        f'Open ports: {len(open_ports)}\n'
                    )
                    if open_ports:
                        txt += f'Some open: {preview}{more}'
                    else:
                        txt += 'No open ports found so far.'
                    try:
                        bot.edit_message_text(txt, chat_id, status_msg.message_id)
                    except:
                        pass
                    last_update = current_time
                time.sleep(1)

        threading.Thread(target=updater, daemon=True).start()

        def scan_port(p):
            nonlocal scanned_ports
            if not should_stop(chat_id) and check_port_tcp(ip, p, timeout=0.5):
                open_ports.append(p)
            scanned_ports += 1

        with ThreadPoolExecutor(max_workers=SCAN_CONCURRENCY) as executor:
            batch_size = 2000
            for start in range(1, TOTAL_PORTS + 1, batch_size):
                if should_stop(chat_id):
                    stop_requested = True
                    break
                end = min(start + batch_size - 1, TOTAL_PORTS)
                list(executor.map(scan_port, range(start, end + 1)))

        open_ports.sort()
        total_time = time.time() - start_time

        if stop_requested:
            final = (
                f'⏹️ **تم إيقاف الفحص الشامل**\n\n'
                f'📊 **النتائج حتى الآن:**\n'
                f'⏱️ الوقت: {total_time:.2f} ثانية\n'
                f'Scanned: {scanned_ports}/{TOTAL_PORTS}\n'
                f'Open ports: {len(open_ports)}\n'
            )
        else:
            final = (
                f'✅ **انتهى الفحص الشامل TCP** على {ip}\n\n'
                f'⏱️ الوقت: {total_time:.2f} ثانية\n'
                f'Scanned: {scanned_ports}/{TOTAL_PORTS}\n'
                f'Open ports: {len(open_ports)}\n'
            )

        if open_ports:
            final += ', '.join(map(str, open_ports[:MAX_DISPLAY_OPEN]))
            if len(open_ports) > MAX_DISPLAY_OPEN:
                final += f', ...(+{len(open_ports)-MAX_DISPLAY_OPEN})'
        else:
            final += '(لا توجد منافذ مفتوحة)'

        try:
            bot.edit_message_text(final, chat_id, status_msg.message_id)
        except:
            bot.send_message(chat_id, final)

    except Exception as e:
        bot.send_message(chat_id, f'❌ خطأ في الفحص الشامل: {str(e)}')
    finally:
        end_operation(chat_id)

# ---------------- معالجة الملفات ----------------
def parse_file_content(file_content):
    try:
        lines = file_content.decode('utf-8').split('\n')
    except:
        lines = file_content.decode('latin-1').split('\n')
    ips = []
    for line in lines:
        if len(ips) >= MAX_FILE_IPS:
            break
        line = line.strip()
        if not line:
            continue
        if ':' in line:
            parts = line.split(':')
            ip = parts[0].strip()
            if validate_ip(ip):
                try:
                    port = int(parts[1].strip())
                    if 1 <= port <= 65535:
                        ips.append({'ip': ip, 'ports': [port]})
                except:
                    ips.append({'ip': ip, 'ports': defaultPorts.copy()})
        else:
            if validate_ip(line):
                ips.append({'ip': line, 'ports': defaultPorts.copy()})
    return ips

def process_file_scan(chat_id, file_content):
    start_operation(chat_id, 'file_scan')
    try:
        ips_to_scan = parse_file_content(file_content)
        if not ips_to_scan:
            bot.send_message(chat_id, "❌ لم يتم العثور على IPs صحيحة في الملف.")
            end_operation(chat_id)
            return
        total_ips = len(ips_to_scan)
        progress_msg = bot.send_message(
            chat_id,
            f"📁 **بدء فحص الملف**\n\n🔢 إجمالي الـIPs: {total_ips}\n📊 تم فحص: 0/{total_ips}\n🟢 النشطة: 0\n⏳ الباقي: {total_ips}\n📈 النسبة: 0%\n[░░░░░░░░░░░░░░░░░░░░]"
        )
        scanned_count = 0
        active_count = 0
        last_update_time = time.time()
        for i, item in enumerate(ips_to_scan):
            if should_stop(chat_id):
                ip, ports = item['ip'], item['ports']
                is_active = perform_quick_scan(chat_id, ip, ports, f"ملف", show_failures=False)
                scanned_count = i + 1
                if is_active:
                    active_count += 1
                try:
                    bot.delete_message(chat_id, progress_msg.message_id)
                except:
                    pass
                success_rate = (active_count / scanned_count * 100) if scanned_count > 0 else 0
                summary = f"""
⏹️ **تم إيقاف فحص الملف**

📊 **النتائج حتى الآن:**
• 🔢 تم فحص: {scanned_count}/{total_ips}
• 🟢 النشطة: {active_count}
• 📈 نسبة النجاح: {success_rate:.1f}%

💡 **ملاحظة:** تم عرض النتائج النشطة فقط
"""
                bot.send_message(chat_id, summary)
                end_operation(chat_id)
                return
            ip, ports = item['ip'], item['ports']
            is_active = perform_quick_scan(chat_id, ip, ports, f"ملف", show_failures=False)
            scanned_count = i + 1
            if is_active:
                active_count += 1
            current_time = time.time()
            if current_time - last_update_time >= 2 or scanned_count == total_ips:
                percentage = (scanned_count / total_ips) * 100
                remaining = total_ips - scanned_count
                progress_bar = create_progress_bar(percentage, 20)
                try:
                    bot.edit_message_text(
                        f"📁 **جاري فحص الملف**\n\n🔢 الإجمالي: {total_ips} IP\n📊 تم فحص: {scanned_count}/{total_ips}\n🟢 النشطة: {active_count}\n⏳ الباقي: {remaining}\n📈 النسبة: {percentage:.1f}%\n{progress_bar}",
                        chat_id,
                        progress_msg.message_id
                    )
                    last_update_time = current_time
                except:
                    try:
                        bot.delete_message(chat_id, progress_msg.message_id)
                    except:
                        pass
                    progress_msg = bot.send_message(
                        chat_id,
                        f"📁 **جاري فحص الملف**\n\n🔢 الإجمالي: {total_ips} IP\n📊 تم فحص: {scanned_count}/{total_ips}\n🟢 النشطة: {active_count}\n⏳ الباقي: {remaining}\n📈 النسبة: {percentage:.1f}%\n{progress_bar}"
                    )
                    last_update_time = current_time
            if scanned_count % 10 == 0:
                time.sleep(0.05)
        try:
            bot.delete_message(chat_id, progress_msg.message_id)
        except:
            pass
        summary = f"""
✅ **تم الانتهاء من فحص الملف**

📊 **النتائج النهائية:**
• 🔢 إجمالي الـIPs: {total_ips}
• 🟢 النشطة: {active_count}
• 🔴 غير النشطة: {total_ips - active_count}
• 📈 نسبة النجاح: {(active_count/total_ips)*100:.1f}%

💡 **ملاحظة:** تم عرض النتائج النشطة فقط
"""
        bot.send_message(chat_id, summary)
    except Exception as e:
        bot.send_message(chat_id, f"❌ خطأ في معالجة الملف: {str(e)}")
    finally:
        end_operation(chat_id)

# ---------------- الفحص السريع الجماعي ----------------
def process_bulk_quick_scan(chat_id, ip_list):
    total_ips = len(ip_list)
    progress_msg = bot.send_message(
        chat_id,
        f"⚡ **بدء الفحص السريع**\n\n🔢 إجمالي الـIPs: {total_ips}\n📊 تم فحص: 0/{total_ips}\n🟢 النشطة: 0\n⏳ الباقي: {total_ips}\n📈 النسبة: 0%\n[░░░░░░░░░░░░░░░░░░░░]"
    )
    active_count = 0
    scanned_count = 0
    last_update_time = time.time()
    for i, item in enumerate(ip_list):
        if should_stop(chat_id):
            ip, ports = item['ip'], item['ports']
            is_active = perform_quick_scan(chat_id, ip, ports, f"سريع", show_failures=False)
            scanned_count = i + 1
            if is_active:
                active_count += 1
            try:
                bot.delete_message(chat_id, progress_msg.message_id)
            except:
                pass
            success_rate = (active_count / scanned_count * 100) if scanned_count > 0 else 0
            summary = f"""
⏹️ **تم إيقاف الفحص السريع**

📊 **النتائج حتى الآن:**
• 🔢 تم فحص: {scanned_count}/{total_ips}
• 🟢 النشطة: {active_count}
• 📈 نسبة النجاح: {success_rate:.1f}%
"""
            bot.send_message(chat_id, summary)
            return active_count
        ip, ports = item['ip'], item['ports']
        is_active = perform_quick_scan(chat_id, ip, ports, f"سريع", show_failures=False)
        scanned_count = i + 1
        if is_active:
            active_count += 1
        current_time = time.time()
        if current_time - last_update_time >= 2 or scanned_count == total_ips:
            percentage = (scanned_count / total_ips) * 100
            remaining = total_ips - scanned_count
            progress_bar = create_progress_bar(percentage, 20)
            try:
                bot.edit_message_text(
                    f"⚡ **جاري الفحص السريع**\n\n🔢 الإجمالي: {total_ips} IP\n📊 تم فحص: {scanned_count}/{total_ips}\n🟢 النشطة: {active_count}\n⏳ الباقي: {remaining}\n📈 النسبة: {percentage:.1f}%\n{progress_bar}",
                    chat_id,
                    progress_msg.message_id
                )
                last_update_time = current_time
            except:
                try:
                    bot.delete_message(chat_id, progress_msg.message_id)
                except:
                    pass
                progress_msg = bot.send_message(
                    chat_id,
                    f"⚡ **جاري الفحص السريع**\n\n🔢 الإجمالي: {total_ips} IP\n📊 تم فحص: {scanned_count}/{total_ips}\n🟢 النشطة: {active_count}\n⏳ الباقي: {remaining}\n📈 النسبة: {percentage:.1f}%\n{progress_bar}"
                )
                last_update_time = current_time
        if scanned_count % 5 == 0:
            time.sleep(0.02)
    try:
        bot.delete_message(chat_id, progress_msg.message_id)
    except:
        pass
    return active_count

# ---------------- أوامر البوت والمعالجات ----------------
@bot.message_handler(commands=['start'])
def start_message(message):
    chat_id = message.chat.id
    stop_user_operations(chat_id)
    kb = telebot.types.ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=False)
    kb.add('/start', '/stop', '/ssh')
    bot.send_message(chat_id, "👋 أهلاً! اختر نوع الفحص:", reply_markup=kb)
    # زر SSH
    inline_kb = telebot.types.InlineKeyboardMarkup()
    inline_kb.row(telebot.types.InlineKeyboardButton("🔑 استخراج SSH", callback_data='ssh_menu'),
                  telebot.types.InlineKeyboardButton("⚡ فحص سريع", callback_data='fx_fast'))
    inline_kb.row(telebot.types.InlineKeyboardButton("🔍 فحص شامل", callback_data='fx_full'),
                  telebot.types.InlineKeyboardButton("🌐 جلب بروكسيات", callback_data='fetch_proxies'))
    bot.send_message(chat_id, "⚡ اختر نوع الفحص:", reply_markup=inline_kb)

@bot.message_handler(commands=['ssh'])
def ssh_command(message):
    chat_id = message.chat.id
    show_ssh_menu(chat_id)

@bot.message_handler(commands=['stop'])
def stop_message(message):
    chat_id = message.chat.id
    stop_user_operations(chat_id)
    bot.send_message(chat_id, "⏹️ تم إيقاف جميع العمليات الجارية.")

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id
    try:
        bot.answer_callback_query(call.id)
    except:
        pass
    if call.data == 'fx_fast':
        bot.send_message(chat_id,
            '⚡ **الفحص السريع**\n\n'
            'أرسل الآن IP أو قائمة IPs (حتى 300 IP)\n\n'
            '📝 **التنسيقات:**\n'
            '• IP:Port\n'
            '• IP:Port1,Port2,Port3\n'
            '• IP فقط\n\n'
            '📋 **مثال:**\n'
            '192.168.1.1:8080\n'
            '192.168.1.2:80,443\n'
            '192.168.1.3\n\n'
            '💡 **ملاحظة:** سيتم عرض النتائج النشطة فقط'
        )
    elif call.data == 'fx_full':
        waitingFull.add(chat_id)
        bot.send_message(chat_id, '🔍 أرسل الآن IP للفحص الشامل TCP 1–65535.')
    elif call.data == 'ssh_menu':
        show_ssh_menu(chat_id)
    elif call.data == 'ssh_generate':
        handle_ssh_generate(chat_id)
    elif call.data == 'back_main':
        start_message(call.message)
    elif call.data == 'upload_file':
        file_upload_mode.add(chat_id)
        bot.send_message(chat_id,
            '📁 **رفع ملف txt**\n\n'
            'ارفع ملف txt يحتوي على IPs (حتى 1000 IP)\n\n'
            '📝 **التنسيقات المدعومة:**\n'
            '• IP:Port\n'
            '• IP فقط\n'
            '• سطر واحد لكل IP\n\n'
            '📎 **ارفع الملف الآن...**\n\n'
            '⚡ **الآن بسرعة فائقة مع العداد الحي**'
        )
    elif call.data == 'fetch_proxies':
        inline_kb = telebot.types.InlineKeyboardMarkup()
        inline_kb.row(
            telebot.types.InlineKeyboardButton("🚀 مصادر افتراضية", callback_data='fetch_default_proxies'),
            telebot.types.InlineKeyboardButton("📝 رابط مخصص", callback_data='fetch_custom_proxies')
        )
        inline_kb.row(telebot.types.InlineKeyboardButton("🔙 رجوع", callback_data='back_main'))
        bot.send_message(chat_id,
            '🌐 **جلب بروكسيات Google**\n\n'
            '🔍 سأبحث عن بروكسيات تابعة لـ Google فقط (AS396982)\n\n'
            '📥 اختر مصدر البروكسيات:',
            reply_markup=inline_kb
        )
    elif call.data == 'fetch_default_proxies':
        bot.send_message(chat_id, "🚀 جاري جلب بروكسيات Google من المصادر الافتراضية...")
        threading.Thread(target=process_google_proxies_scan, args=(chat_id, None), daemon=True).start()
    elif call.data == 'fetch_custom_proxies':
        waiting_proxy_url.add(chat_id)
        bot.send_message(chat_id,
            '📝 **أدخل رابط البروكسيات**\n\n'
            '🌐 مثال:\n'
            'https://raw.githubusercontent.com/TheSpeedX/SOCKS-List/master/http.txt\n\n'
            '📥 سأجلب البروكسيات من هذا الرابط وأفلتر فقط بروكسيات Google'
        )
    elif call.data == 'upload_file':
        file_upload_mode.add(chat_id)
        bot.send_message(chat_id, "📁 ارفع الملف الآن (txt)")

@bot.message_handler(content_types=['document'])
def handle_document(message):
    chat_id = message.chat.id
    if chat_id not in file_upload_mode:
        return
    file_upload_mode.discard(chat_id)
    if not message.document.file_name.lower().endswith('.txt'):
        bot.send_message(chat_id, "❌ يرجى رفع ملف txt فقط.")
        return
    try:
        file_info = bot.get_file(message.document.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        bot.send_message(chat_id, "📁 جاري معالجة الملف...")
        threading.Thread(target=process_file_scan, args=(chat_id, downloaded_file), daemon=True).start()
    except Exception as e:
        bot.send_message(chat_id, f"❌ خطأ في تحميل الملف: {str(e)}")

@bot.message_handler(func=lambda m: True)
def handle_message(message):
    chat_id = message.chat.id
    text = (message.text or "").strip()
    if not text or text.startswith('/'):
        return
    if chat_id in waitingFull:
        waitingFull.remove(chat_id)
        ip = text
        threading.Thread(target=perform_full_scan, args=(chat_id, ip), daemon=True).start()
        return
    if chat_id in waiting_proxy_url:
        waiting_proxy_url.discard(chat_id)
        if text.startswith('http'):
            bot.send_message(chat_id, f"📥 جاري جلب البروكسيات من الرابط...")
            threading.Thread(target=process_google_proxies_scan, args=(chat_id, text), daemon=True).start()
        else:
            bot.send_message(chat_id, "❌ الرابط غير صالح. يرجى إدخال رابط يبدأ بـ http أو https")
        return
    # معالجة إدخالات IP / IP:Port
    raw_ips = [t.strip() for t in text.replace(',', '\n').split('\n') if t.strip()]
    ip_list = []
    for ip_text in raw_ips[:MAX_IPS_PER_MSG]:
        parts = ip_text.split(':')
        ip = parts[0].strip()
        if not validate_ip(ip):
            continue
        if len(parts) > 1 and parts[1].strip():
            try:
                ports = list(map(int, parts[1].split(',')))
                ports = [p for p in ports if 1 <= p <= 65535]
                if len(ports) > MAX_FAST_PORTS:
                    ports = ports[:MAX_FAST_PORTS]
            except:
                ports = defaultPorts.copy()
        else:
            ports = defaultPorts.copy()
        ip_list.append({'ip': ip, 'ports': ports})
    if not ip_list:
        bot.send_message(chat_id, "❌ لم يتم التعرف على أي IP صالح في النص.")
        return
    if len(ip_list) > 1:
        bot.send_message(chat_id, f"🔍 بدء فحص {len(ip_list)} IP...")
        threading.Thread(target=lambda: process_bulk_quick_scan(chat_id, ip_list), daemon=True).start()
    else:
        item = ip_list[0]
        ip, ports = item['ip'], item['ports']
        threading.Thread(target=lambda: perform_quick_scan(chat_id, ip, ports, "سريع", show_failures=True), daemon=True).start()

# ---------------- تشغيل البوت ----------------
if __name__ == "__main__":
    print("🚀 بدء تشغيل البوت المحسن بدون COD...")
    print(f"⚡ الإعدادات: MAX_IPS_PER_MSG={MAX_IPS_PER_MSG}, MAX_FILE_IPS={MAX_FILE_IPS}")
    bot.infinity_polling()
