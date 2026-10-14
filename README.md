# 국내 주식 관점 봇

카투 공개 글에서 추출한 판단 기준으로 국내 기업을 분석하고, 사회초년생에게 쉽게 설명하는 Slack 봇의 첫 실행 기반입니다. 카투 본인 또는 공식 봇이 아닙니다.

현재 구현: 자료 JSON 입력, 검토된 원칙 적용, 자료 시점 확인, 분석·출처 기록, 로컬 질문, Slack 멘션과 스레드 후속 질문. 삼성전자와 SK하이닉스 한 종목씩 지원합니다.

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

Ollama를 설치하고 사용할 모델을 준비한 뒤 서버를 실행하세요. 선택한 모델 이름을 명시적으로 지정합니다. 모델 자동 다운로드는 하지 않습니다.

```sh
export OLLAMA_MODEL='설치한-모델명'
export OLLAMA_URL='http://127.0.0.1:11434'
python3 app.py ask '삼성전자 지금 어떻게 봐?' --horizon '1~3개월'
```

Ollama 요청 형식은 [공식 Chat API](https://docs.ollama.com/api/chat)를 따릅니다. 현재 환경에서는 실제 모델 연결을 검증하지 않았습니다. 모델 오류 또는 형식·출처 검증 실패 시 한 번 재시도하고 판단을 보류합니다. 입력 ID 검사로 출처 조작을 줄이지만, 주장과 출처가 의미상 일치하는지는 별도 평가가 필요합니다.

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

파일은 루트의 app.py, bot.py, model.py, storage.py와 docs/, tests/, examples/로 구성했습니다. 설계는 docs/design.md, 구현 범위는 docs/plan.md에 있습니다.
