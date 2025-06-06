# ai_stock_ai_selector.py
import os
import pandas as pd
import matplotlib.pyplot as plt
import mplfinance as mpf
import yfinance as yf
from datetime import datetime, timedelta
from telegram import Bot
import requests
from bs4 import BeautifulSoup
from sklearn.linear_model import LogisticRegression
import numpy as np

# === 설정 ===
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# === 종목 리스트 초기 ===
STOCK_LIST = ["005930.KS", "000660.KS", "035420.KQ", "035720.KQ", "247540.KQ", "131970.KQ"]

# === 시가총액 필터링 ===
def get_kosdaq_kospi_stocks():
    url = "https://kind.krx.co.kr/corpgeneral/corpList.do?method=download"
    df = pd.read_html(url, header=0, encoding='euc-kr')[0]
    df = df[['종목코드', '회사명', '업종', '상장일', '시가총액']]
    df['종목코드'] = df['종목코드'].astype(str).str.zfill(6)
    df = df.rename(columns={'회사명': 'Name'})
    df['MarketCap'] = df['시가총액'] * 1e8
    df = df[(df['MarketCap'] >= 5e10) & (df['MarketCap'] <= 8e11)]
    return df

# === 데이터 수집 ===
def get_stock_data(stocks):
    data = {}
    for stock in stocks:
        try:
            df = yf.download(stock, period='3mo', interval='1d')
            if not df.empty:
                data[stock] = df
        except Exception as e:
            print(f"Error fetching {stock}: {e}")
    return data

# === 백테스트용 특징 및 레이블 생성 ===
def generate_features(df):
    df['Return'] = df['Close'].pct_change()
    df['Volume_Change'] = df['Volume'].pct_change()
    df['MA5'] = df['Close'].rolling(5).mean()
    df['MA20'] = df['Close'].rolling(20).mean()
    df.dropna(inplace=True)
    df['Label'] = (df['Close'].shift(-3) > df['Close']).astype(int)
    return df

# === 백테스트 기반 AI 모델 학습 ===
def train_ai_model(data):
    X, y = [], []
    for df in data.values():
        df_feat = generate_features(df.copy())
        X.extend(df_feat[['Return', 'Volume_Change', 'MA5', 'MA20']].values)
        y.extend(df_feat['Label'].values)
    model = LogisticRegression().fit(X, y)
    return model

# === 예측 기반 AI 추천 종목 선정 ===
def predict_rising_stocks(model, data):
    selected = []
    for stock, df in data.items():
        try:
            df_feat = generate_features(df.copy())
            if len(df_feat) == 0:
                continue
            latest = df_feat.iloc[-1][['Return', 'Volume_Change', 'MA5', 'MA20']].values.reshape(1, -1)
            prob = model.predict_proba(latest)[0][1]
            if prob > 0.6:
                selected.append(stock)
        except:
            continue
    return selected[:3]

# === 실시간 검색어 기반 종목 추출 ===
def get_search_trends():
    headers = {'User-Agent': 'Mozilla/5.0'}
    search_stocks = []
    try:
        res = requests.get("https://finance.naver.com/", headers=headers)
        soup = BeautifulSoup(res.text, "html.parser")
        keywords = soup.select(".aside_news .tab_con1 li a")
        for k in keywords:
            name = k.text.strip()
            if name:
                search_stocks.append(name)
    except Exception as e:
        print("[NAVER TREND ERROR]", e)
    search_stocks += ["에코프로", "포스코퓨처엠", "HLB"]
    code_map = {"삼성전자": "005930.KS", "에코프로": "086520.KQ", "포스코퓨처엠": "003670.KQ", "HLB": "028300.KQ"}
    return [code_map[s] for s in search_stocks if s in code_map][:3]

# === 단타 전략 종목 선정 ===
def apply_day_trading_strategies(data):
    selected = []
    for stock, df in data.items():
        avg_vol = df['Volume'][:-1].mean()
        if df['Volume'][-1] > avg_vol * 2:
            selected.append(stock)
    return selected[:3]

# === 요약 생성 ===
def generate_summary(df):
    latest = df.iloc[-1]
    ma5 = df['Close'].rolling(5).mean().iloc[-1]
    ma20 = df['Close'].rolling(20).mean().iloc[-1]
    trend = "골든크로스" if ma5 > ma20 else "데드크로스"
    summary = (
        f"종가: {latest['Close']:.2f}\n"
        f"거래량: {latest['Volume']}\n"
        f"5일선: {ma5:.2f}, 20일선: {ma20:.2f}\n"
        f"이평선 크로스: {trend}\n"
    )
    return summary

# === 차트 생성 ===
def save_chart(stock, df):
    filename = f"{stock}.png"
    mpf.plot(df, type='candle', mav=(5,10,20), volume=True, savefig=filename)
    return filename

# === 텔레그램 전송 ===
def send_to_telegram(stocks, data):
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    for stock in stocks:
        df = data.get(stock)
        if df is None:
            continue
        summary = generate_summary(df)
        chart_path = save_chart(stock, df)
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=f"[{stock}] 요약\n" + summary)
        with open(chart_path, 'rb') as img:
            bot.send_photo(chat_id=TELEGRAM_CHAT_ID, photo=img)

# === 메인 실행 ===
def main():
    cap_df = get_kosdaq_kospi_stocks()
    code_list = cap_df['종목코드'].tolist()
    stock_suffix = ['.KS' if c.startswith('0') else '.KQ' for c in code_list]
    stock_codes = [f"{code}{suffix}" for code, suffix in zip(code_list, stock_suffix)]
    trend_stocks = get_search_trends()
    stock_universe = list(set(stock_codes + trend_stocks))

    data = get_stock_data(stock_universe[:100])  # 최대 100개 제한
    model = train_ai_model(data)
    ai_stocks = predict_rising_stocks(model, data)
    strat_stocks = apply_day_trading_strategies(data)

    selected = list(set(ai_stocks + trend_stocks + strat_stocks))[:9]
    send_to_telegram(selected, data)

if __name__ == "__main__":
    main()

