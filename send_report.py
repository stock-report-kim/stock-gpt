#1. send_report.py

import os
import telegram
from datetime import datetime

# 메시지 예시 (나중에 AI 기반 선정 결과로 대체 가능)

message = f""" 📈 오늘의 급등 유망 종목 리포트 ({datetime.now().strftime('%Y-%m-%d')})

✅ 최우선 추천 종목

1. 삼성전자 (005930)


2. 카카오 (035720)


3. 에코프로 (086520)



✅ 재료 반영 전 이슈 종목

1. 나노씨엠에스 - 수소 관련 해외 계약 루머


2. 모트렉스 - 테슬라 FSD 한국 상륙 기대감


3. 뉴프렉스 - 폴더블 아이폰 수혜 소문



📝 참고: 해당 정보는 투자 조언이 아니며 참고용입니다. """

텔레그램 전송

bot = telegram.Bot(token=os.environ['TELEGRAM_BOT_TOKEN']) chat_id = os.environ['TELEGRAM_CHAT_ID'] bot.send_message(chat_id=chat_id, text=message)

