import os
from groq import Groq
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

def main():
    print("AI Clipper Agent запущен и готов к работе!")
    
    # Проверка наличия Groq API ключа
    api_key = os.getenv("GROQ_API_KEY")
    if api_key:
        print("Groq API ключ успешно обнаружен.")
    else:
        print("Внимание: GROQ_API_KEY не найден в переменных окружения.")

if __name__ == "__main__":
    main()
