import base64
import json
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Body
from typing import List, Optional, Dict, Any
from pydantic import BaseModel  # <--- ОСЬ ЦЬОГО НЕ ВИСТАЧАЛО!

app = FastAPI()

# --- ⚙️ НАЛАШТУВАННЯ ---
BITRIX_WEBHOOK_URL = "https://bitrix.emet.in.ua/rest/2049/24pv36uotghswqwa/"

# ID Смарт-процесів
CLAIMS_SPA_ID = 1038       # Рекламації
MANAGERS_SPA_ID = 1042     # Менеджери

# Кому дзвонити в "Дзвіночок" (ID співробітників мед. відділу через кому)
# Наприклад: [2049, 15, 34]
MED_DEPT_USER_IDS = [2049] 

# Поля МЕНЕДЖЕРІВ (Ваші коди з Бітрікс)
MGR_FIELD_EMAIL = "ufCrm5_1769158424"
MGR_FIELD_PASS  = "ufCrm5_1769158448"
MGR_FIELD_TG_ID = "ufCrm5_1769158458"

# Поле в РЕКЛАМАЦІЇ, куди пишемо email менеджера
FIELD_MANAGER_EMAIL_IN_CLAIM = "ufCrm4_1769084999"

# Telegram & Email
TG_BOT_TOKEN = "ВАШ_ТОКЕН_БОТА" 
TG_ADMIN_CHAT_ID = "ВАШ_ОСОБИСТИЙ_ID" 

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "noreply@emet.in.ua"
SMTP_PASS = "cgme lnuf pytd widr"

# --- 🛠 ДОПОМІЖНА ФУНКЦІЯ (ПОШУК МЕНЕДЖЕРА В БІТРІКС) ---
# Цю функцію додайте перед FIELDS_MAP або після imports
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

# Функція для "Дзвіночка"
def send_bitrix_notification(user_id, message):
    try:
        requests.post(f"{BITRIX_WEBHOOK_URL}im.notify", json={
            "to": user_id,
            "message": message,
            "type": "SYSTEM"
        })
    except:
        pass

# --- ПРАВИЛЬНІ КОДИ ПОЛІВ ---
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

# --- ФУНКЦІЇ ---
def send_telegram(message):
    if not TG_BOT_TOKEN or TG_BOT_TOKEN == "ВАШ_ТОКЕН": return
    try:
        url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        requests.post(url, json={"chat_id": TG_CHAT_ID, "text": message, "parse_mode": "HTML"})
    except Exception as e:
        print(f"TG Error: {e}")

def send_email(to_email, subject, body):
    if not to_email or not SMTP_USER or "ваш_" in SMTP_USER: return
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

# --- 🔐 ЛОГІН (ЧЕРЕЗ БІТРІКС) ---
@app.post("/api/login")
async def login(data: Dict[str, str] = Body(...)):
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()
    is_auto = data.get("is_auto", False)

    if not email: return {"status": "error", "message": "Email не вказано"}

    # 1. Шукаємо менеджера в базі Бітрікс
    manager = find_manager_by_email(email)

    if not manager:
        return {"status": "error", "message": "Користувача не знайдено"}

    # 2. Перевіряємо пароль (з поля Бітрікс)
    stored_pass = manager.get(MGR_FIELD_PASS)
    
    # Якщо це не авто-вхід, звіряємо пароль
    if not is_auto and str(stored_pass) != str(password):
        return {"status": "error", "message": "Невірний пароль"}

    return {
        "status": "success",
        "name": manager["title"], # Ім'я з картки
        "email": email,
        "phone": "" 
    }

# --- 📝 СТВОРЕННЯ ЗАЯВКИ (+ ДЗВІНОЧОК) ---
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
        
        # 🔔 ДЗВІНОЧОК ДЛЯ МЕД. ВІДДІЛУ
        notify_msg = f"🚨 Нова рекламація #{new_id}!\nКлієнт: {client}\nМенеджер: {manager}"
        for uid in MED_DEPT_USER_IDS:
            send_bitrix_notification(uid, notify_msg)

        # ✈️ СПОВІЩЕННЯ В ТЕЛЕГРАМ (МЕНЕДЖЕРУ)
        if manager_email:
            mgr = find_manager_by_email(manager_email)
            if mgr:
                tg_id = mgr.get(MGR_FIELD_TG_ID)
                if tg_id:
                    send_telegram(tg_id, f"✅ <b>Заявка #{new_id} прийнята!</b>\nМи сповістимо вас про зміни.")
        
        # Адміну
        if TG_ADMIN_CHAT_ID:
            send_telegram(TG_ADMIN_CHAT_ID, f"📝 Створено заявку #{new_id}")

        return {"status": "success", "id": new_id}
    except Exception as e:
        raise HTTPException(500, str(e))

