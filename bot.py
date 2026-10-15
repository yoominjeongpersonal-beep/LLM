"""Evidence-gated analysis; no network or Slack dependencies."""
import hashlib
import json
import re
from html import escape
from datetime import date, datetime, timedelta, timezone
from model import ModelError
from metrics import calculate_metrics

TICKERS = {"삼성전자": "005930", "SK하이닉스": "000660"}
PROMPT_VERSION = "4"
VERDICTS = {"매수 검토", "관망", "회피 검토", "판단 보류"}
DOCUMENT_VERDICTS = {"긍정", "주의", "혼재", "자료 부족", "판단 보류"}


def today():
    return datetime.now(timezone(timedelta(hours=9))).date().isoformat()


class Bot:
    def __init__(self, store, generate=None, mode="market", persona="katoo"):
        if mode not in {"market", "documents", "viewpoint"}:
            raise ValueError("지원하지 않는 분석 모드")
        self.store = store
        self.generate = generate
        self.mode = mode
        self.persona = persona

    def ask(self, question, horizon=None, as_of=None, preview=False, refresh=False, channel=None):
        as_of = as_of or today()
        date.fromisoformat(as_of)
        matched = [code for name, code in TICKERS.items()
                   if name.lower() in question.lower() or code in question]
        base = dict(question=question, horizon=horizon, as_of=as_of, mode=self.mode, persona=self.persona, channel=channel,
                    prompt_version=PROMPT_VERSION, model=getattr(self.generate, "model", "injected"),
                    sources=[], attempts=0, source_ids=[], principle_ids=[], synthetic=False,
                    metrics={"items": [], "missing": []})
        if self.mode != "viewpoint" and len(matched) != 1:
            result = dict(base, status="unsupported", verdict="판단 보류",
                          reason="삼성전자 또는 SK하이닉스 한 종목씩 질문해주세요.")
            return result if preview else self._save(result)
        if self.mode == "market" and (not horizon or not horizon.strip()):
            result = dict(base, status="needs_horizon", verdict="판단 보류",
                          reason="어느 기간으로 볼까요? 예: 1~3개월, 1년 이상.")
            return result if preview else self._save(result)
        base["ticker"] = matched[0] if len(matched) == 1 else "*"
        cutoff = (date.fromisoformat(as_of) - timedelta(days=1)).isoformat()
        sources = [s for s in self.store.sources(as_of)
                   if (self.mode == "viewpoint" or s["ticker"] in {base["ticker"], "*"})
                   and s.get("persona", "katoo") == self.persona
                   and (channel is None or not s.get("learning_thread") or s.get("scope_channel") == channel)
                   and (s["kind"] != "principle" or s["reviewed"])
                   and (self.mode != "documents" or s["kind"] in {"document", "financial", "principle"})
                   and (self.mode != "viewpoint" or s.get("learning_thread") and s["reviewed"] and s["kind"] in {"principle", "perspective_material"})
                   and (s["kind"] not in {"market", "sector"} or s["observed_at"] >= cutoff)]
        if self.mode == "viewpoint":
            # Small bounded retrieval: retain evidence for the selected persona principles.
            words = [w.lower() for w in re.findall(r"[\w]+", question) if len(w) > 1]
            ranked = sorted((s for s in sources if s["kind"] == "perspective_material"),
                            key=lambda s: (sum(w in s["text"].lower() for w in words), s["published_at"], s["id"]), reverse=True)
            selected, size = [], 0
            for source in ranked:
                if len(selected) >= 8 or size + len(source["text"]) > 60000:
                    continue
                selected.append(source)
                size += len(source["text"])
            ids = {s["id"] for s in selected}
            sources = selected + [s for s in sources if s["kind"] == "principle" and s.get("evidence", {}).get("source_id") in ids][:20]
        base["sources"] = sources
        # Interpretation material is never a substitute for independently checked facts.
        base["perspective_sources"] = [s for s in sources if s["kind"] in {"principle", "perspective_material"}]
        base["research_sources"] = [s for s in sources if s["kind"] in {"document", "financial", "market", "sector"}]
        base["research_status"] = "자동 검색 미연결" if self.mode == "viewpoint" else "입력 자료 기준"
        base["metrics"] = calculate_metrics(sources)
        base["synthetic"] = any(s["synthetic"] for s in sources)
        base["principles_version"] = hashlib.sha256(json.dumps(
            [s for s in sources if s["kind"] == "principle"], sort_keys=True,
            ensure_ascii=False).encode()).hexdigest()[:16]
        missing = sorted({"principle", "financial", "market", "sector"} - {s["kind"] for s in sources})
        if self.mode == "documents":
            missing = [] if any(s["kind"] in {"document", "financial"} for s in sources) else ["document"]
        if self.mode == "viewpoint":
            missing = [] if any(s["kind"] == "perspective_material" for s in sources) else ["승인된 관점 자료 (먼저 ‘자료 추가’로 글을 넣어주세요)"]
        if preview:
            return dict(base, status="preview", verdict="미리보기", missing=missing,
                        reason=f"API 호출 없음 · 선택 자료 {len(sources)}개 · " +
                        ("부족한 자료: " + ", ".join(missing) if missing else "문서·수치·출처를 확인한 뒤 분석하세요."))
        if missing:
            return self._save(dict(base, status="insufficient", verdict="판단 보류", missing=missing,
                                   reason="판단에 필요한 최신 자료가 부족해요: " + ", ".join(missing)))
        if self.generate is None:
            return self._save(dict(base, status="unconfigured", verdict="판단 보류",
                                   reason="분석 모델이 연결되지 않았어요."))
        cache_key = hashlib.sha256(json.dumps(base, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        if not refresh:
            for previous in self.store.history():
                if previous.get("cache_key") == cache_key and previous["status"] == "answered":
                    return dict(previous, cached=True)
        base["cache_key"] = cache_key
        context = dict(base)
        error_code = "invalid_response"
        error_reason = "모델 응답의 형식이나 출처 검증에 실패했어요."
        # Document experiments make a single paid call; retry is explicit.
        for attempt in range(1, 3 if self.mode == "market" else 2):
            base["attempts"] = attempt
            try:
                output = self.generate(context)
                self._validate(output, sources, self.mode)
                return self._save(dict(base, **output, status="answered"))
            except ModelError as error:
                error_code, error_reason = error.code, str(error)
                if not error.retryable:
                    break
            except OSError:
                error_code, error_reason = "network", "Claude API 연결 중 오류가 발생했어요. 네트워크를 확인해주세요."
            except (ValueError, KeyError, TypeError):
                error_code, error_reason = "invalid_response", "모델 응답의 형식이나 출처 검증에 실패했어요."
                context["retry_instruction"] = "JSON 형식과 입력 자료 ID만 사용했는지 확인하세요."
        return self._save(dict(base, status="generation_failed", verdict="판단 보류",
                               error_code=error_code, reason=error_reason))

    @staticmethod
    def _validate(output, sources, mode="market"):
        keys = {"verdict", "reason", "counter", "change", "source_ids", "principle_ids"}
        verdicts = DOCUMENT_VERDICTS if mode in {"documents", "viewpoint"} else VERDICTS
        if not isinstance(output, dict) or set(output) != keys or output["verdict"] not in verdicts:
            raise ValueError("응답 형식 오류")
        for field in ("reason", "counter", "change"):
            if not isinstance(output[field], str) or not output[field].strip() or len(output[field]) > 1800:
                raise ValueError("설명 필드 오류")
            if re.search(r"https?://|<@|<!", output[field]):
                raise ValueError("본문에 임의 URL 또는 Slack 멘션을 넣을 수 없습니다")
        by_id = {s["id"]: s for s in sources}
        for field in ("source_ids", "principle_ids"):
            ids = output[field]
            allow_empty = field == "principle_ids" and mode in {"documents", "viewpoint"} and not any(s["kind"] == "principle" for s in sources)
            if not isinstance(ids, list) or (not ids and not allow_empty) or any(not isinstance(i, str) or i not in by_id for i in ids):
                raise ValueError("출처 오류")
        if any(by_id[i]["kind"] != "principle" for i in output["principle_ids"]):
            raise ValueError("원칙 출처 오류")
        kinds = {by_id[i]["kind"] for i in output["source_ids"]}
        if mode == "viewpoint":
            if "perspective_material" not in kinds:
                raise ValueError("관점 원문 출처 부족")
        elif mode == "documents":
            if not kinds.intersection({"document", "financial"}):
                raise ValueError("기업 분석 출처 부족")
        elif not {"financial", "market", "sector"}.issubset(kinds):
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
    if result.get("cached"):
        lines.append("저장된 답변 재사용 · API 재호출 없음")
    if result["status"] == "preview":
        for s in result["sources"]:
            lines.append(s["id"] + " · " + s["title"] + " · " + s["published_at"] + "\n" + s["url"])
        for m in result["metrics"]["items"]:
            lines.append(m["display"])
    if result["status"] == "answered":
        if result.get("metrics", {}).get("items"):
            lines.append("\n*수치 근거 (코드 계산)*")
            for m in result["metrics"]["items"]:
                lines.append("• " + m["display"] + " · 출처 " + ", ".join(m["source_ids"]))
        if result.get("metrics", {}).get("missing") and result.get("mode") != "viewpoint":
            lines.append("수치 확인 불가: " + ", ".join(result["metrics"]["missing"]))
        lines += ["\n*반대 근거*\n" + result["counter"], "\n*판단이 바뀌는 조건*\n" + result["change"]]
    lines.append("\n기준일: " + result["as_of"] + " · 기간: " + (result["horizon"] or "미정"))
    if result.get("mode") == "documents":
        lines.append("문서 기준 기업 분석입니다. 현재 가격의 매수·매도 판단은 보류합니다.")
    if result.get("mode") == "viewpoint":
        lines.append("승인된 글을 바탕으로 한 관점 해석입니다. 최신 실적·시세 확인 없이 현재 매매 판단을 내리지 않습니다.")
    if result.get("mode") == "documents" and not result["principle_ids"]:
        lines.append("검토된 투자 원칙이 적용되지 않은 일반 문서 분석입니다.")
    else:
        lines.append("카투 공개 글의 관점을 적용한 AI 판단입니다. 본인의 현재 의견이 아닙니다.")
    used = set(result["source_ids"] + result["principle_ids"])
    if result["status"] == "answered":
        used.update(id for m in result.get("metrics", {}).get("items", []) for id in m["source_ids"])
    for s in result["sources"]:
        if s["id"] in used:
            lines.append(s["id"] + " · " + s["title"] + " · " + s["published_at"] + "\n" + s["url"])
    if "analysis_id" in result:
        lines.append("기록 #" + str(result["analysis_id"]))
    return escape("\n".join(lines), quote=False)
