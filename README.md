# 국내 주식 관점 봇

카투 공개 글에서 추출한 판단 기준으로 국내 기업을 분석하고, 사회초년생에게 쉽게 설명하는 Slack 봇의 첫 실행 기반입니다. 카투 본인 또는 공식 봇이 아닙니다.

현재 기본 모드는 **문서 분석**입니다. DART·증권사 API는 나중에 연결합니다. 기업 문서와 검토된 원칙을 읽고 강점·위험·확인할 사항을 분석합니다. 원칙이 없으면 일반 문서 분석이라고 표시하며, 현재 가격에 대한 매수·매도 판단은 보류합니다.

## 문서로 시작하기

UTF-8 Markdown(.md) 또는 텍스트(.txt) 파일을 data/ 아래에 둡니다. JSON으로 만들지 않아도 됩니다. 파일당 최대 150KB이고 원문은 로컬 DB에 저장됩니다. PDF·Word 직접 입력과 Slack 파일 업로드는 아직 지원하지 않습니다.

```sh
python3 app.py add-document data/report.md --ticker 005930 --published-at 2026-10-15 --valid-until 2026-11-15
python3 app.py ask '삼성전자 실적과 위험요인을 분석해줘' --preview --json
```

add-document와 --preview는 **Claude API를 호출하지 않습니다**. 공개 날짜는 문서 작성·공개 날짜, valid-until은 자료를 다시 확인할 날짜로 직접 지정하세요. 관측 날짜는 입력한 당일로 기록되므로 나중에 넣은 자료를 과거 분석에 사용하지 않습니다. 원문 URL을 알고 있으면 --source-url로 지정할 수 있습니다. 생략하면 로컬 파일 경로가 출처가 됩니다. 같은 파일·종목을 다시 넣으면 기존 자료가 갱신됩니다.

미리보기 JSON의 sources에 원문, metrics에 계산 결과와 누락 지표가 들어 있습니다. 일반 문서의 숫자는 모델이 읽지만, 코드로 계산할 비교값은 기존 JSON measurements 형식으로 함께 넣어야 합니다. 원문 숫자 자동 추출·계산은 아직 제공하지 않습니다.

자료를 확인한 뒤 키가 설정된 터미널에서 분석합니다.

```sh
python3 app.py ask '삼성전자 실적과 위험요인을 분석해줘'
```

문서 모드에서는 요청당 유료 호출을 한 번만 하고 자동 재시도하지 않습니다. 같은 질문·기간·기준일·자료·모델·프롬프트 버전이면 저장된 성공 답변을 재사용합니다. --refresh를 붙이면 재생성하며 API 요금이 발생합니다. 다른 질문이나 자료 변경도 새 호출입니다. 동시에 들어온 동일 질문의 호출 합치기는 아직 제공하지 않습니다.

가상 문서로 무료 미리보기만 실행하려면:

```sh
python3 app.py --db data/doc-demo.db add-document examples/document.md --ticker 005930 --published-at 2026-10-15 --valid-until 2026-11-15 --synthetic
python3 app.py --db data/doc-demo.db ask '삼성전자 위험요인을 분석해줘' --preview
```

CLI와 Slack 모두 BOT_MODE=documents가 기본입니다. 시장 자료까지 포함하는 기존 분석은 CLI에서 --mode market 또는 Slack 실행 전 BOT_MODE=market으로 선택합니다. 시장 모드는 투자 기간과 재무·시장·업종·원칙 자료를 요구하고 최대 두 번 호출합니다.

현재 구현: 문서·자료 JSON 입력, 검토된 원칙 적용, 자료 시점 확인, 분석·출처 기록, 무료 미리보기, 저장 답변 재사용, 로컬 질문, Slack 멘션과 스레드 후속 질문. 삼성전자와 SK하이닉스 한 종목씩 지원합니다.

현재 미구현: 최신 기업·시장 자료 자동 수집, Slack 자료실 업로드, 이모지 피드백, 다중 봇 토론, 자동 복기, 모델 추가 학습.

## 로컬 실행

Python 3.9 이상. 자료 입력·기록·테스트에는 표준 라이브러리만 사용합니다.

```sh
python3 app.py import examples/principles.json
python3 app.py ask '삼성전자 지금 어떻게 봐?' --horizon '1~3개월'
python3 app.py history
python3 -m unittest discover -s tests -v
```

