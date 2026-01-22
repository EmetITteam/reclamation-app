import base64
import json
import requests
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from typing import List, Optional

app = FastAPI()

# --- ВАШІ НАЛАШТУВАННЯ ---
BITRIX_WEBHOOK_URL = "https://bitrix.emet.in.ua/rest/2049/24pv36uotghswqwa/"
SMART_PROCESS_ID = 1038

# --- ПРАВИЛЬНІ КОДИ (з вашої консолі) ---
FIELDS_MAP = {
    "title": "title",                      # Стандартне поле (маленькими)
    "lot": "ufCrm4_1769003758",            # LOT
    "invoice": "ufCrm4_1769003770",        # № Реалізації
    "details": "ufCrm4_1769003784",        # Деталі анкети
    "files": "ufCrm4_1769005413",          # Медіа докази
    "manager": "ufCrm4_1769005441",        # Менеджер
    "product": "ufCrm4_1769005557",        # Препарат
    "claim_type": "ufCrm4_1769005573"      # Тип рекламації
}

# Перекладач
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

        # 2. Перекладаємо тип
        readable_type = TYPE_TRANSLATION.get(type, type)

        # 3. Збираємо поля
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

        # 4. Обробка файлів
        if files:
            file_data_list = []
            for file in files:
                content = await file.read()
                b64 = base64.b64encode(content).decode('utf-8')
                file_data_list.append({
                    "fileData": [file.filename, b64]
                })
            
            bx_fields[FIELDS_MAP["files"]] = file_data_list

        # 5. Відправка
        payload = {
            "entityTypeId": SMART_PROCESS_ID,
            "fields": bx_fields
        }

        response = requests.post(f"{BITRIX_WEBHOOK_URL}crm.item.add", json=payload)
        result = response.json()

        if "error" in result:
            print("Bitrix Error:", result)
            raise HTTPException(status_code=500, detail=f"Помилка Бітрикс: {result.get('error_description')}")

        return {"status": "success", "id": result['result']['item']['id']}

    except Exception as e:
        print("Server Error:", str(e))
        raise HTTPException(status_code=500, detail=str(e))
