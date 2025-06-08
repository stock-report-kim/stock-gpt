# ai_stock_ai_selector.py
import os
import requests
from bs4 import BeautifulSoup
from telegram import Bot
from datetime import datetime

# === 설정 ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# === 네이버 실시간 검색어 기반 급등 종목 수집 ===
def get_naver_trending_stocks():
    url = "https://finance.naver.com/sise/lastsearch2.naver"
    headers = {'User-Agent': 'Mozilla/5.0'}
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, 'html.parser')
    items = soup.select("table.type_5 tr td a")
    keywords = [item.text.strip() for item in items if item.text.strip()]
    code_map = {
        "삼성전자": ("005930", "KS"),
        "LG에너지솔루션": ("373220", "KS"),
        "에코프로": ("086520", "KQ"),
        "포스코퓨처엠": ("003670", "KQ"),
        "HLB": ("028300", "KQ")
    }
    codes = [(k, *code_map[k]) for k in keywords if k in code_map]
    return codes[:3]

# === 뉴스 수집 ===
def get_latest_news(stock_name):
    headers = {'User-Agent': 'Mozilla/5.0'}
    url = f"https://search.naver.com/search.naver?where=news&query={stock_name}"
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, "html.parser")
    articles = soup.select(".news_tit")
    texts = [a.text for a in articles[:3]]
    return texts

# === 요약 생성 ===
def create_summary(name, news_list, chart_url):
    today = datetime.now().strftime("%Y-%m-%d (%a)")
    summary = f"📌 [{name}] 실시간 검색 급등 ({today})\n"
    summary += f"📊 차트 보기: {chart_url}\n"
    summary += "📰 주요 뉴스 요약:\n"
    for n in news_list:
        summary += f"- {n}\n"
    return summary

# === 텔레그램 전송 ===
def send_to_telegram(stocks):
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    if not stocks:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text="📭 오늘은 인기 검색 종목이 없습니다.")
        return
    for name, code, market in stocks:
        news = get_latest_news(name)
        chart_url = f"https://finance.naver.com/item/main.nhn?code={code}"
        summary = create_summary(name, news, chart_url)
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=summary)

# === 메인 ===
def main():
    trending = get_naver_trending_stocks()
    send_to_telegram(trending)

if __name__ == '__main__':
    main()
