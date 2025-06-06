# ai_stock_selector.py (v4.0 - 전문가용 무료 AI + 백테스트 + 업종필터 + GPT 테마 분류)

import os
import datetime
import yfinance as yf
import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd
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

# === 업종 매핑 (예시)
SECTOR_MAP = {
    "삼성전자": "반도체",
    "에코프로": "2차전지",
    "하나마이크론": "반도체",
    # 실제 적용 시 CSV나 외부 크롤링 기반으로 확장 가능
}

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
            stocks.append({"name": name, "code": code + suffix})
    return stocks[:30]

# === 2. 기술 분석 ===
def get_last_trading_date(df):
    return df.index[-1].strftime('%Y-%m-%d') if not df.empty else datetime.date.today().isoformat()

def analyze_technical(code):
    try:
        df = yf.download(code, period="3mo", interval="1d", auto_adjust=True)
        if df.empty or len(df) < 20:
            return 0, None, None
        close = df['Close']
        volume = df['Volume']
        macd = MACD(close)
        rsi = RSIIndicator(close).rsi()
        volume_spike = volume.iloc[-1] > volume.rolling(5).mean().iloc[-1] * 2
        ma20 = close.rolling(20).mean().iloc[-1]
        macd_signal = macd.macd_diff().iloc[-1] > 0
        score = int(rsi.iloc[-1] < 40) + int(volume_spike) + int(close.iloc[-1] > ma20) + int(macd_signal)
        return score, get_last_trading_date(df), df
    except Exception as e:
        print(f"Error in analyze_technical({code}): {e}")
        return 0, None, None

# === 3. 뉴스 요약 ===
def fetch_news_titles(name):
    url = f"https://search.naver.com/search.naver?where=news&query={name}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, 'lxml')
    news = soup.select(".list_news div.news_area a.news_tit")
    return [n.text.strip() for n in news[:3]]

def gpt_style_summary(titles):
    if not titles:
        return "관련 뉴스 없음"
    text = " ".join(titles)
    try:
        result = summarizer(text, max_length=60, min_length=10, do_sample=False)
        return result[0]['summary_text']
    except:
        return "뉴스 요약 실패"

# === 4. 테마 분류 ===
def classify_theme(text):
    try:
        result = theme_classifier(text[:200])[0]['label']
        return f"테마 예측: {result}"
    except:
        return "테마 분류 실패"

# === 5. 백테스트 수익률 계산 ===
def backtest_gain(df):
    try:
        entry = df['Close'].iloc[-2]  # 조건 충족 전날 종가
        future = df['Close'].iloc[-1]  # 다음날 종가
        gain = (future - entry) / entry * 100
        return f"예상 수익률(백테스트): {gain:.2f}%"
    except:
        return "수익률 계산 실패"

# === 6. 차트 저장 ===
def save_candle_chart(code, name):
    try:
        df = yf.download(code, period="3mo", interval="1d", auto_adjust=True)
        if df.empty:
            return None
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna().astype(float)
        df.index.name = 'Date'
        filename = f"{code}_chart.png"
        mpf.plot(df, type='candle', volume=True, style='yahoo', title=name, savefig=filename)
        return filename
    except Exception as e:
        print(f"Error generating chart for {code}: {e}")
        return None

# === 7. 텔레그램 전송 ===
def send_telegram_message(text):
    requests.post(SEND_MSG_URL, data={'chat_id': TELEGRAM_CHAT_ID, 'text': text})

def send_telegram_photo(path, caption=""):
    with open(path, 'rb') as img:
        requests.post(SEND_PHOTO_URL, files={'photo': img}, data={'chat_id': TELEGRAM_CHAT_ID, 'caption': caption})

# === 8. 이미지 정리 ===
def cleanup_images():
    for file in os.listdir():
        if file.endswith("_chart.png"):
            try:
                os.remove(file)
            except Exception as e:
                print(f"Error deleting file {file}: {e}")

# === 9. 실행 ===
def main():
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    stocks = fetch_candidate_stocks()
    selected = []
    last_date = today

    for s in stocks:
        sector = SECTOR_MAP.get(s['name'], None)
        if sector and sector not in ["반도체", "2차전지"]:
            continue

        score, date, df = analyze_technical(s['code'])
        if date:
            last_date = date
        if score >= 3:
            titles = fetch_news_titles(s['name'])
            summary = gpt_style_summary(titles)
            theme = classify_theme(summary)
            gain = backtest_gain(df) if df is not None else ""
            selected.append({"name": s['name'], "code": s['code'], "score": score,
                             "summary": summary, "theme": theme, "gain": gain})
        if len(selected) >= 3:
            break

    header = f"📈 [{last_date}] 기준 AI 급등 유망 종목\n\n"
    body = ""
    for s in selected:
        body += f"✅ {s['name']} ({s['code']})\n기술점수: {s['score']}/4\n{s['summary']}\n{s['gain']}\n{s['theme']}\n\n"
    footer = "⚠️ 본 정보는 투자 참고용이며, 투자 판단은 본인 책임입니다."
    full_message = header + body + footer

    send_telegram_message(full_message)

    for s in selected:
        chart = save_candle_chart(s['code'], s['name'])
        if chart:
            send_telegram_photo(chart, caption=s['name'])

    cleanup_images()

if __name__ == '__main__':
    main()
