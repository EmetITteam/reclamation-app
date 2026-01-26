import base64
import json
import requests
import smtplib
import re
import os  # <--- ОСЬ ЦЕЙ РЯДОК ОБОВ'ЯЗКОВО ДОДАТИ!
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Body, Request
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

app = FastAPI()

app = FastAPI()

# --- ⚙️ НАЛАШТУВАННЯ ---
BITRIX_WEBHOOK_URL = "https://bitrix.emet.in.ua/rest/2049/24pv36uotghswqwa/"

# ID Смарт-процесів
CLAIMS_SPA_ID = 1038       # Рекламації
MANAGERS_SPA_ID = 1042     # Менеджери

# Кому дзвонити в "Дзвіночок" (ID співробітників мед. відділу)
MED_DEPT_USER_IDS = [2049, 12546, 2081, 2080, 6601] 

# --- КОДИ ПОЛІВ ---

# 1. Поля в базі МЕНЕДЖЕРІВ (SPA 1042)
MGR_FIELD_EMAIL = "ufCrm5_1769158424"
MGR_FIELD_PASS  = "ufCrm5_1769158448"
MGR_FIELD_TG_ID = "ufCrm5_1769158458"

# 2. Поля в РЕКЛАМАЦІЇ (SPA 1038)
# Те саме поле Tech Email, про яке ви казали (ufCrm4_1769084999)
FIELD_MANAGER_EMAIL_IN_CLAIM = "ufCrm4_1769084999" 

FIELDS_MAP = {
    "title": "title",
    "lot": "ufCrm4_1769003758",
    "invoice": "ufCrm4_1769003770",
    "details": "ufCrm4_1769003784",
    "files": "ufCrm4_1769005413",
    "manager": "ufCrm4_1769005441",
    "product": "ufCrm4_1769005557",
    "claim_type": "ufCrm4_1769005573"
}

TYPE_TRANSLATION = {
    "defect_pack": "Неякісна упаковка",
    "quality": "Якість препарату",
    "effectiveness": "Ефективність",
    "side_effect": "Побічна дія",
    "complication": "Ускладнення",
    "other": "Інше"
}

# Telegram & Email
# --- БЕЗПЕКА (Беремо ключі з налаштувань Vercel) ---
# Якщо змінних немає в Vercel, код не впаде, але телеграм не працюватиме
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN", "") 
TG_ADMIN_CHAT_ID = os.environ.get("TG_ADMIN_CHAT_ID", "")

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "noreply@emet.in.ua"
SMTP_PASS = "cgme lnuf pytd widr"

# --- 🛠 ДОПОМІЖНІ ФУНКЦІЇ ---

def send_telegram(chat_id, message):
    if not chat_id: return
    try:
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"})
    except Exception as e:
        print(f"TG Error: {e}")

def send_email(to_email, subject, body):
    if not to_email or not SMTP_USER: return
    try:
        msg = MIMEMultipart()
        msg['From'] = SMTP_USER
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(SMTP_USER, to_email, msg.as_string())
        server.quit()
    except Exception as e:
        print(f"Email Error: {e}")

# Пошук менеджера в базі (SPA 1042)
def find_manager_by_email(email):
    try:
        r = requests.post(f"{BITRIX_WEBHOOK_URL}crm.item.list", json={
            "entityTypeId": MANAGERS_SPA_ID,
            "filter": { MGR_FIELD_EMAIL: email },
            "select": ["id", "title", MGR_FIELD_EMAIL, MGR_FIELD_PASS, MGR_FIELD_TG_ID]
        })
        data = r.json()
        if "result" in data and data["result"]["items"]:
            return data["result"]["items"][0]
    except Exception as e:
        print(f"Error finding manager: {e}")
    return None

# Відправка "Дзвіночка" в Бітрікс
def send_bitrix_notification(user_id, message):
    try:
        requests.post(f"{BITRIX_WEBHOOK_URL}im.notify", json={
            "to": user_id,
            "message": message,
            "type": "SYSTEM"
        })
    except:
        pass

