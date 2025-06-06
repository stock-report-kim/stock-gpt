# ai_stock_selector.py (v8.0 - 기술 분석 제거 + 시가총액 필터 추가)

import os
import datetime
import yfinance as yf
import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd
import requests
from bs4 import BeautifulSoup
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

# === 시가총액 조회 ===
def fetch_market_cap(code):
    try:
        df = yf.Ticker(code).info
        return df.get("marketCap", 0) / 1e8  # 억 단위로 환산
    except:
        return 0

# === 1. 급등 종목 수집 (시가총액 필터 포함) ===
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
            full_code = code + suffix
            cap = fetch_market_cap(full_code)
            if 500 <= cap <= 8000:
                sector = fetch_sector(name)
                stocks.append({"name": name, "code": full_code, "sector": sector})
    print(f"[후보 종목 수집 완료] 총 {len(stocks)}개")
    return stocks[:30]

# === 2. 뉴스 및 커뮤니티 정보 수집 ===
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

# === 3. GPT 뉴스 요약 ===
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

# === 4. 투자매력도 점수화 ===
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

# === 5. 테마 분류 ===
def classify_theme(summary):
    try:
        result = theme_classifier(summary)
        if result and isinstance(result, list):
            return result[0]['label']
        return "기타"
    except Exception as e:
        print(f"[테마 분류 오류]: {e}")
        return "기타"

# === 6. 캔들차트 저장 ===
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

# === 7. 텔레그램 전송 ===
def send_telegram_message(message):
    try:
        requests.post(SEND_MSG_URL, data={'chat_id': TELEGRAM_CHAT_ID, 'text': message})
    except Exception as e:
        print(f"[텔레그램 메시지 전송 오류]: {e}")

def send_telegram_image(filepath):
    try:
        with open(filepath, 'rb') as photo:
            requests.post(SEND_PHOTO_URL, files={'photo': photo}, data={'chat_id': TELEGRAM_CHAT_ID})
    except Exception as e:
        print(f"[텔레그램 이미지 전송 오류]: {e}")

# === 8. 저장소 정리 ===
def cleanup_all_files():
    for f in os.listdir():
        if f.endswith(".png") or f.endswith(".log") or f.endswith(".json"):
            try:
                os.remove(f)
            except:
                pass

# === 9. main ===
def main():
    stocks = fetch_candidate_stocks()
    scored = []
    for s in stocks:
        news_titles = fetch_news_titles(s['name'])
        summary = gpt_style_summary(news_titles)
        invest_score = score_investment_attractiveness(summary)
        theme = classify_theme(summary)
        scored.append({
            "name": s['name'], "code": s['code'],
            "summary": summary, "invest": invest_score,
            "theme": theme, "sector": s['sector']
        })

    top3 = sorted(scored, key=lambda x: -x['invest'])[:3]
    today = datetime.date.today().strftime("%Y-%m-%d")
    msg = f"📈 [{today}] 기준 AI 급등 유망 종목\n\n"
    for s in top3:
        msg += f"🔹 {s['name']} ({s['code']})\n"
        msg += f"투자매력: {s['invest']} / 테마: {s['theme']}\n"
        msg += f"이슈 요약: {s['summary']}\n\n"
    msg += "⚠️ 본 정보는 투자 참고용이며, 투자 판단은 본인 책임입니다."

    send_telegram_message(msg)
    for s in top3:
        chart = save_candle_chart(s['code'], s['name'])
        if chart:
            send_telegram_image(chart)
    cleanup_all_files()

if __name__ == "__main__":
    main()
