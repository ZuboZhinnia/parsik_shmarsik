import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
from statistics import mean
from pymongo.mongo_client import MongoClient
from pymongo.server_api import ServerApi
import os
from dotenv import load_dotenv

# Завантаження змінних середовища (.env) для безпеки
load_dotenv()

# MongoDB з'єднання через змінні середовища
uri = os.getenv("MONGODB_URI", "mongodb+srv://dobryy_surfer:1Tsv3ry1mp0rtant!@surfer-cluster-2.erpms.mongodb.net/?retryWrites=true&w=majority&appName=Surfer-Cluster-2")

def init_driver():
    """Ініціалізація драйвера Chrome з оптимізованими параметрами"""
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")  # Для стабільності в Docker/CI
    chrome_options.add_argument("--window-size=1920,1080")  # Більший розмір для кращого рендерингу
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

def init_db():
    """Підключення до MongoDB"""
    client = MongoClient(uri, server_api=ServerApi('1'))
    db = client["books_db"]
    return db, db["books_ratings"]

def find_and_click_next_page_by_pattern(driver):
    """Функція для знаходження і кліку на кнопку наступної сторінки за патерном"""
    print("Шукаємо кнопку наступної сторінки за патерном...")
    
    try:
        # Знаходимо всі елементи пагінації
        pagination_elements = driver.find_elements(By.CSS_SELECTOR, ".reviews-pagination button, .reviews-pagination a")
        
        if not pagination_elements:
            print("Елементи пагінації не знайдено")
            return False
            
        print(f"Знайдено {len(pagination_elements)} елементів пагінації")
        
        # Знаходимо активну сторінку або першу сторінку
        active_index = -1
        for i, element in enumerate(pagination_elements):
            if 'active' in element.get_attribute('class') or 'disabled' in element.get_attribute('class'):
                active_index = i
                print(f"Знайдено активну сторінку: {i+1}")
                break
        
        # Якщо не знайшли активну, шукаємо наступну після першої
        next_button = None
        if active_index != -1 and active_index + 1 < len(pagination_elements):
            next_button = pagination_elements[active_index + 1]
        elif len(pagination_elements) > 1:  # Якщо є хоча б два елементи
            next_button = pagination_elements[1]  # Вибираємо другий елемент
            
        # Якщо знайшли кнопку наступної сторінки
        if next_button:
            # Прокручуємо до неї і клікаємо
            driver.execute_script("arguments[0].scrollIntoView(true);", next_button)
            time.sleep(1)
            driver.execute_script("arguments[0].click();", next_button)
            print("Клікнули на кнопку наступної сторінки за патерном")
            
            # Перевіряємо, що контент змінився
            time.sleep(2)
            return True
            
    except Exception as e:
        print(f"Помилка при пошуку кнопки за патерном: {e}")
    
    return False

def parse_review_card(card):
    """Парсинг окремого блоку відгуку"""
    review_data = {}
    
    author_element = card.select_one(".card-comment__nickname")
    review_data["author"] = author_element.get_text(strip=True) if author_element else "Анонім"
    
    date_element = card.select_one(".card-comment__date")
    review_data["date"] = date_element.get_text(strip=True) if date_element else "Невідома дата"
    
    score_element = card.select_one(".card-comment__score")
    if score_element:
        try:
            review_data["score"] = int(score_element.get_text(strip=True).split()[0])
        except (ValueError, IndexError):
            review_data["score"] = None
    
    text_element = card.select_one(".card-comment__text")
    review_data["text"] = text_element.get_text(strip=True) if text_element else ""
    
    return review_data