# --- 🤖 TELEGRAM WEBHOOK (АВТОРИЗАЦІЯ + ВІДПОВІДІ) ---
# --- 🤖 TELEGRAM WEBHOOK (З ПОСИЛАННЯМ ДЛЯ МЕД. ВІДДІЛУ) ---
@app.post("/api/telegram_webhook")
async def telegram_webhook(request: Request):
    try:
        data = await request.json()
        if "message" not in data: return {"status": "ignored"}
        
        msg = data["message"]
        chat_id = msg.get("chat", {}).get("id")
        text = msg.get("text", "").strip()
        
        # 1. /start
        if text == "/start":
            send_telegram(chat_id, "👋 Привіт! Напишіть ваш робочий <b>Email</b> для підключення.")
            return {"status": "ok"}

        # 2. Авторизація (Email)
        if "@" in text and not " " in text:
            email = text.lower()
            manager = find_manager_by_email(email)
            
            if manager:
                # Оновлюємо TG ID в картці менеджера
                requests.post(f"{BITRIX_WEBHOOK_URL}crm.item.update", json={
                    "entityTypeId": MANAGERS_SPA_ID,
                    "id": manager["id"],
                    "fields": { MGR_FIELD_TG_ID: str(chat_id) }
                })
                
                send_telegram(chat_id, f"✅ <b>Вітаємо, {manager['title']}!</b>\nВи успішно підключені до системи.")
                if TG_ADMIN_CHAT_ID:
                    send_telegram(TG_ADMIN_CHAT_ID, f"🔗 Менеджер {manager['title']} підключив Telegram!")
            else:
                send_telegram(chat_id, "❌ Email не знайдено в базі менеджерів.")
            return {"status": "ok"}

        # 3. Відповідь на заявку (Reply)
        if "reply_to_message" in msg:
            original_text = msg["reply_to_message"].get("text", "")
            match = re.search(r"#(\d+)", original_text)
            
            if match:
                claim_id = match.group(1)
                sender_name = msg.get("from", {}).get("first_name", "Менеджер")
                
                formatted_message = f"📱 <b>{sender_name}</b> (Telegram):<br>{text}"
                
                # Додаємо коментар у заявку
                requests.post(f"{BITRIX_WEBHOOK_URL}crm.timeline.comment.add", json={
                    "fields": {
                        "ENTITY_ID": claim_id, 
                        "ENTITY_TYPE": f"dynamic_{CLAIMS_SPA_ID}", 
                        "COMMENT": formatted_message
                    }
                })
                
                # 👇 ФОРМУЄМО ПОСИЛАННЯ ДЛЯ БІТРІКС
                link_to_crm = f"https://bitrix.emet.in.ua/crm/type/{CLAIMS_SPA_ID}/details/{claim_id}/"
                
                # 👇 Сповіщаємо мед. відділ у "Дзвіночок" З ПОСИЛАННЯМ [URL]
                notify_msg = f"💬 Нова відповідь менеджера по заявці [URL={link_to_crm}]#{claim_id}[/URL]: {text}"
                
                for uid in MED_DEPT_USER_IDS:
                    send_bitrix_notification(uid, notify_msg)

                send_telegram(chat_id, "✅ Коментар додано!")
                return {"status": "ok"}
        
        return {"status": "ignored"}

    except Exception as e:
        print(f"TG Webhook Error: {e}")
        return {"status": "error"}

# --- 🔐 ЛОГІН ---
@app.post("/api/login")
async def login(data: Dict[str, Any] = Body(...)):
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()
    is_auto = data.get("is_auto", False)

    if not email: return {"status": "error", "message": "Email не вказано"}

    # Шукаємо в базі Бітрікс
    manager = find_manager_by_email(email)

    if not manager:
        return {"status": "error", "message": "Користувача не знайдено"}

    stored_pass = manager.get(MGR_FIELD_PASS)
    
    if not is_auto and str(stored_pass) != str(password):
        return {"status": "error", "message": "Невірний пароль"}

    return {
        "status": "success",
        "name": manager["title"],
        "email": email,
        "phone": ""
    }

