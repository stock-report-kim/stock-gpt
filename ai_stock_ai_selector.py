# ai_stock_selector.py

import requests
import datetime
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import mplfinance as mpf
from bs4 import BeautifulSoup
from ta.momentum import RSIIndicator
import os
import json

# 환경 변수 (GitHub Actions 또는 로컬 .env에서 설정)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SEND_MSG_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
SEND_PHOTO_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"

# 후보 종목 리스트 동적 수집 (네이버 급등주 페이지 기반)
def fetch_candidate_stocks():
    url = "https://finance.naver.com/sise/sise_rise.naver"
    headers = {'User-Agent': 'Mozilla/5.0'}
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, 'html.parser')
    table = soup.select("table.type_2 tr")
    codes = []
    for row in table:
        a_tag = row.find("a")
        if a_tag and "main.naver?code=" in a_tag.get("href"):
            code = a_tag.get("href").split("=")[-1]
            codes.append(code + ".KS" if code.startswith("0") else code + ".KQ")
    return list(set(codes))[:30]  # 상위 30종목

# 기술적 분석 스코어 계산
def analyze_technical(code):
    df = yf.download(code, period="3mo", interval="1d", auto_adjust=True)
    if df.empty or len(df) < 20:
        return 0
    rsi = RSIIndicator(df['Close']).rsi().iloc[-1]
    volume_spike = df['Volume'].iloc[-1] > df['Volume'].rolling(window=5).mean().iloc[-1] * 2
    ma20 = df['Close'].rolling(window=20).mean().iloc[-1]
    price = df['Close'].iloc[-1]
    signal = (rsi < 30) + volume_spike + (price > ma20)
    return signal

# 뉴스 요약 (KoGPT 또는 sumy 대체)
def fetch_news_summary(query):
    headers = {'User-Agent': 'Mozilla/5.0'}
    url = f"https://search.naver.com/search.naver?where=news&query={query}"
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, 'lxml')
    news_items = soup.select(".list_news div.news_area a.news_tit")
    links = [item['href'] for item in news_items[:3]]
    titles = [item.get_text() for item in news_items[:3]]
    summary = "\n".join([f"- {t}" for t in titles])
    return summary

# 캔들차트 저장 및 전송
def send_chart(code):
    df = yf.download(code, period="3mo", interval="1d", auto_adjust=True)
    if df.empty:
        return
    df.index.name = 'Date'
    df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
    filename = f"{code}_chart.png"
    mpf.plot(df, type='candle', volume=True, style='yahoo', savefig=filename)
    with open(filename, 'rb') as f:
        requests.post(SEND_PHOTO_URL, files={'photo': f}, data={'chat_id': TELEGRAM_CHAT_ID})

# 메인 실행
def main():
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    candidates = fetch_candidate_stocks()
    scored = [(code, analyze_technical(code)) for code in candidates]
    top3 = sorted(scored, key=lambda x: x[1], reverse=True)[:3]

    message = f"\n\n📈 [{today}] AI 기반 단기 급등 예상 종목\n\n"
    for code, score in top3:
        ticker = yf.Ticker(code)
        info = ticker.info
        name = info.get("shortName", code)
        summary = fetch_news_summary(name)
        message += f"🔹 {name} ({code})\n기술점수: {score}/3\n최근 뉴스:\n{summary}\n\n"
        send_chart(code)

    message += "⚠️ 본 정보는 투자 참고용이며, 책임은 투자자 본인에게 있습니다."
    requests.post(SEND_MSG_URL, data={'chat_id': TELEGRAM_CHAT_ID, 'text': message})

if __name__ == "__main__":
    main()
