import time
import json
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi

# Підключення до MongoDB Atlas
uri = "mongodb+srv://dobryy_surfer:1Tsv3ry1mp0rtant!@surfer-cluster-2.erpms.mongodb.net/?retryWrites=true&w=majority&appName=Surfer-Cluster-2"
client = MongoClient(uri, server_api=ServerApi('1'))

try:
    client.admin.command('ping')
    print("Pinged your deployment. You successfully connected to MongoDB!")
except Exception as e:
    print("Помилка з'єднання з MongoDB:", e)
    exit()

# Вибір бази даних та колекції
db = client["books_db"]
collection = db["books"]

# Налаштування для Selenium
chrome_options = Options()
chrome_options.add_argument("--headless")  # Запуск в безголовому режимі (без відкриття вікна браузера)
chrome_options.add_argument("--disable-gpu")
chrome_options.add_argument("--no-sandbox")
driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

BASE_URL = "https://www.yakaboo.ua"  # Базова URL для сайту

# Універсальна функція для пошуку елемента
def find_element(by, value, wait_time=10):
    try:
        element = WebDriverWait(driver, wait_time).until(EC.presence_of_element_located((by, value)))
        return element
    except Exception as e:
        print(f"Помилка при пошуку елемента: {e}")
        return None

# Функція для отримання посилань на книги з видавництва
def get_books_from_publisher(publisher_url):
    driver.get(publisher_url)
    
    # Чекаємо, поки елементи з книгами з'являться на сторінці
    book_links = []
    book_section = find_element(By.CSS_SELECTOR, "#viewport > div.entity-wrapper > div.etm-entity > div.category__content.etm-entity-content > div.category__main > div.category__cards > div")
    
    if book_section:
        soup = BeautifulSoup(driver.page_source, "html.parser")
        print(f"Отримано HTML сторінки видавництва: {publisher_url}")
        book_links = [BASE_URL + a["href"] for a in soup.select(".category__cards .category__item a")]
        print(f"Знайдено {len(book_links)} посилань на книги.")
    else:
        print("Не вдалося знайти секцію з книгами на сторінці видавництва.")
    
    # Якщо посилання не знайдено, пробуємо інший селектор
    if not book_links:
        print("Спробуємо інший селектор для посилань на книги.")
        book_links = [BASE_URL + a["href"] for a in soup.select(".category__content .category__main a")]
        print(f"Знайдено {len(book_links)} посилань після зміни селектора.")
    
    return book_links

# Функція для парсингу даних про книгу
def parse_book_data(book_url):
    driver.get(book_url)
    
    # Чекаємо, поки завантажиться сторінка книги
    book_section = find_element(By.CSS_SELECTOR, ".char__title")
    
    if book_section:
        soup = BeautifulSoup(driver.page_source, "html.parser")
        print(f"Парсимо книгу: {book_url}")
    
        # Збираємо дані про книгу
        isbn = None
        author = None
        publisher = None
        year = None
        cover_url = None

        char_blocks = soup.find_all('div', class_='char')

        for block in char_blocks:
            title_element = block.find('div', class_='char__title')
            if title_element:
                title_text = title_element.get_text(strip=True)
                value_element = block.find('div', class_='char__value')
                if value_element:
                    value_text = value_element.get_text(strip=True)
                    if 'ISBN' in title_text:
                        isbn = value_text
                    elif 'Автор' in title_text:
                        author = value_text
                    elif 'Видавництво' in title_text:
                        publisher = value_text
                    elif 'Рік видання' in title_text:
                        year = value_text

        # Витягуємо URL обкладинки
        cover_div = soup.find('div', class_='slide__item')
        if cover_div:
            img = cover_div.find('img', class_='slide__img')
            if img:
                cover_url = img.get('src')

        # Формуємо словник з даними книги
        book_data = {
            'isbn': isbn if isbn else 'None',
            'author': author if author else 'None',
            'publisher': publisher if publisher else 'None',
            'year': year if year else 'None',
            'cover_url': cover_url if cover_url else 'None'
        }

        return book_data
    else:
        print("Не вдалося знайти необхідні елементи на сторінці книги.")
        return None

# Функція для перевірки наявності книги в MongoDB
def is_book_in_db(isbn):
    return collection.find_one({"isbn": isbn}) is not None

# Основна функція
def main():
    # Встановлюємо URL видавництва для тесту
    publisher_url = 'https://www.yakaboo.ua/ua/book_publisher/view/A_ba_ba_ga_la_ma_ga'

    # Отримуємо всі посилання на книги з видавництва
    book_links = get_books_from_publisher(publisher_url)
    
    if not book_links:
        print("Не знайдено посилань на книги.")
        return

    # Лічильник для обмеження кількості книг до 5
    book_count = 0
    max_books = 5

    # Парсимо кожну книгу та зберігаємо дані в MongoDB
    for book_url in book_links:
        if book_count >= max_books:
            print("Досягнуто ліміту в 5 книг. Завершення...")
            break

        print(f"Парсимо книгу: {book_url}")
        book_data = parse_book_data(book_url)
        
        if book_data:
            # Перевіряємо, чи книга вже є в базі даних
            if is_book_in_db(book_data['isbn']):
                print(f"Книга з ISBN {book_data['isbn']} вже існує в базі даних. Пропускаємо.")
                continue

            # Вставляємо дані в MongoDB
            result = collection.insert_one(book_data)
            print(f"Документ вставлено з id: {result.inserted_id}")

            # Додаємо _id до даних як рядок, якщо хочемо його зберегти
            book_data['_id'] = str(result.inserted_id)

            # Опційно: зберегти дані у JSON-файл для локального збереження
            with open('books_data.json', 'w', encoding='utf-8') as json_file:
                json.dump([book_data], json_file, ensure_ascii=False, indent=4)
            print("Дані збережено в books_data.json")

            book_count += 1

    driver.quit()

if __name__ == "__main__":
    main()