# --- 📝 СТВОРЕННЯ ЗАЯВКИ ---
@app.post("/api/submit_claim")
async def submit_claim(
    type: str = Form(...), client: str = Form(...), product: str = Form(...), 
    lot: str = Form(...), manager: str = Form(...), manager_email: Optional[str] = Form(None),
    invoice: Optional[str] = Form(None), details: str = Form(...), files: List[UploadFile] = File(None)
):
    try:
        details_dict = json.loads(details)
        formatted_text = "\n".join([f"{k}: {v}" for k, v in details_dict.items()])
        readable_type = TYPE_TRANSLATION.get(type, type)
        
        bx_fields = {
            FIELDS_MAP["title"]: f"Рекламація: {client}",
            FIELDS_MAP["product"]: product,
            FIELDS_MAP["claim_type"]: readable_type,
            FIELDS_MAP["lot"]: lot,
            FIELDS_MAP["invoice"]: invoice or "-",
            FIELDS_MAP["details"]: formatted_text,
            FIELDS_MAP["manager"]: manager,
            "OPENED": "Y"
        }
        
        if manager_email: bx_fields[FIELD_MANAGER_EMAIL_IN_CLAIM] = manager_email
        
        if files:
            file_list = []
            for f in files:
                c = await f.read()
                file_list.append([f.filename, base64.b64encode(c).decode()])
            bx_fields[FIELDS_MAP["files"]] = file_list

        r = requests.post(f"{BITRIX_WEBHOOK_URL}crm.item.add", json={"entityTypeId": CLAIMS_SPA_ID, "fields": bx_fields})
        res = r.json()
        if "error" in res: raise HTTPException(500, res['error_description'])
        
        new_id = res['result']['item']['id']
        link_to_item = f"https://bitrix.emet.in.ua/crm/type/{CLAIMS_SPA_ID}/details/{new_id}/"
        
        # 🔔 ДЗВІНОЧОК З ПОСИЛАННЯМ [URL]
        notify_msg = f"🚨 [URL={link_to_item}]Нова рекламація #{new_id}![/URL]\nКлієнт: {client}\nМенеджер: {manager}"
        
        for uid in MED_DEPT_USER_IDS:
            send_bitrix_notification(uid, notify_msg)

        # Телеграм
        if manager_email:
            mgr = find_manager_by_email(manager_email)
            if mgr and mgr.get(MGR_FIELD_TG_ID):
                send_telegram(mgr[MGR_FIELD_TG_ID], f"✅ <b>Заявка #{new_id} прийнята!</b>\nКлієнт: {client}")
        
        if TG_ADMIN_CHAT_ID:
            send_telegram(TG_ADMIN_CHAT_ID, f"📝 Створено заявку(Адмін повідомлення) #{new_id}")

        return {"status": "success", "id": new_id}
    except Exception as e:
        raise HTTPException(500, str(e))

# --- ЦЕЙ КЛАС ОБОВ'ЯЗКОВО МАЄ БУТИ В КОДІ (перед add_comment) ---
class CommentModel(BaseModel):
    id: int
    message: str
    author: str

# --- ДОДАВАННЯ КОМЕНТАРЯ (Виправляємо помилку 404) ---
@app.post("/api/add_comment")
async def add_comment(data: CommentModel):
    # Формуємо красивий HTML для Бітрікс
    formatted_message = f"👨‍💻 <b>{data.author}</b> (Менеджер):<br>{data.message}"
    
    # 1. Відправляємо коментар у стрічку (Таймлайн)
    requests.post(f"{BITRIX_WEBHOOK_URL}crm.timeline.comment.add", json={
        "fields": {
            "ENTITY_ID": data.id, 
            "ENTITY_TYPE": f"dynamic_{CLAIMS_SPA_ID}", 
            "COMMENT": formatted_message
        }
    })
    
    # 2. Формуємо посилання для "Дзвіночка"
    link_to_item = f"https://bitrix.emet.in.ua/crm/type/{CLAIMS_SPA_ID}/details/{data.id}/"
    
    # 3. Відправляємо сповіщення мед. відділу
    for uid in MED_DEPT_USER_IDS:
        send_bitrix_notification(uid, f"💬 [URL={link_to_item}]Новий коментар у заявці #{data.id}[/URL] від менеджера.")
        
    return {"status": "ok"}

