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

# Ініціалізація драйвера

def init_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=chrome_options)

# Ініціалізація бази даних

def init_db():
    uri = "mongodb+srv://dobryy_surfer:1Tsv3ry1mp0rtant!@surfer-cluster-2.erpms.mongodb.net/?retryWrites=true&w=majority&appName=Surfer-Cluster-2"
    client = MongoClient(uri, server_api=ServerApi('1'))
    db = client["books_db"]
    return db, db["ratings"]

# Функція для збору рейтингу та кількості відгуків

def parse_ratings(driver, book_url, ratings_collection):
    driver.get(book_url)
    time.sleep(2)
    
    soup = BeautifulSoup(driver.page_source, "html.parser")
    title = soup.select_one(".product-title").text.strip() if soup.select_one(".product-title") else "Без назви"
    
    reviews_section = soup.select_one("#product > div:nth-child(1) > div > div > div > section > div.main__reviews.product-main-section > section > div > div:nth-child(3)")
    if not reviews_section:
        print("Секція з відгуками не знайдена. HTML-код:")
        print(soup.prettify()[:1000])  # Виводимо перші 1000 символів сторінки для аналізу
        return False
    
    total_rating_element = reviews_section.select_one(".product-rating")
    total_rating = total_rating_element.text.strip() if total_rating_element else "0"
    total_reviews_element = reviews_section.select_one(".product-reviews-counter")
    total_reviews = total_reviews_element.text.strip() if total_reviews_element else "0"
    
    try:
        total_rating = float(total_rating.replace(",", "."))
        total_reviews = int("".join(filter(str.isdigit, total_reviews)))
    except ValueError:
        total_rating = 0
        total_reviews = 0
    
    # Пагінація відгуків
    rating_distribution = {"5_stars": 0, "4_stars": 0, "3_stars": 0, "2_stars": 0, "1_star": 0}
    while True:
        soup = BeautifulSoup(driver.page_source, "html.parser")
        for review in soup.select(".reviews-list > div"):  
            score_element = review.select_one(".card-comment__score")
            if score_element:
                score_text = score_element.text.strip()
                try:
                    score = int(score_text)
                    if score == 5:
                        rating_distribution["5_stars"] += 1
                    elif score == 4:
                        rating_distribution["4_stars"] += 1
                    elif score == 3:
                        rating_distribution["3_stars"] += 1
                    elif score == 2:
                        rating_distribution["2_stars"] += 1
                    elif score == 1:
                        rating_distribution["1_star"] += 1
                except ValueError:
                    continue
        
        next_button = driver.find_elements(By.CSS_SELECTOR, ".reviews-pagination .pagination-next")
        if next_button and next_button[0].is_displayed():
            next_button[0].click()
            time.sleep(2)
        else:
            break
    
    rating_data = {
        "title": title,
        "url": book_url,
        "total_rating": total_rating,
        "total_reviews": total_reviews,
        "rating_distribution": rating_distribution,
        "parsed_at": time.strftime('%Y-%m-%d %H:%M:%S')
    }
    ratings_collection.insert_one(rating_data)
    return True

# Основна функція запуску

def main():
    driver = init_driver()
    db, ratings_collection = init_db()
    book_url = "https://www.yakaboo.ua/ua/harry-potter-and-the-chamber-of-secrets-958092.html"
    parse_ratings(driver, book_url, ratings_collection)
    driver.quit()

if __name__ == "__main__":
    main()
