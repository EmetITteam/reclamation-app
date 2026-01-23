import base64
import json
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Body
from typing import List, Optional, Dict, Any

app = FastAPI()

# --- ВАШІ НАЛАШТУВАННЯ ---
BITRIX_WEBHOOK_URL = "https://bitrix.emet.in.ua/rest/2049/24pv36uotghswqwa/"
SMART_PROCESS_ID = 1038

# --- НАЛАШТУВАННЯ СПОВІЩЕНЬ ---
TG_BOT_TOKEN = "ВАШ_ТОКЕН_БОТА"  # Отримайте у @BotFather
TG_CHAT_ID = "ВАШ_CHAT_ID"       # ID чату/групи куди падатимуть заявки

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SMTP_USER = "noreply@emet.in.ua"      # З якої пошти відправляти
SMTP_PASS = "cgme lnuf pytd widr" # Пароль додатка (App Password), не від скриньки!

# Вставте сюди код поля, який ви створили у Кроці 1
FIELD_MANAGER_EMAIL = "ufCrm4_1769084999"

# --- БАЗА ДАНИХ МЕНЕДЖЕРІВ ---
MANAGERS_DB = {
    # ТЕСТОВИЙ АКАУНТ
    "itd@emet.in.ua": {"pass": "123", "name": "Евгения Малькова", "phone": "380634457827"},
    # ІНШІ МЕНЕДЖЕРИ
    "sm.kiev4@emet.in.ua": {"pass": "CrmEmet83a", "name": "Бойко Ольга", "phone": "380979590833"},
    "ssm.kharkov1@emet.in.ua": {"pass": "CrmEmet19f", "name": "Золотченко Олена", "phone": "380675228279"},
    "sm.odessa2@emet.in.ua": {"pass": "CrmEmet47z", "name": "Каратеева Олена", "phone": "380676360299"},
    "sm.kherson1@emet.in.ua": {"pass": "CrmEmet92k", "name": "Клименко Марина", "phone": "380673350210"},
    "sm.odessa@emet.in.ua": {"pass": "CrmEmet31p", "name": "Крыжняя Карина", "phone": "380675206991"},
    "sm.kiev@emet.in.ua": {"pass": "CrmEmet68d", "name": "Мигашко Анна", "phone": "380676428988"},
    "rm.odessa@emet.in.ua": {"pass": "CrmEmet75q", "name": "Пашковская Юлия", "phone": "380679216305"},
    "sm.odessa1@emet.in.ua": {"pass": "CrmEmet24h", "name": "Пушкарская Виктория", "phone": "380980797797"},
    "sm.kiev3@emet.in.ua": {"pass": "CrmEmet50w", "name": "Селиванова Виктория", "phone": "380676523343"},
    "sm.kharkov2@emet.in.ua": {"pass": "CrmEmet88c", "name": "Тесленко Мария", "phone": "380981812070"},
    "sm.kiev6@emet.in.ua": {"pass": "CrmEmet13j", "name": "Ткаченко Юлия", "phone": "380673320440"},
    "sm.vinnitsa@emet.in.ua": {"pass": "CrmEmet62t", "name": "Фиголь / Претолюк Илона", "phone": "380671967707"},
    "sm.dnepr2@emet.in.ua": {"pass": "CrmEmet53g", "name": "Сирик Людмила", "phone": "380678800286"},
    "sm.kiev8@emet.in.ua": {"pass": "CrmEmet70y", "name": "Некова Катерина", "phone": "380671100901"},
    "sm.zhytomyr2@emet.in.ua": {"pass": "CrmEmet16m", "name": "Войналович Алёна", "phone": "380677875549"},
    "sm.zp@emet.in.ua": {"pass": "CrmEmet41v", "name": "Бакумова Алина", "phone": "380675660356"},
    "rm.zp@emet.in.ua": {"pass": "CrmEmet89e", "name": "Андрющенко Юлия", "phone": "380675707868"},
    "sm.dnepr3@emet.in.ua": {"pass": "CrmEmet36n", "name": "Фещенко Анна", "phone": "380675228219"},
    # Ті, для кого не було контактів у другому списку (Додайте імена вручну при потребі):
    "sm.odessa3@emet.in.ua": {"pass": "CrmEmet22s", "name": "Латій", "phone": ""},
    "sm.dnepr4@emet.in.ua": {"pass": "CrmEmet57x", "name": "Эмцева", "phone": ""},
    "sm.nikolaev@emet.in.ua": {"pass": "CrmEmet91c", "name": "Верланова", "phone": ""},
    "sm.zp2@emet.in.ua": {"pass": "CrmEmet25b", "name": "Шевченко", "phone": ""},
    "sm.vinnitsa2@emet.in.ua": {"pass": "CrmEmet33w", "name": "Рабищук", "phone": ""}
}

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

