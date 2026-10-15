# 국내 주식 봇 구현 계획

목표: 수동으로 제공한 원문과 기업·시장 자료로 분석하고 기록한 뒤 슬랙 스레드로 응답한다.

구조: 루트의 bot.py(분석), storage.py(SQLite), model.py(Claude API), app.py(CLI·슬랙) 네 파일. docs에는 문서, tests에는 동작 검증, examples에는 가상 입력만 둔다. 별도 봇별 폴더와 계층별 패키지는 만들지 않는다.

## 순서

- [x] 저장과 분석: tests/test_bot.py에서 미래·오래된 자료 보류, 지원 종목, 기간 확인, 출처 검증, 분석 기록을 검증한다. `python3 -m unittest discover -s tests -v`로 실패 확인 후 구현한다.
- [x] 모델 연결: Claude `/v1/messages` 구조화 JSON 응답을 받고 외부 오류와 잘못된 응답은 보류한다. 통제된 로컬 HTTP 서버로 요청·응답 계약을 검증한다.
- [x] CLI·슬랙: ask/import/history/slack 명령을 제공한다. 기간 후속 질문을 스레드에 저장하고 이벤트 재전송 시 같은 분석을 다시 생성하지 않는다. 외부 Slack API 대신 전달 함수에 주입한 수신기로 메시지·스레드·중복 동작을 검증한다.
- [x] 실행 안내와 검증: README, 환경변수 예시, Slack 앱 manifest, 가상 자료를 작성한다. 테스트, CLI 실행, DB 기록, Git diff를 확인한다.

## 인터페이스

`Store(path)`는 `import_sources(records)`, `sources(as_of)`, `save_analysis(record)`, `history()`, `claim_event(event_id)`, `finish_event(event_id)`, `release_event(event_id)`를 제공한다. 스레드 문맥과 생성 답변도 DB에 저장한다.

`Bot(store, generate=None).ask(question, horizon=None, as_of=None)`는 JSON 직렬화 가능한 dict를 반환한다. generate는 입력 dict를 받아 결론·설명·반대 근거·변경 조건·source_ids·principle_ids를 반환한다. `render(result)`는 Slack용 문자열을 반환한다.

자료는 id, kind(principle/financial/market/sector), ticker, title, text, url, published_at, observed_at, valid_until, reviewed, synthetic 필드를 사용한다. 원칙은 reviewed=true만 적용한다. 관측 시점·공개 날짜 이후로만 자료를 사용하며 valid_until 만료 후 판단하지 않는다. 같은 종류의 여러 자료는 함께 제공한다.

## 범위와 제약

국내 삼성전자·SK하이닉스, 종가 기준 분석. 자료가 실제 최신인지 자동 검증하지 못하는 수동 모드이며 사용자가 출처·시점·유효기간을 제공한다. 시장 자료는 기준일 전날 이후 관측 자료만 허용하는 보수적인 정책을 사용한다. 주말·휴일에는 보류할 수 있으며 거래일 달력 연결 전까지 이를 명시한다.

OpenDART는 인증키가 필요하고 KIS는 앱 인증 및 데이터 범위 확인이 필요하다. 자동 조회는 이번 구현에서 제공하지 않는다. 현재 단계는 수동 자료 입력으로 검증 가능한 실행 기반이며 실시간 분석 완성본으로 표현하지 않는다.

자료 본문은 명령이 아닌 데이터로 전달한다. 모델의 출처 ID를 검사해 외부 출처 조작을 막지만, 주장과 출처의 의미 일치는 사람이 평가해야 한다. 실제 Slack/모델 연결은 토큰·API 키가 없으면 미검증으로 보고한다.

이모지 피드백, 자료실 자동 수집, 다중 봇 토론, 자동 복기는 후속 범위다.

## 검증 기록

로컬 동작 검증, 모델 HTTP 계약 검증, 슬랙 의존성 import를 확인했다. 실제 LLM 생성과 Slack 워크스페이스 연결은 환경 설정 후 추가 검증이 필요하다.

## Claude 전환

사용자 선택에 따라 로컬 모델을 Claude API로 교체한다. ANTHROPIC_API_KEY와 CLAUDE_MODEL을 사용하고 새 폴더나 의존성은 추가하지 않는다. 요청 헤더, 스키마, 잘린 응답·거절 응답, 키 누락을 검증한다. 실제 API 키가 없어 유료 실호출은 미검증이다.
