# ai_stock_selector.py (v4.7 - 전체 함수 포함, 투자매력/테마/백테스트/청소 등 통합)

import os
import datetime
import yfinance as yf
import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd
import numpy as np
import requests
from bs4 import BeautifulSoup
from ta.momentum import RSIIndicator
from ta.trend import MACD
from transformers import pipeline

# === 설정 ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
SEND_MSG_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
SEND_PHOTO_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"

# === AI 모델 로드 ===
summarizer = pipeline("summarization", model="knkarthick/MEETING_SUMMARY")
theme_classifier = pipeline("text-classification", model="nlptown/bert-base-multilingual-uncased-sentiment")
scorer = pipeline("sentiment-analysis", model="nlptown/bert-base-multilingual-uncased-sentiment")

# === 업종 자동 크롤링 ===
def fetch_sector(name):
    try:
        url = f"https://finance.naver.com/item/main.nhn?query={name}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, 'lxml')
        info = soup.select_one(".description")
        if info and ">" in info.text:
            return info.text.split(" > ")[-1].strip()
        return "기타"
    except:
        return "기타"

# === 1. 급등 종목 수집 ===
def fetch_candidate_stocks():
    url = "https://finance.naver.com/sise/lastsearch2.naver"
    headers = {'User-Agent': 'Mozilla/5.0'}
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, 'lxml')
    stocks = []
    for a in soup.select(".box_type_l a"):
        name = a.text.strip()
        href = a.get("href", "")
        if "code=" in href:
            code = href.split("code=")[-1]
            suffix = ".KS" if code.startswith("0") else ".KQ"
            sector = fetch_sector(name)
            stocks.append({"name": name, "code": code + suffix, "sector": sector})
    print(f"[후보 종목 수집 완료] 총 {len(stocks)}개")
    return stocks[:30]

# === 2. 기술 분석 ===
def get_last_trading_date(df):
    return df.index[-1].strftime('%Y-%m-%d') if not df.empty else datetime.date.today().isoformat()

def analyze_technical(code):
    try:
        df = yf.download(code, period="3mo", interval="1d", auto_adjust=True)
        if df.empty or len(df) < 20:
            print(f"[!] 데이터 부족 또는 없음: {code}, 빈 데이터프레임 반환됨")
            return 0, None, None
        close = df['Close']
        volume = df['Volume']
        macd = MACD(close)
        rsi = RSIIndicator(close).rsi()
        volume_spike = volume.iloc[-1] > volume.rolling(5).mean().iloc[-1] * 2
        ma20 = close.rolling(20).mean().iloc[-1]
        macd_signal = macd.macd_diff().iloc[-1] > 0
        score = int(rsi.iloc[-1] < 40) + int(volume_spike) + int(close.iloc[-1] > ma20) + int(macd_signal)
        print(f"[{code}] 기술점수: {score} (RSI: {rsi.iloc[-1]:.2f}, 거래량급증: {volume_spike}, MACD: {macd_signal})")
        return score, get_last_trading_date(df), df
    except Exception as e:
        print(f"Error in analyze_technical({code}): {e}")
        return 0, None, None

# === 3. 뉴스 및 커뮤니티 정보 수집 ===
def fetch_news_titles(name):
    titles = []
    try:
        url = f"https://search.naver.com/search.naver?where=news&query={name}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, 'lxml')
        news = soup.select(".list_news div.news_area a.news_tit")
        if news:
            extracted = [n.text.strip() for n in news[:3]]
            titles += extracted
            print(f"[뉴스 수집 성공] {name} - {len(extracted)}건")
        else:
            print(f"[뉴스 없음] {name}")
    except Exception as e:
        print(f"[뉴스 수집 오류] {name}: {e}")
    try:
        url = f"https://m.stock.naver.com/domestic/stock/{name}/community"
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, 'lxml')
        posts = soup.select(".community_area .title")
        if posts:
            extracted_posts = [p.text.strip() for p in posts[:2]]
            titles += extracted_posts
            print(f"[커뮤니티 수집 성공] {name} - {len(extracted_posts)}건")
        else:
            print(f"[커뮤니티 없음] {name}")
    except Exception as e:
        print(f"[커뮤니티 수집 오류] {name}: {e}")
    print(f"[뉴스/루머 총 수집] {name} - {len(titles)}건")
    return titles

# === 4. 뉴스 요약 ===
def gpt_style_summary(titles):
    if not titles:
        return "관련 뉴스 및 루머 없음"
    text = "\n".join(["- " + t for t in titles])
    try:
        prompt = f"다음 정보는 뉴스/커뮤니티 게시글/루머입니다. 투자자 관점에서 핵심 이슈를 요약해줘:\n{text}"
        result = summarizer(prompt, max_length=80, min_length=20, do_sample=False)
        return result[0]['summary_text']
    except Exception as e:
        print(f"[요약 오류]: {e}")
        return "요약 실패"

# === 5. 투자매력도 점수화 ===
def score_investment_attractiveness(summary):
    try:
        result = scorer(summary)
        if result and isinstance(result, list):
            label = result[0]['label']
            score = int(label[0])
            return score
        return 0
    except Exception as e:
        print(f"[투자매력도 점수화 오류]: {e}")
        return 0

# === 6. 테마 자동 분류 ===
def classify_theme(summary):
    try:
        result = theme_classifier(summary)
        if result and isinstance(result, list):
            return result[0]['label']
        return "기타"
    except Exception as e:
        print(f"[테마 분류 오류]: {e}")
        return "기타"

# === 7. 캔들차트 저장 ===
def save_candle_chart(code, name):
    try:
        df = yf.download(code, period="3mo", interval="1d", auto_adjust=True)
        if df.empty:
            print(f"[캔들차트 실패] {code} 데이터 없음")
            return None
        filename = f"{code}_chart.png"
        mpf.plot(df, type='candle', volume=True, style='yahoo', title=name, savefig=filename)
        return filename
    except Exception as e:
        print(f"[캔들차트 생성 오류] {name}: {e}")
        return None

# === 8. 텔레그램 메시지 전송 ===
def send_telegram_message(message):
    try:
        requests.post(SEND_MSG_URL, data={'chat_id': TELEGRAM_CHAT_ID, 'text': message})
    except Exception as e:
        print(f"[텔레그램 메시지 전송 오류]: {e}")

# === 9. 텔레그램 이미지 전송 ===
def send_telegram_image(filepath):
    try:
        with open(filepath, 'rb') as photo:
            requests.post(SEND_PHOTO_URL, files={'photo': photo}, data={'chat_id': TELEGRAM_CHAT_ID})
    except Exception as e:
        print(f"[텔레그램 이미지 전송 오류]: {e}")

# === 10. 백테스트/패턴 분석 ===
def check_recent_performance(df):
    try:
        if df is None or df.empty or len(df) < 10:
            return "패턴 분석 불가"
        recent = df['Close'].iloc[-3:]
        if all(x > df['Close'].mean() for x in recent):
            return "최근 3일 상승세 유지"
        else:
            return "변동성 존재"
    except Exception as e:
        return f"패턴 분석 실패: {e}"

# === 11. 저장소 정리 ===
def cleanup_old_files():
    import glob
    for f in glob.glob("*.png"):
        try:
            os.remove(f)
        except:
            pass
