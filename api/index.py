import base64
import json
import requests
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from typing import List, Optional

app = FastAPI()

# --- ВАШІ НАЛАШТУВАННЯ ---
BITRIX_WEBHOOK_URL = "https://bitrix.emet.in.ua/rest/2049/24pv36uotghswqwa/"
SMART_PROCESS_ID = 1038

# --- ОНОВЛЕНІ КОДИ ПОЛІВ (Згідно з вашим повідомленням) ---
FIELDS_MAP = {
    "title": "TITLE",
    "lot": "UF_CRM_4_1769003758",         # LOT (Рядок)
    "invoice": "UF_CRM_4_1769003770",     # № Реалізації (Рядок)
    "details": "UF_CRM_4_1769003784",     # Деталі анкети (Рядок)
    
    # Нові коди:
    "files": "UF_CRM_4_1769005413",       # Медіа докази (Файл)
    "manager": "UF_CRM_4_1769005441",     # Менеджер (Рядок)
    "product": "UF_CRM_4_1769005557",     # Препарат (Рядок)
    "claim_type": "UF_CRM_4_1769005573"   # Тип рекламації (Рядок)
}

# Перекладач кодів сайту в зрозумілий текст для Бітрікса
TYPE_TRANSLATION = {
    "defect_pack": "Неякісна упаковка",
    "quality": "Якість препарату",
    "effectiveness": "Ефективність",
    "side_effect": "Побічна дія",
    "complication": "Ускладнення",
    "other": "Інше"
}

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
        # 1. Формуємо текст анкети
        details_dict = json.loads(details)
        formatted_text = "--- ДЕТАЛІ ЗАЯВКИ ---\n"
        for question, answer in details_dict.items():
            formatted_text += f"{question}:\n{answer}\n\n"

        # 2. Перекладаємо тип (наприклад, defect_pack -> Неякісна упаковка)
        readable_type = TYPE_TRANSLATION.get(type, type)

        # 3. Збираємо основні поля
        bx_fields = {
            FIELDS_MAP["title"]: f"Рекламація: {client}",
            FIELDS_MAP["product"]: product,          # Текст
            FIELDS_MAP["claim_type"]: readable_type, # Текст
            FIELDS_MAP["lot"]: lot,
            FIELDS_MAP["invoice"]: invoice or "Не вказано",
            FIELDS_MAP["details"]: formatted_text,
            FIELDS_MAP["manager"]: manager,
            "OPENED": "Y"
        }

        # 4. Обробка файлів (завантажуємо в поле Медіа докази)
        if files:
            file_data_list = []
            for file in files:
                content = await file.read()
                # Кодуємо файл у base64 для передачі в Бітрікс
                b64 = base64.b64encode(content).decode('utf-8')
                file_data_list.append({
                    "fileData": [file.filename, b64]
                })
            
            # Додаємо файли до полів
            bx_fields[FIELDS_MAP["files"]] = file_data_list

        # 5. Відправка запиту в Бітрікс
        payload = {
            "entityTypeId": SMART_PROCESS_ID,
            "fields": bx_fields
        }

        response = requests.post(f"{BITRIX_WEBHOOK_URL}crm.item.add", json=payload)
        result = response.json()

        # 6. Обробка відповіді
        if "error" in result:
            print("Bitrix Error:", result)
            raise HTTPException(status_code=500, detail=f"Помилка Бітрикс: {result.get('error_description')}")

        return {"status": "success", "id": result['result']['item']['id']}

    except Exception as e:
        print("Server Error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