def parse_reviews_ratings(driver, book_url, max_pages=3):
    """Парсинг відгуків з пагінацією за патерном"""
    driver.get(book_url)
    print(f"Завантажено сторінку: {book_url}")
    
    reviews_data = []
    current_page = 1
    
    while current_page <= max_pages:
        print(f"Обробка сторінки {current_page}")
        time.sleep(3)  # Даємо час для завантаження JS
        
        # Парсимо відгуки з поточної сторінки
        soup = BeautifulSoup(driver.page_source, "html.parser")
        review_cards = soup.select(".reviews-list > div")
        
        if not review_cards:
            print(f"Відгуки не знайдено на сторінці {current_page}")
            break
        
        print(f"Знайдено {len(review_cards)} відгуків на сторінці {current_page}")
        
        # Обробляємо знайдені відгуки
        for card in review_cards:
            review_data = parse_review_card(card)
            if review_data.get("score") is not None:
                reviews_data.append(review_data)
        
        # Спроба перейти на наступну сторінку за допомогою пошуку за патерном
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(2)
        
        # Зберігаємо поточний URL для перевірки перенаправлення
        current_url = driver.current_url
        
        # Спочатку пробуємо знайти кнопку за патерном
        if not find_and_click_next_page_by_pattern(driver):
            # Якщо не вдалося, використовуємо старий метод як запасний
            print("Пробуємо запасний метод...")
            try:
                next_page_selector = "#product > div:nth-child(1) > div > div > div > section > div.main__reviews.product-main-section > section > div > div:nth-child(3) > div.reviews-pagination > div > button:nth-child(2) > a"
                next_page_exists = driver.execute_script(f"return !!document.querySelector('{next_page_selector}')")
                
                if next_page_exists:
                    driver.execute_script(f"document.querySelector('{next_page_selector}').click();")
                    print("Клікнули на кнопку наступної сторінки запасним методом")
                    time.sleep(2)
                else:
                    print("Кнопка не знайдена. Можливо, це остання сторінка.")
                    break
            except Exception as e:
                print(f"Помилка при використанні запасного методу: {e}")
                break
        
        # Перевіряємо, чи змінився URL або вміст сторінки
        new_url = driver.current_url
        if new_url != current_url:
            print(f"URL змінився: з {current_url} на {new_url}")
        
        time.sleep(2)
        current_page += 1
    
    print(f"Всього зібрано {len(reviews_data)} відгуків з {current_page-1} сторінок")
    return reviews_data

def analyze_ratings(reviews_data):
    """Аналіз зібраних рейтингів"""
    if not reviews_data:
        return {"count": 0, "average": 0, "distribution": {}}
    
    ratings = [review["score"] for review in reviews_data if "score" in review]
    
    if not ratings:
        return {"count": 0, "average": 0, "distribution": {}}
        
    distribution = {str(i): ratings.count(i) for i in range(1, 6)}
    
    return {
        "count": len(ratings),
        "average": round(mean(ratings), 2),
        "distribution": distribution
    }

def save_to_mongodb(db_collection, book_url, book_title, book_isbn, reviews_data, analysis):
    """Збереження результатів у MongoDB"""
    document = {
        "url": book_url,
        "title": book_title,
        "isbn": book_isbn,
        "total_reviews": analysis["count"],
        "average_rating": analysis["average"],
        "ratings_distribution": analysis["distribution"],
        "reviews": reviews_data,
        "parsed_at": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    existing_document = db_collection.find_one({"url": book_url})
    if existing_document:
        result = db_collection.update_one({"url": book_url}, {"$set": document})
        print(f"Оновлено {result.modified_count} запис")
    else:
        result = db_collection.insert_one(document)
        print(f"Додано новий запис з ID: {result.inserted_id}")

def main():
    """Головна функція скрипта"""
    print("Скрипт запущено")
    
    try:
        driver = init_driver()
        db, db_collection = init_db()
        
        book_url = "https://www.yakaboo.ua/ua/harry-potter-and-the-philosophers-stone.html"
        reviews_data = parse_reviews_ratings(driver, book_url, max_pages=3)
        
        analysis = analyze_ratings(reviews_data)
        print(f"Зібрано {analysis['count']} відгуків. Середня оцінка: {analysis['average']}")
        
        save_to_mongodb(db_collection, book_url, "Гаррі Поттер і філософський камінь", "978-966-7047-39-9", reviews_data, analysis)
        
    except Exception as e:
        print(f"Критична помилка: {e}")
    finally:
        if 'driver' in locals():
            driver.quit()
        print("Робота скрипта завершена")

if __name__ == "__main__":
    main()