# --- 2. СИНХРОНІЗАЦІЯ СТАТУСІВ ---
@app.post("/api/sync_status")
async def sync_status(data: Dict[str, List[int]] = Body(...)):
    ids = data.get('ids', [])
    if not ids: return {"items": []}
    try:
        payload = {"entityTypeId": SMART_PROCESS_ID, "filter": {"@id": ids}, "select": ["id", "stageId"]}
        response = requests.post(f"{BITRIX_WEBHOOK_URL}crm.item.list", json=payload)
        result = response.json()
        if "error" in result: return {"items": []}
        return {"items": result['result']['items']}
    except Exception:
        return {"items": []}




# --- 3. ОТРИМАННЯ КОМЕНТАРІВ (З ІМЕНАМИ - FINAL) ---
@app.post("/api/get_comments")
async def get_comments(data: Dict[str, int] = Body(...)):
    item_id = data.get('id')
    if not item_id: return {"comments": []}
    try:
        payload = {
            "filter": {"ENTITY_ID": item_id, "ENTITY_TYPE": f"dynamic_{SMART_PROCESS_ID}", "TYPE_ID": "COMMENT"},
            "order": {"ID": "DESC"}
        }
        response = requests.post(f"{BITRIX_WEBHOOK_URL}crm.timeline.comment.list", json=payload)
        result = response.json()
        if "error" in result: return {"comments": []}

        raw_comments = result['result']
        comments = []
        user_cache = {} 

        for c in raw_comments:
            author_id = c.get('AUTHOR_ID')
            author_name = "Медичний відділ"
            if author_id:
                if author_id in user_cache: author_name = user_cache[author_id]
                else:
                    try:
                        u_res = requests.get(f"{BITRIX_WEBHOOK_URL}user.get", params={"ID": author_id})
                        u_data = u_res.json()
                        if "result" in u_data and u_data["result"]:
                            user = u_data["result"][0]
                            full_name = f"{user.get('NAME', '')} {user.get('LAST_NAME', '')}".strip()
                            if full_name:
                                author_name = full_name
                                user_cache[author_id] = author_name
                    except: pass 
            
            comments.append({
                "id": c['ID'],
                "text": c['COMMENT'],
                "author": author_name,
                "date": c['CREATED']
            })
        return {"comments": comments}
    except Exception: return {"comments": []}

# --- 5. ОТРИМАННЯ ІСТОРІЇ (FIXED) ---
@app.post("/api/get_history")
async def get_history(email: str = Form(...)):
    print(f"SEARCHING HISTORY FOR: {email}") # Лог для перевірки
    try:
        # Перевірка на пустий email
        if not email:
            print("Email is empty")
            return {"history": []}

        # Питаємо Бітрікс
        payload = {
            "entityTypeId": SMART_PROCESS_ID,
            "filter": { FIELD_MANAGER_EMAIL: email }, 
            "select": ["id", "title", "stageId", "createdTime"],
            "order": { "id": "DESC" }
        }
        
        r = requests.post(f"{BITRIX_WEBHOOK_URL}crm.item.list", json=payload)
        
        # Якщо Бітрікс повернув не 200 або не JSON
        if r.status_code != 200:
            print(f"Bitrix HTTP Error: {r.status_code} - {r.text}")
            return {"history": []}
            
        data = r.json()

        # Якщо Бітрікс повернув помилку API (наприклад, невірне поле)
        if "error" in data:
            print(f"Bitrix API Error: {data}")
            return {"history": []}

        history = []
        if "result" in data and "items" in data["result"]:
            for item in data["result"]["items"]:
                stage = item.get("stageId", "")
                status_text = "В обробці"
                status_color = "text-yellow-600"
                
                # Визначаємо статус
                if any(x in stage for x in ["WON", "SUCCESS", "ВИКОНАНО", "УСПІХ"]):
                    status_text = "Вирішено"
                    status_color = "text-green-600"
                elif any(x in stage for x in ["FAIL", "LOSE", "ВІДМОВА", "ПРОВАЛ"]):
                    status_text = "Відмовлено"
                    status_color = "text-red-600"
                elif any(x in stage for x in ["NEW", "НОВА", "BEGIN"]):
                     status_text = "Нова"
                     status_color = "text-blue-600"

                history.append({
                    "id": item["id"],
                    "title": item["title"],
                    "date": item["createdTime"][:10],
                    "status": status_text,
                    "color": status_color
                })
        
        print(f"Found {len(history)} items")
        return {"history": history}

    except Exception as e:
        print(f"CRITICAL HISTORY ERROR: {e}")
        # Повертаємо пустий список, щоб фронтенд не ламався
        return {"history": []}

