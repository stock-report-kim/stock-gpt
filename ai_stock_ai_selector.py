import os
import requests
import re
import datetime
import yfinance as yf
import matplotlib.pyplot as plt
import mplfinance as mpf
from bs4 import BeautifulSoup
from newspaper import Article
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lex_rank import LexRankSummarizer
from ta.momentum import RSIIndicator

# --- 환경 변수 ---
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
SEND_MSG_URL = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage'
SEND_PHOTO_URL = f'https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto'

HEADERS = {'User-Agent': 'Mozilla/5.0'}

# --- 1. 최신 테마 및 후보 종목 추출 ---
def get_trending_themes_and_stocks():
    print("[1] 네이버 뉴스에서 인기 테마 수집 중...")
    url = "https://finance.naver.com/news/"
    res = requests.get(url, headers=HEADERS)
    soup = BeautifulSoup(res.text, 'lxml')

    # 테마 키워드 추출 (페이지 구조 변경될 수 있음)
    themes = []
    theme_tags = soup.select('.theme_list a')
    for tag in theme_tags[:5]:  # 상위 5개 테마
        themes.append(tag.get_text().strip())

    print(f"발견된 테마: {themes}")

    candidate_stocks = set()
    # 테마별 뉴스에서 종목명 추출 (간단히 한글명 추출, 실제론 DB 매핑 필요)
    for theme in themes:
        search_url = f"https://search.naver.com/search.naver?where=news&query={theme}"
        res = requests.get(search_url, headers=HEADERS)
        soup = BeautifulSoup(res.text, 'lxml')
        news_titles = soup.select(".list_news div.news_area a.news_tit")

        for title in news_titles[:10]:  # 상위 10개 뉴스
            text = title.get_text()
            # 한글 종목명 추출 (간단 패턴, 보완 가능)
            stocks = re.findall(r"[가-힣]{2,5}", text)
            for s in stocks:
                candidate_stocks.add(s)

    print(f"후보 종목 수: {len(candidate_stocks)}")
    return list(candidate_stocks)

# --- 2. 종목명 -> 티커 매핑 (예: 삼성전자 -> 005930.KS) ---
# 실제 환경에서는 종목명-티커 DB를 구축해서 매핑하는게 맞음
# 여기서는 테스트용 샘플 매핑 (필요시 확장)
SAMPLE_NAME_TO_TICKER = {
    "삼성전자": "005930.KS",
    "에코프로": "086520.KQ",
    "하나마이크론": "067310.KQ",
    "카카오": "035720.KQ",
    "셀트리온": "068270.KQ",
}

def name_to_ticker(name):
    return SAMPLE_NAME_TO_TICKER.get(name)

# --- 3. 기술적 분석 필터링 ---
def filter_by_technical(stock_names):
    print("[2] 기술적 분석으로 후보 필터링 중...")
    filtered = []
    for name in stock_names:
        ticker = name_to_ticker(name)
        if not ticker:
            continue
        try:
            df = yf.download(ticker, period='3mo', interval='1d', progress=False)
            if df.empty or len(df) < 20:
                continue

            # RSI 계산
            rsi = RSIIndicator(df['Close']).rsi().iloc[-1]

            # 거래량 최근 10일 평균 대비 마지막 거래량 2배 이상 체크
            avg_vol = df['Volume'].rolling(window=10).mean().iloc[-2]
            recent_vol = df['Volume'].iloc[-1]

            # 기본 조건: RSI 30~70, 거래량 급증
            if 30 < rsi < 70 and recent_vol > 2 * avg_vol:
                filtered.append((name, ticker))
                print(f"선택됨: {name} ({ticker}) RSI: {rsi:.1f} 거래량: {recent_vol} (평균: {avg_vol:.0f})")
        except Exception as e:
            print(f"기술분석 오류 {name}: {e}")
            continue
    return filtered

# --- 4. 뉴스 요약 (Sumy LexRank) ---
def summarize_news(url):
    try:
        article = Article(url)
        article.download()
        article.parse()
        text = article.text
        if len(text) < 200:
            return "뉴스 내용이 충분하지 않습니다."

        parser = PlaintextParser.from_string(text, Tokenizer("korean"))
        summarizer = LexRankSummarizer()
        summary = summarizer(parser.document, sentences_count=3)
        return " ".join([str(sentence) for sentence in summary])
    except Exception as e:
        return f"뉴스 요약 실패: {e}"

# --- 5. 뉴스에서 근거 수집 ---
def get_news_reasons(name):
    search_url = f"https://search.naver.com/search.naver?where=news&query={name}"
    res = requests.get(search_url, headers=HEADERS)
    soup = BeautifulSoup(res.text, 'lxml')
    news_items = soup.select(".list_news div.news_area a.news_tit")

    reasons = []
    for item in news_items[:3]:
        title = item.get_text()
        link = item['href']
        summary = summarize_news(link)
        reasons.append(f"{title}\n요약: {summary}")
    return "\n\n".join(reasons)

# --- 6. 캔들차트 생성 ---
def create_candle_chart(ticker, name):
    df = yf.download(ticker, period='3mo', interval='1d', progress=False)
    df.index.name = 'Date'
    df = df.dropna()

    if df.empty:
        return None

    filename = f"{ticker}.png"
    mc = mpf.make_marketcolors(up='r', down='b', inherit=True)
    s = mpf.make_mpf_style(marketcolors=mc)
    mpf.plot(df, type='candle', style=s, title=f"{name} 12주 캔들차트",
             ylabel='가격', volume=True, savefig=filename)
    return filename

# --- 7. 텔레그램 메시지 전송 ---
def send_telegram_message(text):
    resp = requests.post(SEND_MSG_URL, data={'chat_id': TELEGRAM_CHAT_ID, 'text': text})
    return resp.ok

def send_telegram_photo(filename):
    with open(filename, 'rb') as photo:
        resp = requests.post(SEND_PHOTO_URL, files={'photo': photo}, data={'chat_id': TELEGRAM_CHAT_ID})
    return resp.ok

# --- 8. 메인 함수 ---
def main():
    today = datetime.datetime.now().strftime('%Y-%m-%d')
    print(f"[시작] {today} AI 기반 급등 예상 종목 추천")

    # 1. 후보군 추출
    candidate_names = get_trending_themes_and_stocks()

    # 2. 기술적 분석 필터링
    filtered = filter_by_technical(candidate_names)
    if not filtered:
        print("선별된 종목 없음. 종료.")
        return

    # 3. 급등 예상 상위 3종목 선정 (기술적 조건 순)
    selected = filtered[:3]

    # 4. 종목별 뉴스 기반 근거 수집 및 메시지 작성
    message = f"📈 {today} AI 기반 당일 급등 예상 3종목\n\n"
    for name, ticker in selected:
        message += f"🔹 {name} ({ticker})\n"
        message += "▶ 급등 예상 근거 및 뉴스 요약:\n"
        reasons = get_news_reasons(name)
        message += reasons + "\n\n"

    message += "⚠️ 본 정보는 투자 참고용이며, 투자 책임은 본인에게 있습니다."

    # 5. 메시지 전송
    if send_telegram_message(message):
        print("메시지 전송 성공")

    # 6. 차트 생성 및 전송
    for name, ticker in selected:
        filename = create_candle_chart(ticker, name)
        if filename:
            if send_telegram_photo(filename):
                print(f"{name} 차트 전송 성공")
            else:
                print(f"{name} 차트 전송 실패")
        else:
            print(f"{name} 차트 생성 실패")

if __name__ == '__main__':
    main()
