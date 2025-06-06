# ai_stock_selector.py (v8.0 - 루머/SNS 기반 추출 + AI 선정 병렬 비교)

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
            mcap = fetch_market_cap(code)
            if 500 <= mcap <= 8000:
                stocks.append({"name": name, "code": code + suffix, "sector": sector, "mcap": mcap})
    print(f"[후보 종목 수집 완료] 총 {len(stocks)}개")
    return stocks[:30]

# === 시가총액 수집 ===
def fetch_market_cap(code):
    try:
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        headers = {'User-Agent': 'Mozilla/5.0'}
        res = requests.get(url, headers=headers)
        soup = BeautifulSoup(res.text, 'lxml')
        mcap_tag = soup.select_one(".first .blind")
        if mcap_tag:
            mcap_text = mcap_tag.text.replace(",", "")
            return int(int(mcap_text) / 1e8)  # 억 원 단위
    except:
        pass
    return 0

# === 커뮤니티 및 SNS/블로그 기반 루머 수집 ===
def fetch_rumor_titles(name):
    titles = []
    try:
        # 디시인사이드 클리앙 등 수집 예시 (간소화)
        for site in [
            f"https://www.clien.net/service/search?q={name}",
            f"https://www.dcinside.com/search/{name}",
            f"https://search.naver.com/search.naver?where=view&query={name}"
        ]:
            res = requests.get(site, headers={'User-Agent': 'Mozilla/5.0'})
            soup = BeautifulSoup(res.text, 'lxml')
            titles += [t.text.strip() for t in soup.find_all(['h3', 'a']) if name in t.text][:2]
    except Exception as e:
        print(f"[루머 수집 오류] {name}: {e}")
    return titles

# === 2. 요약 및 AI 분석 ===
def gpt_style_summary(titles):
    if not titles:
        return "관련 뉴스 및 루머 없음"
    text = "\n".join(["- " + t for t in titles])
    try:
        prompt = f"다음 정보는 루머/게시글입니다. 투자자 관점에서 핵심 이슈를 요약해줘:\n{text}"
        result = summarizer(prompt, max_length=80, min_length=20, do_sample=False)
        return result[0]['summary_text']
    except Exception as e:
        print(f"[요약 오류]: {e}")
        return "요약 실패"

def score_investment_attractiveness(summary):
    try:
        result = scorer(summary)
        if result and isinstance(result, list):
            label = result[0]['label']
            return int(label[0])
    except:
        pass
    return 0

def classify_theme(summary):
    try:
        result = theme_classifier(summary)
        if result and isinstance(result, list):
            return result[0]['label']
    except:
        pass
    return "기타"

# === 3. 차트 저장 ===
def save_candle_chart(code, name):
    try:
        df = yf.download(code, period="3mo", interval="1d", auto_adjust=True)
        df = df.astype(float)
        if df.empty:
            return None
        filename = f"{code}_chart.png"
        mpf.plot(df, type='candle', volume=True, style='yahoo', title=name, savefig=filename)
        return filename
    except:
        return None

# === 4. 텔레그램 전송 ===
def send_telegram_message(message):
    try:
        requests.post(SEND_MSG_URL, data={'chat_id': TELEGRAM_CHAT_ID, 'text': message})
    except:
        pass

def send_telegram_image(filepath):
    try:
        with open(filepath, 'rb') as photo:
            requests.post(SEND_PHOTO_URL, files={'photo': photo}, data={'chat_id': TELEGRAM_CHAT_ID})
    except:
        pass

# === 5. 저장소 정리 ===
def cleanup_all_files():
    for f in os.listdir():
        if f.endswith(".png"):
            try: os.remove(f)
            except: pass

# === 6. main ===
def main():
    stocks = fetch_candidate_stocks()
    rumor_results, ai_results = [], []

    for s in stocks:
        rumors = fetch_rumor_titles(s['name'])
        summary = gpt_style_summary(rumors)
        invest_score = score_investment_attractiveness(summary)
        theme = classify_theme(summary)
        if invest_score >= 3:
            rumor_results.append({"name": s['name'], "code": s['code'], "summary": summary, "invest": invest_score, "theme": theme})
        ai_results.append({"name": s['name'], "code": s['code'], "summary": summary, "invest": invest_score, "theme": theme})

    top_rumors = sorted(rumor_results, key=lambda x: -x['invest'])[:3]
    top_ai = sorted(ai_results, key=lambda x: -x['invest'])[:3]

    today = datetime.date.today().strftime("%Y-%m-%d")
    msg = f"📌 [{today}] 급등 예상 종목 리스트\n\n"
    msg += "[🔥 루머/이벤트 기반 급등 유망주]\n"
    for s in top_rumors:
        msg += f"🔸{s['name']} | 매력도 {s['invest']} | 테마: {s['theme']}\n{ s['summary'] }\n\n"
    msg += "[🤖 AI 분석 기반 유망주]\n"
    for s in top_ai:
        msg += f"🔹{s['name']} | 매력도 {s['invest']} | 테마: {s['theme']}\n{ s['summary'] }\n\n"
    msg += "⚠️ 본 정보는 참고용이며, 투자 판단은 본인 책임입니다."

    send_telegram_message(msg)
    for s in top_rumors[:1] + top_ai[:1]:
        chart = save_candle_chart(s['code'], s['name'])
        if chart:
            send_telegram_image(chart)
    cleanup_all_files()

if __name__ == "__main__":
    main()