# --- 6. ДОДАВАННЯ КОМЕНТАРЯ (ЧАТ) ---
class CommentModel(BaseModel):
    id: int
    message: str
    author: str

@app.post("/api/add_comment")
async def add_comment(data: CommentModel):
    try:
        # Форматуємо текст, щоб було видно, хто писав
        formatted_message = f"👨‍💻 <b>{data.author}</b> (Менеджер):<br>{data.message}"
        
        # Відправляємо в Бітрікс (Timeline)
        # ENTITY_TYPE="dynamic_{ID}", де ID - це номер вашого смарт-процесу (1038)
        r = requests.post(f"{BITRIX_WEBHOOK_URL}crm.timeline.comment.add", json={
            "fields": {
                "ENTITY_ID": data.id,
                "ENTITY_TYPE": "dynamic_1038", 
                "COMMENT": formatted_message
            }
        })
        
        result = r.json()
        
        if "result" in result:
            return {"status": "ok"}
        else:
            print(f"Bitrix Error: {result}")
            return {"status": "error", "message": "Bitrix rejected"}

    except Exception as e:
        print(f"Add Comment Error: {e}")
        return {"status": "error", "message": str(e)}

# --- 7. ОТРИМАННЯ ДЕТАЛЕЙ ЗАЯВКИ (НОВЕ) ---
@app.post("/api/get_claim_details")
async def get_claim_details(data: Dict[str, int] = Body(...)):
    item_id = data.get('id')
    if not item_id: return {"status": "error"}

    try:
        # Запитуємо конкретну заявку
        r = requests.post(f"{BITRIX_WEBHOOK_URL}crm.item.get", json={
            "entityTypeId": SMART_PROCESS_ID,
            "id": item_id
        })
        res = r.json()
        
        if "result" not in res:
            return {"status": "error"}

        item = res['result']['item']
        
        # Визначаємо статус для краси
        stage = item.get("stageId", "")
        status_text = "В обробці"
        if any(x in stage for x in ["WON", "SUCCESS", "ВИКОНАНО", "УСПІХ"]): status_text = "Вирішено"
        elif any(x in stage for x in ["FAIL", "LOSE", "ВІДМОВА"]): status_text = "Відмовлено"
        elif any(x in stage for x in ["NEW", "НОВА"]): status_text = "Нова"

        # Формуємо красиву відповідь, використовуючи ваші коди полів
        return {
            "status": "ok",
            "data": {
                "id": item.get("id"),
                "title": item.get("title"),
                "product": item.get(FIELDS_MAP["product"]),
                "lot": item.get(FIELDS_MAP["lot"]),
                "client": item.get("title").replace("Рекламація: ", ""), # Витягуємо ім'я з заголовка
                "details": item.get(FIELDS_MAP["details"]), # Текст анкети
                "status_text": status_text
            }
        }
    except Exception as e:
        print(f"Details Error: {e}")
        return {"status": "error"}

