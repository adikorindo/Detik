import time
import json
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import logging
import random
import pytz
from datetime import datetime
from transformers import pipeline

# === KONFIGURASI ===
FB_PAGES = [
    {"page_id": "615563141635327", "access_token": "EAAc8IY7AhZAgBO6q7E1Pm6cTx7ipcb6rW8uV1ZA5kt9CvHHEHu03maDCbapyxlafhIyUpktKx9Qh6AAWMSAIgBKShKTs0kC6z4dXLBDIqbvBfc4ZCU4aOlaC3vt7CD9ZCZBbq4KCx55MZCOTBbBj5f0aITJqfVu9T98YFcFZBpSso3f7wULdoDquuLZAxMkuWAD6"}, #Info Bisnis ID
    {"page_id": "626016627261060", "access_token": "EAAd1DrRrDJ8BO71QZAT2p8ZAb7iNi3M74pLEdywuE8HU9efieoupS8KnQ52g7OumZASWUEee51XhJUWxiBZAKZB4cbgUgTmFXjZA3EXHiQJ6zvhza3oYFR1sS9Dnj6TIqSoBlWGNmNopGg1vIxNPn58nIQeBKntJzZB2WQcpQzmXJV4vdoXaJVZBB9YoFZAOZBpbwf"}, #Berita Bisnis ID
    {"page_id": "613037738556925", "access_token": "EAAIwwD4kdckBOZBZBbp1gU4gCLUdxi9jGdlngIzpd27od7c8yxCMItZAhN94Pr6B9YA2JCGWtpu1bfoJeyn3loAYwCbBN9gCY3MFoTMRG9DgaZCJAZB1p1ISs9chbmPncRc2znYHPHzZC7TtZCJvzX6egMXlWPQUj8YwEoMR0mUrItZBpvJKU5W19KwCdB9BhHjF"}, # Seputar Bisnis ID
]

SITEMAP_URLS = [
    "https://inet.detik.com/mobileapps/sitemap_web.xml",
    "https://inet.detik.com/science/sitemap_web.xml",
    "https://inet.detik.com/cyber-life/sitemap_web.xml",
    "https://inet.detik.com/consumer/sitemap_web.xml"
]

TIMEZONE = "Asia/Jakarta"
CHECK_INTERVAL = 40 * 60  # 30 menit

# === SETUP LOGGER ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === SETUP SESSION REQUESTS ===
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
})

# === LOAD MODEL SUMMARIZATION ===
summarizer = pipeline("summarization", model="facebook/bart-large-cnn")

# === FETCHER: Mengambil URL dari Sitemap ===
def fetch_sitemap(sitemap_url):
    try:
        response = session.get(sitemap_url, timeout=10)
        response.raise_for_status()
        content = response.text.replace(' xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"', '')
        root = ET.fromstring(content)
        urls = root.findall('.//loc') or root.findall('./url/loc')
        return [url.text.strip() for url in urls]
    except Exception as e:
        logger.error(f"Failed to fetch sitemap: {e}")
        return []

# === FETCHER: Mengambil Konten Berita ===
def fetch_page_content(url):
    try:
        response = session.get(url, timeout=10)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        content = {'title': '', 'main_content': '', 'image_url': '', 'url': url}

        title_tag = soup.find('meta', property='og:title') or soup.title
        if title_tag:
            content['title'] = title_tag['content'].strip() if title_tag.has_attr('content') else title_tag.text.strip()

        article_content = soup.find('div', class_='detail__body-text') or soup.find('article')
        if article_content:
            text_paragraphs = article_content.find_all("p")
            content['main_content'] = ' '.join([p.get_text(strip=True) for p in text_paragraphs])

        image_meta = soup.find('meta', property='og:image')
        if image_meta and image_meta.has_attr('content'):
            content['image_url'] = image_meta['content']
        else:
            image_tag = soup.find('img')
            if image_tag and 'src' in image_tag.attrs:
                content['image_url'] = image_tag['src']

        return content if content['title'] and content['main_content'] else None
    except Exception as e:
        print("Gagal mendapatkan artikel berita")
        logger.error(f"Failed to fetch page {url}: {e}")
        return None

# === SUMMARIZER: Meringkas Berita ===
def summarize_text(text, method="random"):
    if method == "random":
        method = random.choice(["abstractive", "extractive"])

    if method == "abstractive":
        summary = summarizer(text, max_length=500, min_length=100, do_sample=False)
        return summary[0]['summary_text']
    else:
        return '. '.join(text.split('. ')[:5]) + '.'

# === POSTER: Posting ke Facebook ===
def post_to_facebook(title, summary, url, image_url):
    message = f"{title}\n\n{summary}"

    for page in FB_PAGES:
        post_url = f"https://graph.facebook.com/{page['page_id']}/photos"
        payload = {
            "url": image_url,
            "caption": message,
            "access_token": page["access_token"],
        }

        response = requests.post(post_url, data=payload)
        if response.status_code == 200:
            logger.info(f"Posted to {page['page_id']} successfully.")
        else:
            logger.error(f"Failed to post to {page['page_id']}: {response.text}")

# === MAIN LOOP ===
posted_articles = set()
JSON_FILE = "posted_articles_biz.json"

try:
    with open(JSON_FILE, "r") as f:
        posted_articles = set(json.load(f))
except FileNotFoundError:
    posted_articles = set()

while True:
    wib_time = datetime.now(pytz.timezone(TIMEZONE)).hour

    if 6 <= wib_time < 24:
        sitemap_url = random.choice(SITEMAP_URLS)
        article_urls = fetch_sitemap(sitemap_url)

        for article_url in article_urls:
            if article_url not in posted_articles:
                content = fetch_page_content(article_url)
                if content:
                    summary = summarize_text(content['main_content'])
                    post_to_facebook(content['title'], summary, content['url'], content['image_url'])
                    posted_articles.add(article_url)

                    with open(JSON_FILE, "w") as f:
                        json.dump(list(posted_articles), f)

                    time.sleep(CHECK_INTERVAL)  # Tunggu 45 menit sebelum cek lagi
    else:
        time.sleep(60)  # Tunggu 1 menit sebelum cek lagi
