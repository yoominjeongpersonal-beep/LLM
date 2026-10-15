# 투자 관점 봇

## Slack으로 관점 자료 넣기

Slack의 기본 실행 모드는 viewpoint입니다. 사람이 넣는 글은 인물의 판단 방식과 관점을 배우는 자료이고, 기업·시장 사실을 확인할 리서치 자료와 별개입니다. 관점 글을 기업의 최신 사실로 대체하지 않습니다. 자동 검색·DART·증권사 자료 조회는 아직 연결하지 않았습니다.

1. 채널에서 `@katoo-bot 자료 추가`를 보냅니다.
2. 그 메시지의 스레드에 글 **본문과 원문 링크**를 댓글로 넣습니다. 댓글마다 멘션할 필요는 없습니다. 링크만 올리면 본문을 자동으로 가져오지 않습니다.
3. 다 넣었으면 같은 스레드에서 `@katoo-bot 관점 정리`를 보냅니다. 이때 Claude를 한 번 호출합니다.
4. 원칙·적용 조건·원문 인용을 확인하고 `@katoo-bot 승인` 또는 `@katoo-bot 수정: 바꿀 내용`을 보냅니다. 수정 정리는 유료 호출입니다. 승인은 무료입니다.
5. 승인 이후 같은 채널에서 `@katoo-bot 이 관점에서 반도체 투자를 어떻게 판단해?`처럼 질문합니다. 특정 기업 문서가 없어도 관점에 근거한 설명이 가능합니다. 현재 종목 매매 판단에는 별도 최신 자료가 필요하다고 안내합니다.

수집·승인은 시작한 사람만 할 수 있고, 봇 메시지와 자료 스레드 밖의 일반 대화는 저장하지 않습니다. 수집 중에 멘션한 일반 글도 자료로 들어갑니다. 승인 후에는 수집이 끝나므로 그 스레드에서 멘션 질문이 가능합니다. 더 추가하려면 다시 ‘자료 추가’를 보내세요. ‘취소’는 수집을 종료하며 이미 승인된 원칙을 삭제하지 않습니다. 원문 댓글을 수정·삭제하는 이벤트는 현재 동기화하지 않으므로 수정할 본문을 새 댓글로 올리고 원칙 초안을 재검토해야 합니다.

원칙과 상황별 의견을 구분하고, 상황별 의견을 영구 원칙으로 적용하지 않습니다. 원래 작성 날짜가 확인되지 않은 글은 그렇게 표시하며 승인 날짜를 원문의 작성 날짜라고 주장하지 않습니다. 초안 인용은 실제 입력 본문에 있는지 검증합니다. 다른 인물 봇과 자료를 섞지 않도록 BOT_PERSONA로 구분합니다. 승인 자료는 승인한 채널 안에서만 Slack 답변에 사용합니다. 로컬 CLI는 운영자용이므로 해당 봇의 승인 자료를 모두 읽을 수 있습니다.

원문과 초안은 data/bot.db의 learning_posts, learning_drafts 등에 저장하고 승인 자료는 sources로 반영합니다. GitHub 저장은 아직 구현하지 않았고, 공개 원격 저장소에 원문을 push하지 않습니다. 모델 자체를 재훈련하는 방식이 아닙니다.

추출은 스레드당 최대 40개 댓글·100,000자입니다. 원문 저장과 승인에는 Claude를 호출하지 않습니다. 같은 원문 초안·같은 수정 요청은 재사용합니다. 답변에는 관련 원문 최대 8개·본문 60,000자와 연결 원칙 최대 20개를 선정해 전달하며, 동일 입력의 성공 답변은 재사용합니다. 한도 내 관련도 선택은 키워드 기반이고 의미 검색은 아직 없습니다. 이벤트 중복·전달 재시도에는 저장된 결과를 사용하지만 프로세스 강제 종료 직전 호출 비용까지 정확히 한 번 보장하지는 않습니다.

### 기존 Slack 앱 설정 갱신

일반 스레드 댓글을 받으려면 권한과 이벤트를 갱신해야 합니다. Slack 앱의 **App Manifest**에서 프로젝트의 slack-manifest.json 내용으로 저장하고 **Reinstall to Workspace**를 진행하세요. 추가 권한은 channels:history, groups:history이고 이벤트는 message.channels, message.groups입니다. 기존 app_mentions:read, chat:write와 Socket Mode는 유지합니다. 앱은 채널 이벤트를 수신하되 위에서 설명한 수집 스레드만 저장합니다.

같은 토큰을 설정한 터미널에서 실행 중인 봇을 Ctrl+C로 종료하고 다시 실행합니다.

```sh
export BOT_MODE=viewpoint
.venv/bin/python app.py slack
```

로컬에서 승인된 관점만 확인하고 싶다면 `python3 app.py ask '이 봇의 투자 관점은?' --mode viewpoint --preview --json`으로 무료 미리보기를 볼 수 있습니다.

아래의 문서 분석 모드 설명은 이전 구현 및 수동 리서치 검증용입니다. 사람의 기본 사용 흐름은 위의 Slack 관점 자료 전달이며 기업 문서를 매번 업로드하는 방식이 아닙니다.

카투 공개 글에서 추출한 판단 기준으로 국내 기업을 분석하고, 사회초년생에게 쉽게 설명하는 Slack 봇의 첫 실행 기반입니다. 카투 본인 또는 공식 봇이 아닙니다.

로컬 CLI의 수동 검증 모드는 **문서 분석**입니다. Slack 기본 모드는 위에서 설명한 viewpoint이며, 관점 글을 기업 분석 문서와 구분합니다. DART·증권사 API는 나중에 연결합니다. 수동 문서 모드는 기업 문서와 검토된 원칙을 읽고 강점·위험·확인할 사항을 분석합니다. 원칙이 없으면 일반 문서 분석이라고 표시하며, 현재 가격에 대한 매수·매도 판단은 보류합니다.

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
