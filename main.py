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
from urllib.parse import urlparse

# MongoDB та константи
uri = "mongodb+srv://dobryy_surfer:1Tsv3ry1mp0rtant!@surfer-cluster-2.erpms.mongodb.net/?retryWrites=true&w=majority&appName=Surfer-Cluster-2"
BASE_URL = "https://www.yakaboo.ua"

def init_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

def init_db():
    client = MongoClient(uri, server_api=ServerApi('1'))
    db = client["books_db"]
    return db, db["books"], db["selectors"]

def find_element(driver, by, value, wait_time=10):
    try:
        return WebDriverWait(driver, wait_time).until(EC.presence_of_element_located((by, value)))
    except Exception as e:
        return None

def get_books_from_publisher(driver, publisher_url, selectors_collection):
    driver.get(publisher_url)
    time.sleep(2)
    soup = BeautifulSoup(driver.page_source, "html.parser")
    domain = urlparse(publisher_url).netloc
    
    # Об'єднані селектори - збережені + стандартні
    all_selectors = []
    
    # Додаємо збережені селектори, якщо є
    saved_selectors = selectors_collection.find_one({"domain": domain})
    if saved_selectors and "selectors" in saved_selectors:
        all_selectors.extend(saved_selectors["selectors"])
    
    # Додаємо стандартні селектори
    all_selectors.extend([
        ".category__content .category__main a",
        ".category__cards .category__item a",
        ".product-card__link",
        ".products-layout a[href*='/ua/']",
        ".product-list a",
        ".book-item a",
        ".item-card a",
        "a.book-link",
        ".book-container a"
    ])
    
    book_links = []
    successful_selector = None
    
    # Перебираємо всі селектори
    for selector in all_selectors:
        links = soup.select(selector)
        if not links:
            continue
            
        filtered_links = []
        for link in links:
            href = link.get('href')
            if not href:
                continue
                
            is_valid_link = False
            if 'yakaboo.ua' in domain:
                is_valid_link = '/ua/' in href and not href.endswith('#')
            else:
                is_valid_link = not href.endswith('#') and not href.startswith('javascript') and ('/books/' in href or '/book/' in href)
            
            if is_valid_link:
                full_url = BASE_URL + href if not href.startswith('http') else href
                if full_url not in filtered_links:
                    filtered_links.append(full_url)
        
        if len(filtered_links) > 5:
            book_links = filtered_links
            successful_selector = selector
            break
    
    # Якщо знайдений успішний селектор, зберігаємо його
    if successful_selector:
        selectors_collection.update_one(
            {"domain": domain}, 
            {"$set": {"selectors": [successful_selector]}}, 
            upsert=True
        )
    
    # Резервний метод пошуку
    if not book_links:
        all_links = soup.find_all('a', href=True)
        for link in all_links:
            href = link.get('href')
            
            is_valid_link = False
            if 'yakaboo.ua' in domain:
                is_valid_link = ('/ua/' in href) and not href.endswith('#') and not href.startswith('javascript') and '/ua/book_publisher/' not in href
            else:
                is_valid_link = not href.endswith('#') and not href.startswith('javascript') and ('/book/' in href or '/product/' in href)
            
            if is_valid_link:
                full_url = BASE_URL + href if not href.startswith('http') else href
                if full_url not in book_links:
                    book_links.append(full_url)
    
    return book_links

def parse_and_save_book(driver, book_url, collection):
    driver.get(book_url)
    if not find_element(driver, By.CSS_SELECTOR, ".char__title"):
        return False
        
    soup = BeautifulSoup(driver.page_source, "html.parser")
    
    # Знаходимо назву
    title_element = soup.find('h1', class_='product-title') or soup.find('h1') or soup.select_one('.product-main-section h1')
    title = title_element.get_text(strip=True).replace("Книга", "").strip() if title_element else "Без назви"
    
    # Характеристики книги
    char_blocks = soup.find_all('div', class_='char')
    isbn, author, publisher, year = None, None, None, None
    
    for block in char_blocks:
        title_element = block.find('div', class_='char__title')
        if not title_element:
            continue
            
        title_text = title_element.get_text(strip=True)
        value_element = block.find('div', class_='char__value')
        if not value_element:
            continue
            
        value_text = value_element.get_text(strip=True)
        
        if 'ISBN' in title_text:
            if ',' in value_text or ';' in value_text or ' / ' in value_text:
                return False
            isbn = value_text.strip()
        elif 'Автор' in title_text:
            if ',' in value_text or ';' in value_text or ' / ' in value_text:
                return False
            author = value_text.strip()
        elif 'Видавництво' in title_text:
            publisher = value_text.strip()
        elif 'Рік видання' in title_text:
            year = value_text.strip()
    
    if not isbn or not author:
        return False
    
    # Перевіряємо, чи існує книга вже в базі
    if collection.find_one({"isbn": isbn}):
        return False
    
    # Обкладинка
    cover_url = 'None'
    cover_div = soup.find('div', class_='slide__item')
    if cover_div:
        img = cover_div.find('img', class_='slide__img')
        if img:
            cover_url = img.get('src')
    
    # Категорія
    category = "None"
    category_element = soup.select_one("#product .product-options.products-options.category-options.product-main-section")
    if category_element:
        category_links = category_element.select("a")
        if not category_links:
            category = category_element.get_text(strip=True).replace("Категорія:", "").strip()
        else:
            seen_categories = set()
            categories = []
            for link in category_links:
                category_name = link.get_text(strip=True)
                if category_name.lower() not in seen_categories:
                    categories.append(category_name)
                    seen_categories.add(category_name.lower())
            category = ", ".join(categories)
    
    # Формуємо та зберігаємо документ
    book_data = {
        'title': title,
        'isbn': isbn,
        'author': author,
        'publisher': publisher,
        'year': year,
        'cover_url': cover_url,
        'category': category,
        'url': book_url
    }
    
    collection.insert_one(book_data)
    return True

def main():
    print("Скрипт запущено")
    driver = init_driver()
    print("Драйвер ініціалізовано")
    db, books_collection, selectors_collection = init_db()
    print("Підключення до бази даних встановлено")
    
    publisher_url = 'https://www.yakaboo.ua/ua/book_publisher/view/A_ba_ba_ga_la_ma_ga'
    print(f"Переходимо на сторінку видавництва: {publisher_url}")
    book_links = get_books_from_publisher(driver, publisher_url, selectors_collection)
    print(f"Знайдено {len(book_links)} посилань на книги")
    
    if not book_links:
        print("Посилання на книги не знайдені, завершуємо роботу")
        driver.quit()
        return
    
    book_count = 0
    max_books = 5
    
    for book_url in book_links:
        if book_count >= max_books:
            print(f"Досягнуто ліміту в {max_books} книг")
            break
        
        print(f"Обробка книги {book_count+1}: {book_url}")    
        if parse_and_save_book(driver, book_url, books_collection):
            book_count += 1
            print(f"Книга успішно збережена, всього: {book_count}")
    
    print("Робота скрипта завершена")
    driver.quit()

if __name__ == "__main__":
    main()