# --- 📋 ІСТОРІЯ (Шукаємо по FIELD_MANAGER_EMAIL_IN_CLAIM) ---
# --- 📋 ІСТОРІЯ (З ОНОВЛЕНИМ ДЕБАГОМ СТАТУСІВ) ---
@app.post("/api/get_history")
async def get_history(email: str = Form(...)):
    if not email: return {"history": []}
    
    # Запит до Бітрікс
    r = requests.post(f"{BITRIX_WEBHOOK_URL}crm.item.list", json={
        "entityTypeId": CLAIMS_SPA_ID,
        "filter": { FIELD_MANAGER_EMAIL_IN_CLAIM: email }, 
        "select": ["id", "title", "stageId", "createdTime"],
        "order": {"id": "DESC"}
    })
    
    data = r.json()
    if "result" not in data: return {"history": []}
    
    history = []
    if "items" in data['result']:
        for item in data['result']['items']:
            stage = item.get("stageId", "")
            
            # 👇 ОСЬ ЦЕЙ РЯДОК ПОКАЖЕ НАМ КОД СТАТУСУ В ЛОГАХ
            print(f"🐛 CLAIM #{item['id']} STAGE ID: {stage}") 

            st_text = "В обробці"
            stage_upper = stage.upper() # Переводимо в верхній регістр

            # Перевірка на УСПІХ (додавайте сюди коди, які побачите в логах)
            if any(x in stage_upper for x in ["WON", "SUCCESS", "ВИКОНАНО","ВЫПОЛНЕНО", "УСПІХ", "DONE", "FINAL", "CLIENT"]): 
                st_text = "Вирішено"
            # Перевірка на ВІДМОВУ
            elif any(x in stage_upper for x in ["FAIL", "LOSE", "ВІДМОВА", "ОТКАЗ"]): 
                st_text = "Відмовлено"
            # Перевірка на НОВУ
            elif any(x in stage_upper for x in ["NEW", "НОВА", "BEGIN"]): 
                st_text = "Нова"
            
            history.append({
                "id": item["id"], "title": item["title"], 
                "date": item["createdTime"][:10], "status": st_text
            })
            
    return {"history": history}

# --- 📄 ДЕТАЛІ ЗАЯВКИ ---
@app.post("/api/get_claim_details")
async def get_claim_details(data: Dict[str, int] = Body(...)):
    item_id = data.get('id')
    if not item_id: return {"status": "error"}
    r = requests.post(f"{BITRIX_WEBHOOK_URL}crm.item.get", json={"entityTypeId": CLAIMS_SPA_ID, "id": item_id})
    res = r.json()
    if "result" not in res: return {"status": "error"}
    item = res['result']['item']
    stage = item.get("stageId", "")
    st_text = "В обробці"
    stage_upper = stage.upper()
    if any(x in stage_upper for x in ["WON", "SUCCESS", "ВИКОНАНО", "ВЫПОЛНЕНО", "CLIENT"]): st_text = "Вирішено"
    elif any(x in stage_upper for x in ["FAIL", "LOSE", "ВІДМОВА", "ОТКАЗ"]): st_text = "Відмовлено"
    elif "NEW" in stage: st_text = "Нова"
    return {"status": "ok", "data": {
        "id": item.get("id"), "title": item.get("title"), "product": item.get(FIELDS_MAP["product"]),
        "lot": item.get(FIELDS_MAP["lot"]), "client": item.get("title", "").replace("Рекламація: ", ""),
        "details": item.get(FIELDS_MAP["details"]), "status_text": st_text
    }}

# --- ДОДАЙТЕ ЦЕЙ РЯДОК ПЕРЕД ФУНКЦІЄЮ (для кешування імен) ---
USER_NAME_CACHE = {}