원칙 예시는 검토 전 후보입니다. 따라서 위 질문은 자료가 부족하다는 보류 응답을 반환합니다. 실제 답을 생성하려면 원칙을 원문과 대조해 reviewed를 true로 바꾸고 기업·시장·업종 자료를 넣어야 합니다.

답변 생성에는 Claude API를 사용합니다. [Claude Console](https://platform.claude.com/)에서 API 키를 발급하고 환경변수를 설정하세요. API 키는 채팅이나 Git에 넣지 않습니다. 요청에 포함되는 질문과 선택된 자료는 Anthropic으로 전송됩니다.

```sh
# 키를 터미널 기록에 남기지 않고 입력 (macOS zsh)
read -rs 'ANTHROPIC_API_KEY?Claude API key: '; echo
export ANTHROPIC_API_KEY
export CLAUDE_MODEL='claude-sonnet-5-5'
python3 app.py ask '삼성전자 지금 어떻게 봐?' --horizon '1~3개월'
```

Claude [Messages API](https://platform.claude.com/docs/en/api/messages/create)와 [구조화 출력](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)을 사용합니다. 기본 모델은 claude-sonnet-5-5이며 CLAUDE_MODEL로 변경할 수 있습니다. 현재 환경에서는 실제 API 연결을 검증하지 않았습니다. 질문 하나에 최대 두 번 호출하며 각 호출의 출력 상한은 2048토큰입니다. 입력 길이도 비용에 영향을 줍니다. 모델 오류 또는 형식·출처 검증 실패 시 한 번 재시도하고 판단을 보류합니다. 잘린 응답과 거절 응답도 보류합니다. 입력 ID 검사로 출처 조작을 줄이지만, 주장과 출처가 의미상 일치하는지는 별도 평가가 필요합니다.

## 자료 넣기

자료는 JSON 배열로 작성합니다. 원문 파일은 Git에서 제외된 data/ 아래에 두세요.

```json
[
  {
    "id": "사용자가 정한 고유 ID",
    "kind": "market",
    "ticker": "005930",
    "title": "출처를 설명하는 제목",
    "text": "원문 또는 출처가 있는 수치와 설명",
    "url": "https://실제-출처-주소",
    "published_at": "2026-10-14",
    "observed_at": "2026-10-14",
    "valid_until": "2026-10-15",
    "reviewed": true,
    "synthetic": false
  }
]
```

```sh
python3 app.py import data/sources.json
```

kind는 principle(투자 원칙), financial(공시·실적), market(종가·거래량), sector(업종 비교) 중 하나입니다. ticker는 005930, 000660 또는 공통 자료용 *입니다. 같은 ID를 다시 넣으면 자료가 갱신됩니다. 이미 저장한 분석의 자료 스냅샷은 유지됩니다.

published_at은 공개 날짜, observed_at은 해당 자료를 확인한 날짜, valid_until은 재검토해야 하는 날짜입니다. 기준일 이후 공개·관측 자료와 유효기간이 지난 자료는 제외합니다. 시장·업종 자료는 기준일 전날 이후 관측된 것만 사용합니다. 거래일 달력이 없어 주말·휴일에도 보수적으로 보류할 수 있습니다. 수동 입력 값의 진위와 최신 분기 여부는 자동 확인하지 못합니다. 새 중요 뉴스가 나오면 자료를 갱신해야 합니다.

가상 자료에는 synthetic=true를 반드시 넣습니다. examples/synthetic.json은 평가용이며 실제 기업 사실이 아닙니다. 모든 자료를 가상으로 표시했고, historical 실행 예시도 실제 투자 판단이 아닙니다.

```sh
python3 app.py --db data/demo.db import examples/synthetic.json
python3 app.py --db data/demo.db ask '삼성전자 어떻게 봐?' --horizon '1~3개월' --as-of 2026-10-15
```

모델 미설정 시 연결되지 않았다는 보류 답변이 나옵니다. 모델이 연결되면 가상 입력 분석과 가상 자료 표시를 확인할 수 있습니다.

## Slack 연결

1. [Slack 앱 관리](https://api.slack.com/apps)에서 slack-manifest.json으로 앱을 만듭니다.
2. Socket Mode용 앱 토큰(xapp-, connections:write)을 발급합니다.
3. 워크스페이스에 앱을 설치하고 봇 토큰(xoxb-)을 받습니다.
4. 봇을 질문할 채널에 초대합니다.
5. 아래 명령으로 실행합니다. 앱은 최소 app_mentions:read, chat:write 권한만 요청합니다.

```sh
python3 -m venv .venv
. .venv/bin/activate
python3 -m pip install -r requirements.txt
export SLACK_BOT_TOKEN='발급받은-봇-토큰'
export SLACK_APP_TOKEN='발급받은-앱-토큰'
python3 app.py slack
```

환경변수 이름은 .env.example을 참고하세요. .env 자동 로딩은 제공하지 않으며 실제 토큰을 Git에 넣지 마세요. [Slack Socket Mode 공식 안내](https://docs.slack.dev/tools/bolt-python/concepts/socket-mode/)를 기준으로 연결합니다. 실제 워크스페이스 연결은 아직 검증하지 않았습니다.

사용 예:

```text
@카투 관점 AI 삼성전자 지금 어떻게 봐? 1~3개월
```

기간을 생략하면 봇이 물어봅니다. 같은 스레드에서 다시 멘션해 `1~3개월`이라고 답하면 원래 질문을 이어갑니다. 사용자별 스레드 문맥은 분리됩니다. 기간을 정한 뒤 후속 질문도 같은 스레드에서 멘션하세요. 답변은 결론·이유·반대 근거·판단 변경 조건·기준일·출처·기록 번호로 구성됩니다.

동일 이벤트는 중복 생성하지 않고 전달 실패 후 재시도에는 저장된 답변을 사용합니다. Slack 전달 성공 직후 프로세스가 종료되는 경계에서는 중복 전달 가능성이 있습니다. 실행 중 이벤트를 처리하다 비정상 종료하면 processing 상태가 남을 수 있으므로 현재 버전은 개발용 단일 프로세스 운영을 전제로 합니다.

## 다음 작업

실자료 자동 연결이 다음 우선순위입니다. [OpenDART 재무 API](https://opendart.fss.or.kr/guide/detail.do?apiGrpCd=DS003&apiId=2019020)는 인증키가 필요합니다. 주가·거래량·업종 자료는 [KIS 개발자센터](https://apiportal.koreainvestment.com/) 등에서 이용 조건과 필요한 필드를 확인한 뒤 연결해야 합니다. 현재 봇이 이 API에서 자료를 자동 조회하지는 않습니다.

파일은 루트의 app.py, bot.py, model.py, storage.py, metrics.py와 docs/, tests/, examples/로 구성했습니다. 설계는 docs/design.md, 구현 범위는 docs/plan.md에 있습니다.

## 수치 근거

metrics.py가 입력값으로 계산한 결과를 Claude에 전달하고, 같은 값을 답변의 ‘수치 근거’에 직접 표시합니다. 모델이 계산한 숫자에 의존하지 않습니다. 모델의 설명이 모든 숫자를 정확히 인용하는지까지 자동 보장하는 것은 아닙니다.

- 실적: financial 자료의 measurements.revenue, measurements.operating_profit에 current, previous, unit, basis, period, previous_period, period_end, previous_period_end를 넣습니다. 단위·연결/별도 기준·분기/누적 범위가 같은 자료끼리 입력해야 합니다. 이 일치 여부는 입력자가 확인합니다. `100 × (현재/비교값 − 1)`을 계산하며 비교값이 0 이하이면 원금액만 표시합니다.
- 시세: market 자료의 prices는 date, close, volume을 갖는 배열입니다. 종가는 같은 수정주가 기준과 원 단위, 거래량은 주 단위로 넣습니다. 분할 등으로 기준이 바뀐 자료를 그대로 비교하면 안 됩니다.
- 업종: sector 자료의 prices는 date, close 배열입니다. 종목 자료의 처음·마지막 날짜와 정확히 같은 지수 날짜가 있을 때만 수익률을 비교합니다. 두 수익률의 차이는 %가 아닌 %p로 표시합니다. 가격수익률이며 배당은 포함하지 않습니다.
- 거래량: 최신 5개와 그 직전 20개 관측일의 평균을 비교합니다. 최소 25개 관측치가 필요합니다. 거래일 누락 여부와 휴장일은 자동 검증하지 않으므로 자료 제공 시 완전한 거래일 시계열인지 확인해야 합니다.

원자료가 없거나 형식이 맞지 않는 지표는 ‘수치 확인 불가’로 표시하며 임의로 채우지 않습니다. 숫자만으로 매수 결론을 정하지 않습니다. 수치는 계산 버전 및 사용 출처와 함께 분석 기록에 저장됩니다. examples/synthetic.json에 전체 입력 예시가 있습니다. 실자료 자동 수집은 아직 연결되지 않았습니다.
