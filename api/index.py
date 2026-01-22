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

# --- НАЛАШТУВАННЯ СПОВІЩЕНЬ (ЗАПОВНІТЬ СВОЇ ДАНІ) ---
TG_BOT_TOKEN = "ВАШ_ТОКЕН"
TG_CHAT_ID = "ВАШ_CHAT_ID" 
FIELD_MANAGER_EMAIL = "ufCrm4_1769090000" # Замініть на реальний код поля Email менеджера!

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
