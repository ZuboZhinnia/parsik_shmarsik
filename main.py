import time
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

# Константи
BASE_URL = "https://www.yakaboo.ua"  # Базова URL для сайту

# Ініціалізація драйвера
def init_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Запуск в безголовому режимі (без відкриття вікна браузера)
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

# Ініціалізація бази даних
def init_db():
    try:
        client.admin.command('ping')
        print("Pinged your deployment. You successfully connected to MongoDB!")
        db = client["books_db"]
        collection = db["books"]
        return db, collection
    except Exception as e:
        print("Помилка з'єднання з MongoDB:", e)
        exit()

# Універсальна функція для пошуку елемента
def find_element(driver, by, value, wait_time=10):
    try:
        element = WebDriverWait(driver, wait_time).until(EC.presence_of_element_located((by, value)))
        return element
    except Exception as e:
        print(f"Помилка при пошуку елемента: {e}")
        return None

# Функція для отримання посилань на книги з видавництва
def get_books_from_publisher(driver, publisher_url):
    driver.get(publisher_url)
    
    # Чекаємо, поки елементи з книгами з'являться на сторінці
    book_links = []
    book_section = find_element(driver, By.CSS_SELECTOR, "#viewport > div.entity-wrapper > div.etm-entity > div.category__content.etm-entity-content > div.category__main > div.category__cards > div")
    
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
        soup = BeautifulSoup(driver.page_source, "html.parser")
        book_links = [BASE_URL + a["href"] for a in soup.select(".category__content .category__main a")]
        print(f"Знайдено {len(book_links)} посилань після зміни селектора.")
    
    return book_links

# Функція для отримання категорій книги
def get_book_categories(category_element):
    if not category_element:
        return "None"
        
    category_links = category_element.select("a")
    if not category_links:
        return category_element.get_text(strip=True).replace("Категорія:", "").strip()
        
    # Зберігаємо вже побачені категорії
    seen_categories = set()
    categories = []

    for link in category_links:
        category_name = link.get_text(strip=True)

        # Додаємо категорію лише якщо її префікс ще не був доданий
        if category_name.lower() not in seen_categories:
            # Перевірка на дублювання за словами
            duplicate_found = False
            for existing_category in seen_categories:
                if category_name.lower() in existing_category.lower() or existing_category.lower() in category_name.lower():
                    duplicate_found = True
                    break
            if not duplicate_found:
                categories.append(category_name)
                seen_categories.add(category_name.lower())

    return ", ".join(categories)

# Функція для отримання обкладинки книги
def get_book_cover(soup):
    cover_div = soup.find('div', class_='slide__item')
    if cover_div:
        img = cover_div.find('img', class_='slide__img')
        if img:
            return img.get('src')
    return 'None'

# Функція для отримання характеристик книги
def get_book_characteristics(char_blocks):
    isbn = None
    author = None
    publisher = None
    year = None
    
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
                    
    return isbn, author, publisher, year

# Функція для парсингу даних про книгу
def parse_book_data(driver, book_url):
    driver.get(book_url)
    
    # Чекаємо, поки завантажиться сторінка книги
    book_section = find_element(driver, By.CSS_SELECTOR, ".char__title")
    
    if not book_section:
        print("Не вдалося знайти необхідні елементи на сторінці книги.")
        return None
        
    soup = BeautifulSoup(driver.page_source, "html.parser")

    # Збираємо дані про книгу
    char_blocks = soup.find_all('div', class_='char')
    isbn, author, publisher, year = get_book_characteristics(char_blocks)
    
    # Витягуємо URL обкладинки
    cover_url = get_book_cover(soup)

    # Витягуємо категорію
    category_element = soup.select_one("#product .product-options.products-options.category-options.product-main-section")
    category = get_book_categories(category_element)

    # Формуємо словник з даними книги
    book_data = {
        'isbn': isbn if isbn else None,
        'author': author if author else 'None',
        'publisher': publisher if publisher else 'None',
        'year': year if year else 'None',
        'cover_url': cover_url,
        'category': category,
        'url': book_url
    }

    return book_data

# Функція для перевірки наявності книги в MongoDB
def is_book_in_db(collection, isbn):
    return collection.find_one({"isbn": isbn}) is not None

# Функція для збереження книги в базу даних
def save_book_to_db(collection, book_data):
    if book_data['isbn'] is None:
        print(f"Книга {book_data['url']} не має ISBN. Пропускаємо.")
        return False

    if is_book_in_db(collection, book_data['isbn']):
        print(f"Книга з ISBN {book_data['isbn']} вже існує в базі даних. Пропускаємо.")
        return False

    # Вставляємо дані в MongoDB
    result = collection.insert_one(book_data)
    print(f"Документ вставлено з id: {result.inserted_id}")
    return True

# Основна функція
def main():
    driver = init_driver()
    db, collection = init_db()
    
    # Встановлюємо URL видавництва для тесту
    publisher_url = 'https://www.yakaboo.ua/ua/book_publisher/view/A_ba_ba_ga_la_ma_ga'

    # Отримуємо всі посилання на книги з видавництва
    book_links = get_books_from_publisher(driver, publisher_url)
    
    if not book_links:
        print("Не знайдено посилань на книги.")
        driver.quit()
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
        book_data = parse_book_data(driver, book_url)
        
        if book_data and save_book_to_db(collection, book_data):
            book_count += 1

    driver.quit()

if __name__ == "__main__":
    main()