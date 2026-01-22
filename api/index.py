import base64
import json
import requests
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Body
from typing import List, Optional, Dict, Any

app = FastAPI()

# --- ВАШИ НАЛАШТУВАННЯ ---
BITRIX_WEBHOOK_URL = "https://bitrix.emet.in.ua/rest/2049/24pv36uotghswqwa/"
SMART_PROCESS_ID = 1038

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

# 1. СТВОРЕННЯ ЗАЯВКИ
@app.post("/api/submit_claim")
async def submit_claim(
    type: str = Form(...),
    client: str = Form(...),
    product: str = Form(...),
    lot: str = Form(...),
    manager: str = Form(...),
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

        return {"status": "success", "id": result['result']['item']['id']}

    except Exception as e:
        print("Server Error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))

# 2. СИНХРОНІЗАЦІЯ СТАТУСІВ (ОНОВЛЕННЯ ТА ВИДАЛЕННЯ)
@app.post("/api/sync_status")
async def sync_status(data: Dict[str, List[int]] = Body(...)):
    # Отримуємо список ID з телефону: [1, 2, 3]
    ids = data.get('ids', [])
    if not ids:
        return {"items": []}

    try:
        # Питаємо у Бітрікс про ці ID
        payload = {
            "entityTypeId": SMART_PROCESS_ID,
            "filter": {"@id": ids},
            "select": ["id", "stageId"] # Нам потрібен тільки статус
        }
        
        response = requests.post(f"{BITRIX_WEBHOOK_URL}crm.item.list", json=payload)
        result = response.json()
        
        if "error" in result:
            return {"items": []}

        # Повертаємо тільки ті, що існують. Ті, що видалені в Бітрікс, сюди не потраплять.
        return {"items": result['result']['items']}

    except Exception:
        return {"items": []}

# 3. ОТРИМАННЯ КОМЕНТАРІВ
@app.post("/api/get_comments")
async def get_comments(data: Dict[str, int] = Body(...)):
    item_id = data.get('id')
    if not item_id:
        return {"comments": []}

    try:
        # Отримуємо коментарі з Таймлайну
        payload = {
            "filter": {
                "ENTITY_ID": item_id,
                "ENTITY_TYPE": f"dynamic_{SMART_PROCESS_ID}", # Тип сутності
                "TYPE_ID": "COMMENT" # Тільки коментарі
            },
            "order": {"ID": "DESC"} # Нові зверху
        }

        response = requests.post(f"{BITRIX_WEBHOOK_URL}crm.timeline.comment.list", json=payload)
        result = response.json()

        if "error" in result:
            return {"comments": []}

        comments = []
        for c in result['result']:
            comments.append({
                "id": c['ID'],
                "text": c['COMMENT'],
                "author": c.get('AUTHOR', {}).get('NAME', 'Менеджер'), # Ім'я автора
                "date": c['CREATED']
            })

        return {"comments": comments}

    except Exception:
        return {"comments": []}
