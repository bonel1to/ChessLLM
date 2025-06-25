import os
from dotenv import load_dotenv
load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
if not OPENROUTER_API_KEY:
    raise ValueError(
        "OPENROUTER_API_KEY не найден в переменных окружения!\n"
        "Добавьте ключ в переменные окружения или создайте файл .env с содержимым: OPENROUTER_API_KEY=ваш_ключ"
    )

