# ai_stock_selector.py (v8.0 - 검색어 랭킹 기반 + AI 추천 통합)

import os
import datetime
import yfinance as yf
import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
from transformers import pipeline

# === 설정 ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SEND_MSG_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
SEND_PHOTO_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"

summarizer = pipeline("summarization", model="knkarthick/MEETING_SUMMARY")

# === 검색어 기반 종목 수집 ===
def fetch_hot_keywords():
    keywords = []
    try:
        for site in ["https://datalab.naver.com/keyword/trendSearch.naver", "https://www.google.com/trends/trendingsearches/daily?geo=KR"]:
            res = requests.get(site, headers={'User-Agent': 'Mozilla/5.0'})
            if 'naver' in site:
                soup = BeautifulSoup(res.text, 'lxml')
                tags = soup.select(".list_rank a")
                keywords += [tag.text.strip() for tag in tags[:10]]
            elif 'google' in site:
                data = res.text
                for line in data.split('\n'):
                    if 'title' in line:
                        t = line.split(':')[-1].strip().strip('" ,')
                        keywords.append(t)
    except Exception as e:
        print(f"[검색어 수집 오류]: {e}")
    return list(set(keywords))[:10]

# === 뉴스/루머 요약 ===
def fetch_news_titles(name):
    titles = []
    try:
        url = f"https://search.naver.com/search.naver?where=news&query={name}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, 'lxml')
        news = soup.select(".list_news div.news_area a.news_tit")
        titles += [n.text.strip() for n in news[:3]]
    except Exception as e:
        print(f"[뉴스 오류] {name}: {e}")
    return titles

def summarize_titles(titles):
    if not titles:
        return "관련 뉴스 없음"
    try:
        text = "\n".join(["- " + t for t in titles])
        result = summarizer(text, max_length=80, min_length=20, do_sample=False)
        return result[0]['summary_text']
    except Exception as e:
        print(f"[요약 오류]: {e}")
        return "요약 실패"

# === 캔들차트 저장 ===
def save_candle_chart(code, name):
    try:
        df = yf.download(code, period="3mo", interval="1d", auto_adjust=True)
        if df.empty or not all(np.issubdtype(df[c].dtype, np.number) for c in ['Open','High','Low','Close']):
            print(f"[차트 실패] {code}")
            return None
        filename = f"{code}_chart.png"
        mpf.plot(df, type='candle', volume=True, style='yahoo', title=name, savefig=filename)
        return filename
    except Exception as e:
        print(f"[차트 생성 오류] {name}: {e}")
        return None

# === 텔레그램 전송 ===
def send_telegram_message(message):
    try:
        requests.post(SEND_MSG_URL, data={'chat_id': TELEGRAM_CHAT_ID, 'text': message})
    except Exception as e:
        print(f"[메시지 오류]: {e}")

def send_telegram_image(filepath):
    try:
        with open(filepath, 'rb') as photo:
            requests.post(SEND_PHOTO_URL, files={'photo': photo}, data={'chat_id': TELEGRAM_CHAT_ID})
    except Exception as e:
        print(f"[이미지 오류]: {e}")

# === AI 추천 종목 (예시 기반) ===
def ai_recommended_stocks():
    return [
        {"name": "씨젠", "code": "096530.KQ"},
        {"name": "에코프로", "code": "086520.KQ"},
        {"name": "삼성엔지니어링", "code": "028050.KS"}
    ]



# === 저장소 정리 ===
def cleanup_all_files():
    for f in os.listdir():
        if f.endswith(".png"):
            try: os.remove(f)
            except: pass

# === 메인 ===
def main():
    hot_keywords = fetch_hot_keywords()
    keyword_section = "📊 [급등 검색어 기반 종목 분석]\n\n"
    for word in hot_keywords[:3]:
        titles = fetch_news_titles(word)
        summary = summarize_titles(titles)
        keyword_section += f"🔹 {word}\n요약: {summary}\n\n"

    ai_stocks = ai_recommended_stocks()
    ai_section = "🤖 [AI 추천 종목 분석]\n\n"
    for stock in ai_stocks:
        titles = fetch_news_titles(stock['name'])
        summary = summarize_titles(titles)
        ai_section += f"🔹 {stock['name']} ({stock['code']})\n요약: {summary}\n\n"
        chart = save_candle_chart(stock['code'], stock['name'])
        if chart:
            send_telegram_image(chart)

    final_msg = f"{keyword_section}\n{ai_section}⚠️ 본 정보는 참고용이며, 투자 판단은 본인 책임입니다."
    send_telegram_message(final_msg)

if __name__ == "__main__":
    main()
