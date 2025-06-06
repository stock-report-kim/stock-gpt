# ai_stock_ai_selector.py

import requests
import yfinance as yf
import pandas as pd
import matplotlib.pyplot as plt
import mplfinance as mpf
from bs4 import BeautifulSoup
from ta.momentum import RSIIndicator
from ta.trend import MACD
import os
import datetime

# Step 1: 실시간 테마 키워드 크롤링 (네이버 뉴스 기준)
def fetch_trending_keywords():
    url = "https://finance.naver.com/"
    res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
    soup = BeautifulSoup(res.text, 'lxml')
    keywords = []
    for tag in soup.select(".section_stock_market .tit a"):
        if tag.text:
            keywords.append(tag.text.strip())
    return list(set(keywords))[:5]  # 상위 5개 테마 키워드

# Step 2: 키워드에 연관된 종목 후보 수집 (네이버 뉴스 기사 기반)
def search_related_stocks(keyword):
    url = f"https://search.naver.com/search.naver?where=news&query={keyword}+주식"
    res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
    soup = BeautifulSoup(res.text, 'lxml')
    articles = soup.select(".list_news .news_tit")
    stock_names = []
    for a in articles:
        title = a.text
        for word in title.split():
            if word.endswith("주") or len(word) >= 3:
                stock_names.append(word.strip())
    return list(set(stock_names))[:3]  # 키워드당 종목 최대 3개 추출

# Step 3: 네이버 종목명으로 티커 변환 (간단한 매핑 예시)
def name_to_ticker(name):
    mapping_url = f"https://finance.naver.com/search/searchList.naver?query={name}"
    res = requests.get(mapping_url, headers={'User-Agent': 'Mozilla/5.0'})
    soup = BeautifulSoup(res.text, 'lxml')
    result = soup.select_one("table tr td.tit a")
    if result:
        href = result['href']
        if 'code=' in href:
            return href.split('code=')[1]
    return None

# Step 4: 기술적 분석 지표 기반 점수

def analyze_technical(code):
    try:
        df = yf.download(code + ".KS", period="3mo")
        if df.empty or len(df) < 20:
            return 0

        rsi = RSIIndicator(df['Close']).rsi().iloc[-1]
        macd = MACD(df['Close']).macd_diff().iloc[-1]

        score = 0
        if rsi < 30:
            score += 2
        elif rsi > 70:
            score -= 1
        if macd > 0:
            score += 2
        return score
    except Exception as e:
        return 0

# Step 5: 뉴스 기반 재료/루머 요약 (단순 수집)
def fetch_material_news(stock_name):
    url = f"https://search.naver.com/search.naver?where=news&query={stock_name}+재료"
    res = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'})
    soup = BeautifulSoup(res.text, 'lxml')
    items = soup.select(".list_news .news_tit")
    summaries = [item.text for item in items[:2]]
    return summaries

# Step 6: 종목 차트 저장

def save_chart(code, name):
    df = yf.download(code + ".KS", period="3mo")
    df.index.name = 'Date'
    df.rename(columns={'Open': 'Open', 'High': 'High', 'Low': 'Low', 'Close': 'Close', 'Volume': 'Volume'}, inplace=True)
    mpf.plot(df, type='candle', style='yahoo', volume=True, savefig=f"{name}.png")

# Step 7: 메인 로직
if __name__ == "__main__":
    keywords = fetch_trending_keywords()
    print("[테마 키워드]", keywords)
    
    candidates = set()
    for keyword in keywords:
        names = search_related_stocks(keyword)
        for name in names:
            ticker = name_to_ticker(name)
            if ticker:
                candidates.add((name, ticker))

    scored = []
    for name, code in candidates:
        score = analyze_technical(code)
        news = fetch_material_news(name)
        scored.append((score, name, code, news))

    top3 = sorted(scored, reverse=True)[:3]

    print("\n📌 오늘의 AI 추천 종목:\n")
    for i, (score, name, code, news) in enumerate(top3, 1):
        print(f"{i}. {name} ({code}) - 기술점수: {score}")
        print("   🔎 재료:")
        for line in news:
            print("   -", line)
        print()
        save_chart(code, name)

    print("✅ 차트 이미지가 저장되었습니다.")