# --- 0. АВТОРИЗАЦІЯ ---
@app.post("/api/login")
async def login(data: Dict[str, str] = Body(...)):
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()
    is_auto = data.get("is_auto", False) # Якщо вхід по посиланню

    if not email:
        return {"status": "error", "message": "Email не вказано"}

    user_data = MANAGERS_DB.get(email)

    if not user_data:
        return {"status": "error", "message": "Користувача не знайдено"}

    # Якщо вхід не автоматичний (по посиланню), перевіряємо пароль
    if not is_auto and user_data["pass"] != password:
        return {"status": "error", "message": "Невірний пароль"}

    return {
        "status": "success",
        "name": user_data["name"],
        "email": email,
        "phone": user_data["phone"]
    }

# --- 1. СТВОРЕННЯ ЗАЯВКИ ---
@app.post("/api/submit_claim")
async def submit_claim(
    type: str = Form(...),
    client: str = Form(...),
    product: str = Form(...),
    lot: str = Form(...),
    manager: str = Form(...),
    manager_email: Optional[str] = Form(None), # Отримуємо Email менеджера
    invoice: Optional[str] = Form(None),
    details: str = Form(...),
    files: List[UploadFile] = File(None)
):
    try:
        details_dict = json.loads(details)
        formatted_text = "--- ДЕТАЛІ ЗАЯВКИ ---\n"
        for question, answer in details_dict.items():
            formatted_text += f"{question}:\n{answer}\n\n"

        readable_type = TYPE_TRANSLATION.get(type, type)

        bx_fields = {
            FIELDS_MAP["title"]: f"Рекламація: {client}",
            FIELDS_MAP["product"]: product,
            FIELDS_MAP["claim_type"]: readable_type,
            FIELDS_MAP["lot"]: lot,
            FIELDS_MAP["invoice"]: invoice or "Не вказано",
            FIELDS_MAP["details"]: formatted_text,
            FIELDS_MAP["manager"]: manager,
            "OPENED": "Y"
        }
        
        # Додаємо email менеджера в приховане поле, якщо воно налаштоване
        if manager_email and FIELD_MANAGER_EMAIL != "ufCrm4_1769090000":
             bx_fields[FIELD_MANAGER_EMAIL] = manager_email

        if files:
            file_data_list = []
            for file in files:
                content = await file.read()
                b64 = base64.b64encode(content).decode('utf-8')
                file_data_list.append([file.filename, b64])
            bx_fields[FIELDS_MAP["files"]] = file_data_list

        payload = {
            "entityTypeId": SMART_PROCESS_ID,
            "fields": bx_fields
        }

        response = requests.post(f"{BITRIX_WEBHOOK_URL}crm.item.add", json=payload)
        result = response.json()

        if "error" in result:
            raise HTTPException(status_code=500, detail=f"Помилка Бітрикс: {result.get('error_description')}")
        
        new_id = result['result']['item']['id']
        
        # Сповіщення в Телеграм
        tg_text = f"🚨 <b>Нова рекламація #{new_id}</b>\n\n👤 Від: {manager}\n🏥 Клієнт: {client}\n💊 Препарат: {product}\n📄 Тип: {readable_type}"
        send_telegram(tg_text)

        return {"status": "success", "id": new_id}

    except Exception as e:
        print("Server Error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))

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

# --- 5. ОТРИМАННЯ ІСТОРІЇ ЗА EMAIL ---
@app.post("/api/get_history")
async def get_history(email: str = Form(...)):
    try:
        # Питаємо Бітрікс: дай список, де Email Менеджера = email
        r = requests.post(f"{BITRIX_WEBHOOK_URL}crm.item.list", json={
            "entityTypeId": SMART_PROCESS_ID,
            "filter": { FIELD_MANAGER_EMAIL: email }, # Фільтруємо по нашому полю
            "select": ["id", "title", "stageId", "createdTime"], # Беремо тільки потрібне
            "order": { "id": "DESC" } # Сортуємо: найновіші зверху
        })
        data = r.json()

        history = []
        if "result" in data and "items" in data["result"]:
            for item in data["result"]["items"]:
                # Розшифровуємо стадію для краси (можна додати свої коди)
                stage = item.get("stageId", "")
                status_text = "В обробці"
                status_color = "text-yellow-600" # Жовтий
                
                if "WON" in stage or "SUCCESS" in stage or "ВИКОНАНО" in stage:
                    status_text = "Вирішено"
                    status_color = "text-green-600"
                elif "FAIL" in stage or "LOSE" in stage or "ВІДМОВА" in stage:
                    status_text = "Відмовлено"
                    status_color = "text-red-600"
                elif "NEW" in stage:
                     status_text = "Нова"
                     status_color = "text-blue-600"

                history.append({
                    "id": item["id"],
                    "title": item["title"],
                    "date": item["createdTime"][:10], # Тільки дата (без часу)
                    "status": status_text,
                    "color": status_color
                })
        
        return {"history": history}

    except Exception as e:
        print(f"History Error: {e}")
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

