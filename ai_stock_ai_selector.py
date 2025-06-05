import yfinance as yf
import mplfinance as mpf
import matplotlib.pyplot as plt
from bs4 import BeautifulSoup
import requests
import os
import datetime
import pandas as pd
from ta.momentum import RSIIndicator
from ta.trend import MACD

# 🧠 후보 종목군 (예: KOSDAQ 기술주 30선)
CANDIDATES = {
    "086520.KQ": "에코프로",
    "035720.KQ": "카카오",
    "067310.KQ": "하나마이크론",
    "005930.KS": "삼성전자",
    "035250.KQ": "강원에너지"
}

# 📊 기술적 분석 기반 점수화
def analyze_technical(code):
    df = yf.download(code, period="3mo", interval="1d")
    if len(df) < 30: return 0  # 거래일 부족

    rsi = RSIIndicator(df['Close']).rsi().iloc[-1]
    macd = MACD(df['Close']).macd_diff().iloc[-1]
    recent_gain = (df['Close'][-1] - df['Close'][-6]) / df['Close'][-6]

    score = 0
    if rsi < 30: score += 2  # 과매도
    if macd > 0: score += 1  # 상승추세 시작
    if recent_gain > 0.1: score += 2  # 최근 급등

    return score

# 📰 뉴스 기반 긍정 키워드 분석
def analyze_news(name):
    url = f"https://search.naver.com/search.naver?where=news&query={name}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, 'lxml')
    titles = [a.get_text() for a in soup.select("a.news_tit")[:5]]

    pos_keywords = ["호재", "수주", "급등", "최대", "신제품"]
    neg_keywords = ["적자", "하락", "리스크"]

    score = 0
    for t in titles:
        score += sum([1 for k in pos_keywords if k in t])
        score -= sum([1 for k in neg_keywords if k in t])

    summary = "\n".join(["- " + t for t in titles])
    return score, summary

# 🧠 종합 AI 분석
results = []
for code, name in CANDIDATES.items():
    tech_score = analyze_technical(code)
    news_score, news_summary = analyze_news(name)
    total_score = tech_score + news_score
    results.append({
        "code": code,
        "name": name,
        "score": total_score,
        "news_summary": news_summary
    })

# 📈 상위 3개 종목 선정
top3 = sorted(results, key=lambda x: x['score'], reverse=True)[:3]

# 📝 텔레그램 메시지 생성
date = datetime.datetime.now().strftime("%Y-%m-%d")
message = f"📈 {date} AI 기반 단타 유망주\n\n"
for item in top3:
    message += f"🔹 {item['name']} ({item['code']})\n점수: {item['score']}\n뉴스요약:\n{item['news_summary']}\n\n"

# 🖼️ 캔들 차트 생성 및 전송
def send_chart(code, name):
    df = yf.download(code, period="3mo", interval="1d")
    filename = f"{code}_candlestick.png"
    mpf.plot(df, type='candle', style='charles', volume=True, mav=(5,20), savefig=filename)

    with open(filename, 'rb') as img:
        requests.post(f"https://api.telegram.org/bot{TOKEN}/sendPhoto", data={"chat_id": CHAT_ID}, files={"photo": img})

# 텔레그램 전송
requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", data={"chat_id": CHAT_ID, "text": message})
for item in top3:
    send_chart(item["code"], item["name"])