# --- 4. WEBHOOK ВІД БІТРІКС (РОЗДІЛЕННЯ ПОТОКІВ) ---
@app.post("/api/webhook/status_update")
async def status_update(
    id: str,
    stage_id: str
):
    # --- НАЛАШТУВАННЯ ---
    # Сюди будуть падати листи про НОВІ заявки
    EMAIL_MED_DEPT = "itd@emet.in.ua"  # <--- ВПИШІТЬ ТУТ ПОШТУ ВІДДІЛУ
    
    # Посилання на ваш Бітрікс (щоб лікарі могли клікнути і перейти до заявки)
    # Замініть 'your-domain' на вашу адресу (наприклад: emet.bitrix24.ua)
    LINK_TO_CRM = f"https://bitrix.emet.in.ua/crm/type/{SMART_PROCESS_ID}/details"

    try:
        print(f"Webhook received: ID={id}, STAGE={stage_id}") 

        # 1. ЧИСТИМО ID
        if "_" in id:
            clean_id = id.split("_")[-1]
        else:
            clean_id = id
        clean_id = "".join(filter(str.isdigit, clean_id))
        
        if not clean_id:
            return {"status": "error", "message": "Invalid ID"}

        real_id = int(clean_id) 

        # 2. АНАЛІЗ СТАДІЇ
        stage_upper = stage_id.upper()
        
        # Словник синонімів для стадій
        is_new = "NEW" in stage_upper or "НОВА" in stage_upper or "BEGIN" in stage_upper or "START" in stage_upper
        is_success = "WON" in stage_upper or "SUCCESS" in stage_upper or "CLIENT" in stage_upper or "ВЫПОЛНЕНО" in stage_upper or "ВИКОНАНО" in stage_upper
        is_fail = "FAIL" in stage_upper or "LOSE" in stage_upper or "REJECT" in stage_upper or "ВІДМОВА" in stage_upper or "ПРОВАЛ" in stage_upper

        if is_new or is_success or is_fail:
            # Запитуємо дані заявки
            r = requests.post(f"{BITRIX_WEBHOOK_URL}crm.item.get", json={
                "entityTypeId": SMART_PROCESS_ID,
                "id": real_id
            })
            item_data = r.json()
            
            if "result" in item_data:
                item = item_data['result']['item']
                manager_mail = item.get(FIELD_MANAGER_EMAIL)
                client_name = item.get("title", "Без назви")
                
                # --- СЦЕНАРІЙ 1: НОВА ЗАЯВКА -> МЕД. ВІДДІЛ ---
                if is_new:
                    subject = f"Нова рекламація #{real_id} від {client_name}"
                    body = f"""
                    <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
                        <h2 style="color: #2563eb;">Поступила нова рекламація</h2>
                        <p><b>Номер:</b> #{real_id}</p>
                        <p><b>Клієнт:</b> {client_name}</p>
                        <p>Будь ласка, розгляньте звернення та прийміть рішення.</p>
                        <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
                        <a href="{LINK_TO_CRM}/{real_id}/" style="background: #2563eb; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">Відкрити в CRM</a>
                    </div>
                    """
                    send_email(EMAIL_MED_DEPT, subject, body)
                    print(f"New Ticket Email sent to MED DEPT: {EMAIL_MED_DEPT}")

                # --- СЦЕНАРІЙ 2: РІШЕННЯ -> МЕНЕДЖЕР ---
                elif (is_success or is_fail) and manager_mail:
                    status_text = "✅ ВИРІШЕНО" if is_success else "❌ ВІДМОВЛЕНО"
                    color = "#22c55e" if is_success else "#ef4444"
                    app_link = "https://emet-service.vercel.app/" # Ваше посилання
                    
                    body = f"""
                    <div style="font-family: Arial, sans-serif; padding: 20px; border: 1px solid #eee; border-radius: 10px;">
                        <h2 style="color: {color};">Статус рекламації оновлено</h2>
                        <p>Заявка <b>#{real_id}</b> ({client_name}) перейшла у статус:</p>
                        <h1 style="color: {color}; margin: 20px 0;">{status_text}</h1>
                        <p>Зайдіть у Service Desk, щоб переглянути деталі.</p>
                        <hr style="border: 0; border-top: 1px solid #eee; margin: 20px 0;">
                        <a href="{app_link}" style="background: #2563eb; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; display: inline-block;">Перейти до заявки</a>
                    </div>
                    """
                    send_email(manager_mail, f"Результат заявки #{real_id} [{status_text}]", body)
                    print(f"Result Email sent to MANAGER: {manager_mail}")

        return {"status": "ok"}

    except Exception as e:
        print(f"Webhook Error: {e}")
        # Повертаємо OK, щоб Бітрікс не панікував
        return {"status": "ok", "error": str(e)}

