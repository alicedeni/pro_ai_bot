"""
Скрипт для экспорта данных пользователей в CSV файл
"""
import json
import csv
from pathlib import Path
from datetime import datetime

DATA_FILE = Path("user_data.json")
OUTPUT_FILE = Path("exported_data.csv")


def export_to_csv():
    """Экспортирует данные пользователей в CSV файл"""
    if not DATA_FILE.exists():
        print(f"Файл {DATA_FILE} не найден!")
        return
    
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        user_data = json.load(f)
    
    if not user_data:
        print("Нет данных для экспорта.")
        return
    
    # Подготавливаем данные для CSV
    rows = []
    for user_id, data in user_data.items():
        row = {
            "ID пользователя": user_id,
            "Имя пользователя": data.get("username", ""),
            "Полное имя": data.get("full_name", ""),
            "Номер розыгрыша": data.get("raffle_number", ""),
            "Начало квеста": data.get("started_at", ""),
            "Завершение квеста": data.get("completed_at", ""),
        }
        
        # Добавляем ответы на вопросы
        answers = data.get("answers", {})
        for i in range(6):
            answer_data = answers.get(str(i), {})
            row[f"Ответ на задание {i+1}"] = answer_data.get("answer", "")
            row[f"Время ответа {i+1}"] = answer_data.get("timestamp", "")
        
        rows.append(row)
    
    # Записываем в CSV
    if rows:
        fieldnames = [
            "ID пользователя", "Имя пользователя", "Полное имя", "Номер розыгрыша",
            "Начало квеста", "Завершение квеста",
            "Ответ на задание 1", "Время ответа 1",
            "Ответ на задание 2", "Время ответа 2",
            "Ответ на задание 3", "Время ответа 3",
            "Ответ на задание 4", "Время ответа 4",
            "Ответ на задание 5", "Время ответа 5",
            "Ответ на задание 6", "Время ответа 6",
        ]
        
        # Для корректного открытия в Excel (русская локаль) используем cp1251 и разделитель ;
        with open(OUTPUT_FILE, "w", newline="", encoding="cp1251") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=";")
            writer.writeheader()
            writer.writerows(rows)
        
        print(f"✅ Данные успешно экспортированы в {OUTPUT_FILE}")
        print(f"📊 Всего пользователей: {len(rows)}")
    else:
        print("Нет данных для экспорта.")


if __name__ == "__main__":
    export_to_csv()
