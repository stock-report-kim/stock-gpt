# ai_stock_selector.py

import yfinance as yf
import matplotlib.pyplot as plt
import pandas as pd
import requests
import datetime
from ta.momentum import RSIIndicator
from ta.trend import MACD
from bs4 import BeautifulSoup
import os

# ✅ 종목 리스트 (원하는 만큼 추가 가능)
CANDIDATES = {
    "005930.KS": "삼성전자",
    "086520.KQ": "에코프로",
    "067310.KQ": "하나마이크론",
    "035250.KQ": "강원에너지",
    "035720.KQ": "카카오"
}

# ✅ 기술적 분석 점수 계산
def analyze_technical(code):
    df = yf.download(code, period="3mo", interval="1d", auto_adjust=True)
    if len(df) < 30:
        return 0

    close = df['Close'].squeeze()
    rsi = RSIIndicator(close).rsi().iloc[-1]
    macd = MACD(close).macd_diff().iloc[-1]
    recent_gain = (close.iloc[-1] - close.iloc[-6]) / close.iloc[-6]

    score = 0
    if rsi < 30:
        score += 2
    if macd > 0:
        score += 1
    if recent_gain > 0.1:
        score += 2

    return score

# ✅ 네이버 뉴스 3건 추출
def fetch_news(keyword):
    url = f"https://search.naver.com/search.naver?where=news&query={keyword}"
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, "lxml")
    items = soup.select(".list_news div.news_area a.news_tit")
    return [item.get_text() for item in items[:3]]

# ✅ 단순 키워드 추출
def extract_keywords(news_list):
    combined = " ".join(news_list)
    words = pd.Series(combined.split())
    keywords = words[words.str.len() > 3].value_counts().head(5).index.tolist()
    return ", ".join(keywords)

# ✅ 차트 생성
def draw_chart(code, name):
    df = yf.download(code, period="3mo", interval="1d", auto_adjust=True)
    plt.figure(figsize=(8, 4))
    plt.plot(df.index, df['Close'], color='blue', label='Close')
    plt.title(f"{name} (최근 3개월 종가 차트)")
    plt.xlabel("날짜")
    plt.ylabel("가격")
    plt.grid(True)
    plt.tight_layout()
    filename = f"{code}.png"
    plt.savefig(filename)
    plt.close()
    return filename

# ✅ Telegram 전송
def send_telegram_message(token, chat_id, text):
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    requests.post(url, data={"chat_id": chat_id, "text": text})

def send_telegram_photo(token, chat_id, file_path):
    url = f"https://api.telegram.org/bot{token}/sendPhoto"
    with open(file_path, "rb") as photo:
        requests.post(url, files={"photo": photo}, data={"chat_id": chat_id})

# ✅ 메인 실행
def main():
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
    CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
    today = datetime.datetime.now().strftime("%Y-%m-%d")

    scored = []
    for code, name in CANDIDATES.items():
        score = analyze_technical(code)
        if score == 0:
            continue
        news = fetch_news(name)
        keywords = extract_keywords(news)
        summary = f"▶ {name} ({code})\n기술 점수: {score}/5\n핵심 뉴스 키워드: {keywords}"
        scored.append((score, code, name, summary))

    if not scored:
        send_telegram_message(TOKEN, CHAT_ID, f"[{today}] 분석 결과 추천 종목 없음.")
        return

    # 점수 기준 상위 3종목
    top3 = sorted(scored, key=lambda x: x[0], reverse=True)[:3]

    # 메시지 작성 및 전송
    msg = f"📈 [{today}] AI 기반 급등 예상 종목 Top 3\n\n"
    for _, _, _, summary in top3:
        msg += summary + "\n\n"
    msg += "📊 아래는 각 종목의 최근 3개월간 차트입니다."
    send_telegram_message(TOKEN, CHAT_ID, msg)

    # 차트 전송
    for _, code, name, _ in top3:
        file_path = draw_chart(code, name)
        send_telegram_photo(TOKEN, CHAT_ID, file_path)

if __name__ == "__main__":
    main()
