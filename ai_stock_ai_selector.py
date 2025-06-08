# ai_stock_ai_selector.py
import os
import pandas as pd
import matplotlib.pyplot as plt
import mplfinance as mpf
import yfinance as yf
from datetime import datetime, timedelta
from telegram import Bot
import requests
from bs4 import BeautifulSoup

# === 설정 ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# === 종목 리스트 ===
STOCK_LIST = ["005930.KS", "000660.KS", "035420.KQ", "035720.KQ", "247540.KQ", "131970.KQ"]

# === 데이터 수집 ===
def get_stock_data(stocks):
    data = {}
    for stock in stocks:
        try:
            df = yf.download(stock, period='3mo', interval='1d')
            if not df.empty:
                data[stock] = df
        except Exception as e:
            print(f"Error fetching {stock}: {e}")
    return data

# === 뉴스 수집 ===
def get_latest_news(stock_name):
    headers = {'User-Agent': 'Mozilla/5.0'}
    url = f"https://search.naver.com/search.naver?where=news&query={stock_name}"
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, "html.parser")
    articles = soup.select(".news_tit")
    texts = [a.text for a in articles[:3]]
    return "\n".join(texts)

# === GPT 스타일 요약 ===
def gpt_style_summary(stock, df, news_text):
    latest = df.iloc[-1]
    change = df['Close'].pct_change().iloc[-1] * 100
    volume = latest['Volume']
    close = latest['Close']
    ma5 = df['Close'].rolling(5).mean().iloc[-1]
    ma20 = df['Close'].rolling(20).mean().iloc[-1]
    cross = "골든크로스" if ma5 > ma20 else "데드크로스"
    return f"[{stock}]\n- 📌 종가: {close:.2f}원 ({change:+.2f}%)\n- 📊 거래량: {volume:,}주\n- 📈 기술적 흐름: 5일선({ma5:.2f}) vs 20일선({ma20:.2f}) → {cross}\n- 📰 주요 뉴스: {news_text}"

# === 종목 선정 ===
def select_top2_stocks(data):
    scored = []
    for stock, df in data.items():
        if len(df) < 21: continue
        change = df['Close'].pct_change().tail(3).sum()
        avg_vol = df['Volume'].mean()
        score = change * 100 + (df['Volume'].iloc[-1] / avg_vol)
        scored.append((stock, score))
    top2 = sorted(scored, key=lambda x: x[1], reverse=True)[:2]
    return [s[0] for s in top2]

# === 차트 생성 ===
def save_chart(stock, df):
    filename = f"{stock}.png"
    mpf.plot(df, type='candle', mav=(5,10,20), volume=True, savefig=filename)
    return filename

# === 텔레그램 전송 ===
def send_to_telegram(stocks, data):
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    for stock in stocks:
        df = data[stock]
        name = stock.split('.')[0]
        news = get_latest_news(name)
        summary = gpt_style_summary(stock, df, news)
        chart_path = save_chart(stock, df)
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=summary)
        with open(chart_path, 'rb') as img:
            bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=img)

# === 메인 ===
def main():
    universe = STOCK_LIST  # 시가총액 제한 제거됨
    data = get_stock_data(universe)
    top2 = select_top2_stocks(data)
    send_to_telegram(top2, data)

if __name__ == "__main__":
    main()