# --- ОНОВЛЕНА ФУНКЦІЯ (запитує імена у Бітрікс) ---
@app.post("/api/get_comments")
async def get_comments(data: Dict[str, int] = Body(...)):
    item_id = data.get('id')
    
    # Отримуємо коментарі
    r = requests.post(f"{BITRIX_WEBHOOK_URL}crm.timeline.comment.list", json={
        "filter": {"ENTITY_ID": item_id, "ENTITY_TYPE": f"dynamic_{CLAIMS_SPA_ID}", "TYPE_ID": "COMMENT"},
        "order": {"ID": "DESC"}
    })
    
    comments = []
    items = r.json().get('result', [])
    
    for c in items:
        author_id = c.get('AUTHOR_ID')
        author_name = f"Користувач {author_id}" # Запасний варіант
        
        # ВАРІАНТ 1: Коментар від Менеджера (через наш додаток/телеграм)
        # У них AUTHOR_ID зазвичай 0 або None, а ім'я сховане в тексті <b>Name</b>
        if not author_id or str(author_id) == '0':
             match = re.search(r"<b>(.*?)</b>", c.get('COMMENT', ''))
             if match:
                 author_name = match.group(1)
             else:
                 author_name = "Менеджер"
        
        # ВАРІАНТ 2: Коментар від співробітника Бітрікс (Лікар, Адмін)
        # У них є реальний ID (наприклад 2049)
        elif author_id:
            # Якщо ім'я вже є в кеші - беремо звідти (щоб не гальмувати)
            if author_id in USER_NAME_CACHE:
                author_name = USER_NAME_CACHE[author_id]
            else:
                # Якщо немає - робимо запит до Бітрікс
                try:
                    u_req = requests.post(f"{BITRIX_WEBHOOK_URL}user.get", json={"ID": author_id})
                    users = u_req.json().get('result', [])
                    if users:
                        user = users[0]
                        full_name = f"{user.get('NAME', '')} {user.get('LAST_NAME', '')}".strip()
                        if full_name:
                            author_name = full_name
                            USER_NAME_CACHE[author_id] = author_name # Запам'ятовуємо
                except:
                    pass
        
        comments.append({
            "id": c['ID'], 
            "text": c['COMMENT'], 
            "author": author_name, 
            "date": c['CREATED']
        })
        
    return {"comments": comments}

# --- 🔄 СТАТУСИ (WEBHOOK ВІД БІТРІКС) ---
# --- 🔄 СТАТУСИ (ИСПРАВЛЕНО: ДОБАВЛЕН РУССКИЙ ЯЗЫК) ---
@app.post("/api/webhook/status_update")
async def status_update(id: str, stage_id: str):
    EMAIL_MED_DEPT = "reclamation@emet.in.ua"
    
    try:
        # Очистка ID
        clean_id = id.split('_')[-1] if '_' in id else id
        clean_id = "".join(filter(str.isdigit, clean_id))
        
        if not clean_id: return {"status": "error"}
        real_id = int(clean_id)
        
        print(f"🔄 WEBHOOK UPDATE: Claim #{real_id}, Stage: {stage_id}")
        
        LINK_TO_CRM = f"https://bitrix.emet.in.ua/crm/type/{CLAIMS_SPA_ID}/details/{real_id}/"
        stage_upper = stage_id.upper() # Превращаем в верхний регистр (ВЫПОЛНЕНО)

        # --- ЛОГИКА СТАТУСОВ ---
        
        # 1. Новая
        is_new = any(x in stage_upper for x in ["NEW", "НОВА", "BEGIN"])
        
        # 2. Успех (Добавил: ВЫПОЛНЕНО, ГОТОВО, CLIENT, DONE)
        is_success = any(x in stage_upper for x in ["SUCCESS", "WON", "CLIENT", "УСПІХ", "ВИКОНАНО", "ВЫПОЛНЕНО", "ГОТОВО", "DONE"])
        
        # 3. Отказ (Добавил: ОТКАЗ)
        is_fail = any(x in stage_upper for x in ["FAIL", "LOSE", "ВІДМОВА", "ОТКАЗ"])
        
        is_end = is_success or is_fail

        if is_new or is_end:
            r = requests.post(f"{BITRIX_WEBHOOK_URL}crm.item.get", json={"entityTypeId": CLAIMS_SPA_ID, "id": real_id})
            item = r.json().get('result', {}).get('item', {})
            manager_mail = item.get(FIELD_MANAGER_EMAIL_IN_CLAIM)
            
            print(f"   -> Status Logic: New={is_new}, Success={is_success} (Found 'ВЫПОЛНЕНО'?), Fail={is_fail}")

            # 🅰️ НОВАЯ
            if is_new:
                body = f"Нова рекламація #{real_id}. <br><a href='{LINK_TO_CRM}'>Відкрити картку</a>"
                send_email(EMAIL_MED_DEPT, f"Нова рекламація #{real_id}", body)
            
            # 🅱️ ЗАВЕРШЕНА
            elif is_end:
                status_text = "ВИРІШЕНО ✅" if is_success else "ВІДМОВЛЕНО ❌"
                
                if manager_mail:
                    mgr = find_manager_by_email(manager_mail)
                    
                    # Телеграм
                    if mgr and mgr.get(MGR_FIELD_TG_ID):
                        tg_msg = f"🔔 <b>Оновлення статусу!</b>\nЗаявка #{real_id}\nСтатус: {status_text}"
                        send_telegram(mgr[MGR_FIELD_TG_ID], tg_msg)
                        print(f"   -> TG sent to {mgr[MGR_FIELD_TG_ID]}")
                    
                    # Email
                    msg_text = f"Статус заявки #{real_id} змінено на: {status_text}"
                    send_email(manager_mail, f"Статус заявки #{real_id}", msg_text)
                    print(f"   -> Email sent to {manager_mail}")
                else:
                    print("   -> No Manager Email found")

        return {"status": "ok"}
    except Exception as e:
        print(f"❌ WEBHOOK ERROR: {e}")
        return {"status": "ok", "error": str(e)}

