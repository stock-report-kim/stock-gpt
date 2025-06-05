import os
import requests
import datetime
import yfinance as yf
import matplotlib.pyplot as plt
from bs4 import BeautifulSoup

# 환경 변수
TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHAT_ID = os.environ['TELEGRAM_CHAT_ID']
SEND_MSG_URL = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
SEND_PHOTO_URL = f'https://api.telegram.org/bot{TOKEN}/sendPhoto'

# 날짜
today = datetime.datetime.now().strftime('%Y-%m-%d')

# 종목 목록
priority_stocks = ["005930.KS", "086520.KQ", "067310.KQ"]
stock_names = {"005930.KS": "삼성전자", "086520.KQ": "에코프로", "067310.KQ": "하나마이크론"}

# 뉴스 수집
def fetch_news(query):
    headers = {'User-Agent': 'Mozilla/5.0'}
    url = f"https://search.naver.com/search.naver?where=news&query={query}"
    res = requests.get(url, headers=headers)
    soup = BeautifulSoup(res.text, 'lxml')
    news_items = soup.select(".list_news div.news_area a.news_tit")
    links = [item['href'] for item in news_items[:3]]
    titles = [item.get_text() for item in news_items[:3]]
    return list(zip(titles, links))

# 간단 요약 (룰 기반)
def simple_summary(news_list):
    summary_lines = []
    for title, link in news_list:
        if any(word in title for word in ["실적", "증가", "호재", "수주", "신규", "급등"]):
            summary_lines.append(f"✔️ {title}")
        elif any(word in title for word in ["하락", "급락", "적자", "리스크"]):
            summary_lines.append(f"⚠️ {title}")
        else:
            summary_lines.append(f"- {title}")
    return "\n".join(summary_lines)

# 뉴스 요약 메시지 구성
news_summaries = ""
for code in priority_stocks:
    name = stock_names[code]
    news = fetch_news(name)
    summary = simple_summary(news)
    news_summaries += f"📰 {name} 뉴스 요약:\n{summary}\n\n"

# 텔레그램 메시지
message = f"""
📈 오늘의 단타 유망주 보고서 ({today})

✅ AI 추천 종목:
- 삼성전자
- 에코프로
- 하나마이크론

📌 뉴스 기반 키워드 요약:
{news_summaries}

📊 종가 차트는 아래 참고
※ 본 정보는 투자 권유가 아닙니다.
"""

# 메시지 전송
requests.post(SEND_MSG_URL, data={'chat_id': CHAT_ID, 'text': message})

# 차트 생성 및 전송
for code in priority_stocks:
    stock = yf.Ticker(code)
    hist = stock.history(period="7d")
    plt.figure(figsize=(6, 4))
    plt.plot(hist.index, hist['Close'], marker='o', color='blue')
    plt.title(f"{stock_names[code]} 7일 종가")
    plt.xlabel("날짜")
    plt.ylabel("가격")
    plt.grid(True)
    filename = f"{code}.png"
    plt.savefig(filename)
    plt.close()

    with open(filename, 'rb') as photo:
        requests.post(SEND_PHOTO_URL, files={'photo': photo}, data={'chat_id': CHAT_ID})
