"""Home 도메인 패키지.

AppRegistry 가 부팅 시 이 패키지를 import 한다(컨벤션 발견). 그 import-time 부수효과로
access-log sink 를 미들웨어에 등록한다(과거 config.py 가 하던 역할).
"""
from app.domains.home.access_log_sink import register_sink

register_sink()
