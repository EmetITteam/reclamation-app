import base64
import json
import requests
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from typing import List, Optional

app = FastAPI()

# --- ВАШІ КЛЮЧІ (ВЖЕ ВСТАВЛЕНІ) ---
BITRIX_WEBHOOK_URL = "https://bitrix.emet.in.ua/rest/2049/24pv36uotghswqwa/"
SMART_PROCESS_ID = 1038

# Коди полів (з вашого повідомлення)
FIELDS_MAP = {
    "title": "TITLE",
    "product": "UF_CRM_4_1769003740",     # Препарат
    "lot": "UF_CRM_4_1769003758",         # LOT
    "invoice": "UF_CRM_4_1769003770",     # № Реалізації
    "claim_type": "UF_CRM_4_1769003614",  # Тип рекламації
    "details": "UF_CRM_4_1769003784",     # Деталі анкети
}

# Словник для перекладу кодів сайту в назви Бітрікс (як на ваших скріншотах)
TYPE_MAPPING = {
    "defect_pack": "Неякісна упаковка",  # Як у вас в таблиці
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
    invoice: Optional[str] = Form(None),
    details: str = Form(...),
    files: List[UploadFile] = File(None)
):
    try:
        # 1. Форматуємо анкету
        details_dict = json.loads(details)
        formatted_text = "--- ДЕТАЛІ ЗАЯВКИ ---\n"
        for question, answer in details_dict.items():
            formatted_text += f"{question}:\n{answer}\n\n"

        # 2. Отримуємо правильну назву типу для Бітрикс
        bitrix_type_value = TYPE_MAPPING.get(type, type)

        # 3. Формуємо поля
        bx_fields = {
            FIELDS_MAP["title"]: f"Рекламація: {client} ({bitrix_type_value})",
            FIELDS_MAP["product"]: product,
            FIELDS_MAP["lot"]: lot,
            FIELDS_MAP["invoice"]: invoice or "Не вказано",
            FIELDS_MAP["claim_type"]: bitrix_type_value, 
            FIELDS_MAP["details"]: formatted_text,
            "OPENED": "Y"
        }

        # 4. Обробка файлів (завантажуємо в поле "Деталі анкети" посиланням або окремо, 
        # оскільки для завантаження в поле файлу потрібен складніший метод disk.storage.upload)
        # Для спрощення MVP: ми додамо імена файлів в опис, а самі файли краще вантажити 
        # через окремий метод, але поки спробуємо базову передачу, якщо поле підтримує base64.
        # Якщо ні - файли прийдуть, але можуть не відобразитися без дод. методу.
        if files:
            file_info = "\n\n--- ФАЙЛИ ---\n"
            file_data_list = []
            for file in files:
                content = await file.read()
                b64 = base64.b64encode(content).decode('utf-8')
                file_info += f"Додано файл: {file.filename}\n"
                # Спроба передати файл, якщо поле підтримує (на майбутнє)
                file_data_list.append({"fileData": [file.filename, b64]})
            
            bx_fields[FIELDS_MAP["details"]] += file_info

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
