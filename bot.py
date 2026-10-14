"""Evidence-gated analysis; no network or Slack dependencies."""
import hashlib
import json
import re
from html import escape
from datetime import date, datetime, timedelta, timezone

TICKERS = {"삼성전자": "005930", "SK하이닉스": "000660"}
PROMPT_VERSION = "1"
VERDICTS = {"매수 검토", "관망", "회피 검토", "판단 보류"}


def today():
    return datetime.now(timezone(timedelta(hours=9))).date().isoformat()


class Bot:
    def __init__(self, store, generate=None):
        self.store = store
        self.generate = generate

    def ask(self, question, horizon=None, as_of=None):
        as_of = as_of or today()
        date.fromisoformat(as_of)
        matched = [code for name, code in TICKERS.items()
                   if name.lower() in question.lower() or code in question]
        base = dict(question=question, horizon=horizon, as_of=as_of,
                    prompt_version=PROMPT_VERSION, model=getattr(self.generate, "model", "injected"),
                    sources=[], attempts=0, source_ids=[], principle_ids=[], synthetic=False)
        if len(matched) != 1:
            return self._save(dict(base, status="unsupported", verdict="판단 보류",
                                   reason="삼성전자 또는 SK하이닉스 한 종목씩 질문해주세요."))
        if not horizon or not horizon.strip():
            return self._save(dict(base, status="needs_horizon", verdict="판단 보류",
                                   reason="어느 기간으로 볼까요? 예: 1~3개월, 1년 이상."))
        base["ticker"] = matched[0]
        cutoff = (date.fromisoformat(as_of) - timedelta(days=1)).isoformat()
        sources = [s for s in self.store.sources(as_of)
                   if s["ticker"] in {matched[0], "*"}
                   and (s["kind"] != "principle" or s["reviewed"])
                   and (s["kind"] not in {"market", "sector"} or s["observed_at"] >= cutoff)]
        base["sources"] = sources
        base["synthetic"] = any(s["synthetic"] for s in sources)
        base["principles_version"] = hashlib.sha256(json.dumps(
            [s for s in sources if s["kind"] == "principle"], sort_keys=True,
            ensure_ascii=False).encode()).hexdigest()[:16]
        missing = sorted({"principle", "financial", "market", "sector"} - {s["kind"] for s in sources})
        if missing:
            return self._save(dict(base, status="insufficient", verdict="판단 보류", missing=missing,
                                   reason="판단에 필요한 최신 자료가 부족해요: " + ", ".join(missing)))
        if self.generate is None:
            return self._save(dict(base, status="unconfigured", verdict="판단 보류",
                                   reason="분석 모델이 연결되지 않았어요."))
        context = dict(base)
        for attempt in range(1, 3):
            base["attempts"] = attempt
            try:
                output = self.generate(context)
                self._validate(output, sources)
                return self._save(dict(base, **output, status="answered"))
            except (ValueError, KeyError, TypeError, OSError):
                context["retry_instruction"] = "JSON 형식과 입력 자료 ID만 사용했는지 확인하세요."
        return self._save(dict(base, status="generation_failed", verdict="판단 보류",
                               reason="모델 응답이나 근거를 확인하지 못했어요. 다시 요청해주세요."))

    @staticmethod
    def _validate(output, sources):
        keys = {"verdict", "reason", "counter", "change", "source_ids", "principle_ids"}
        if not isinstance(output, dict) or set(output) != keys or output["verdict"] not in VERDICTS:
            raise ValueError("응답 형식 오류")
        for field in ("reason", "counter", "change"):
            if not isinstance(output[field], str) or not output[field].strip() or len(output[field]) > 1800:
                raise ValueError("설명 필드 오류")
            if re.search(r"https?://|<@|<!", output[field]):
                raise ValueError("본문에 임의 URL 또는 Slack 멘션을 넣을 수 없습니다")
        by_id = {s["id"]: s for s in sources}
        for field in ("source_ids", "principle_ids"):
            ids = output[field]
            if not isinstance(ids, list) or not ids or any(not isinstance(i, str) or i not in by_id for i in ids):
                raise ValueError("출처 오류")
        if any(by_id[i]["kind"] != "principle" for i in output["principle_ids"]):
            raise ValueError("원칙 출처 오류")
        if not {"financial", "market", "sector"}.issubset({by_id[i]["kind"] for i in output["source_ids"]}):
            raise ValueError("기업·시장 근거 부족")

    def _save(self, result):
        result["created_at"] = datetime.now(timezone.utc).isoformat()
        result["analysis_id"] = self.store.save_analysis(result)
        return result


def render(result):
    lines = []
    if result["synthetic"]:
        lines.append("[가상 자료를 사용한 테스트 — 실제 투자 판단이 아닙니다]")
    lines.extend(["*" + result["verdict"] + "*", result["reason"]])
    if result["status"] == "answered":
        lines += ["\n*반대 근거*\n" + result["counter"], "\n*판단이 바뀌는 조건*\n" + result["change"]]
    lines.append("\n기준일: " + result["as_of"] + " · 기간: " + (result["horizon"] or "미정"))
    lines.append("카투 공개 글의 관점을 적용한 AI 판단입니다. 본인의 현재 의견이 아닙니다.")
    used = set(result["source_ids"] + result["principle_ids"])
    for s in result["sources"]:
        if s["id"] in used:
            lines.append(s["id"] + " · " + s["title"] + " · " + s["published_at"] + "\n" + s["url"])
    lines.append("기록 #" + str(result["analysis_id"]))
    return escape("\n".join(lines), quote=False)