# --- 📨 ВЕБХУК ПОДІЙ (КОМЕНТАРІ З БІТРІКС -> ТЕЛЕГРАМ) ---
# --- 📨 ВЕБХУК (ФИНАЛ: ДОБАВИЛИ ID В ТЕКСТ ДЛЯ ОТВЕТОВ) ---
# --- 📨 ВЕБХУК (ФІНАЛ: З ПОСИЛАННЯМ НА CRM) ---
@app.post("/api/webhook/bitrix_event")
async def bitrix_event(request: Request):
    try:
        form = await request.form()
        fields = dict(form)
        event = fields.get('event')
        
        if event == 'ONCRMTIMELINECOMMENTADD':
            comment_id = fields.get('data[FIELDS][ID]')
            if not comment_id: return {"status": "ignored"}

            # 1. Отримуємо деталі коментаря
            r_com = requests.post(f"{BITRIX_WEBHOOK_URL}crm.timeline.comment.get", json={"id": comment_id})
            comment_res = r_com.json()
            comment_data = comment_res.get('result', {})
            
            if not comment_data: return {"status": "error"}

            entity_id = comment_data.get('ENTITY_ID') 
            comment_text = comment_data.get('COMMENT', '')
            author_id = comment_data.get('AUTHOR_ID')

            # Фільтр "Ехо" (ігноруємо свої ж повідомлення)
            if "📱" in comment_text or "👨‍💻" in comment_text or "URL=" in comment_text:
                return {"status": "ignored"}

            # 2. Шукаємо заявку
            r_item = requests.post(f"{BITRIX_WEBHOOK_URL}crm.item.get", json={"entityTypeId": CLAIMS_SPA_ID, "id": entity_id})
            item = r_item.json().get('result', {}).get('item', {})
            
            if not item: return {"status": "ignored"}
            
            manager_mail = item.get(FIELD_MANAGER_EMAIL_IN_CLAIM)
            claim_title = item.get("title", f"Заявка #{entity_id}")

            # 3. Відправляємо в ТГ
            if manager_mail:
                mgr = find_manager_by_email(manager_mail)
                if mgr and mgr.get(MGR_FIELD_TG_ID):
                    
                    author_name = "Медичний відділ"
                    try:
                        u_req = requests.post(f"{BITRIX_WEBHOOK_URL}user.get", json={"ID": author_id})
                        users = u_req.json().get('result', [])
                        if users: author_name = f"{users[0]['NAME']} {users[0]['LAST_NAME']}"
                    except: pass
                    
                    # 👇 СТВОРЮЄМО ПОСИЛАННЯ
                    link_to_crm = f"https://bitrix.emet.in.ua/crm/type/{CLAIMS_SPA_ID}/details/{entity_id}/"
                    
                    # 👇 ДОДАЄМО ПОСИЛАННЯ В ЗАГОЛОВОК
                    msg = f"💬 <b>Новий коментар у заявці <a href='{link_to_crm}'>#{entity_id}</a></b>\n{claim_title}\n\n👤 <b>{author_name}:</b>\n{comment_text}\n\n<i>Ви можете відповісти на це повідомлення</i>"
                    
                    send_telegram(mgr[MGR_FIELD_TG_ID], msg)
                    print(f"   -> ✅ SENT TG to {mgr[MGR_FIELD_TG_ID]}")

        return {"status": "ok"}
    except Exception as e:
        print(f"❌ ERROR: {e}")
        return {"status": "error"}
