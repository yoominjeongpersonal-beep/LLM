"""Explicit Slack material collection, reviewed viewpoint extraction, and approval."""
import hashlib
import json
import re
import threading
from datetime import datetime, timezone, timedelta
from html import escape

from model import ModelError

EXTRACTION_VERSION = "1"


def clean(text, bot_user_id=None):
    pattern = re.escape("<@" + bot_user_id + ">") if bot_user_id else r"<@[A-Z0-9]+>"
    return re.sub(pattern, "", text).strip()


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:24]


class Learning:
    def __init__(self, store, generate=None, persona="katoo", bot_user_id=None):
        self.store, self.generate, self.persona = store, generate, persona
        self.bot_user_id = bot_user_id
        self.lock = threading.RLock()

    def key(self, event):
        return self.persona + ":" + event["channel"] + ":" + event.get("thread_ts", event["ts"])

    def handle_mention(self, event_id, event, post):
        text = clean(event.get("text", ""), self.bot_user_id)
        command = text in {"자료 추가", "관점 정리", "승인", "취소"} or text.startswith("수정:") or text.startswith("자료 추가\n")
        with self.lock:
            state = self.store.get("learning_threads", self.key(event))
            if not command and not (state and state["status"] in {"collecting", "review"}):
                return False
            return self._event(event_id, event, post, lambda: self._command(event, text, state))

    def handle_message(self, event_id, event, post):
        if event.get("bot_id") or event.get("subtype") or not event.get("thread_ts"):
            return False
        text = event.get("text", "").strip()
        # Mention events own all commands and mentioned material; avoid double handling.
        if not text or self.bot_user_id and "<@" + self.bot_user_id + ">" in text:
            return False
        with self.lock:
            state = self.store.get("learning_threads", self.key(event))
            if not state or state["status"] not in {"collecting", "review"} or state["owner"] != event.get("user"):
                return False
            return self._event(event_id, event, post, lambda: self._collect(event, state))

    def _event(self, event_id, event, post, action):
        if event.get("bot_id") or not self.store.claim_event("learning:" + event_id):
            return True
        try:
            cached = self.store.get("replies", "learning:" + event_id)
            if cached is None:
                try:
                    text = action()
                except ModelError as error:
                    text = str(error)
                except (ValueError, KeyError, TypeError, OSError):
                    text = "자료 저장 또는 관점 정리에 실패했어요. 승인하지 않았고 자동 재호출도 하지 않았어요."
                cached = dict(channel=event["channel"], thread_ts=event.get("thread_ts", event["ts"]),
                              text=escape(text, quote=False), unfurl_links=False, unfurl_media=False)
                self.store.put("replies", "learning:" + event_id, cached)
            post(**cached)
            self.store.finish_event("learning:" + event_id)
        except Exception:
            self.store.release_event("learning:" + event_id)
            raise
        return True

    def _command(self, event, text, state):
        key = self.key(event)
        if state and state["owner"] != event.get("user"):
            return "이 자료 스레드는 시작한 사람만 추가·수정·승인할 수 있어요. 새 자료 추가 스레드를 열어주세요."
        if text == "자료 추가" or text.startswith("자료 추가\n"):
            if not state:
                state = dict(owner=event["user"], persona=self.persona, channel=event["channel"], status="collecting", draft=None)
            state["status"] = "collecting"
            self.store.put("learning_threads", key, state)
            remainder = text.removeprefix("자료 추가").strip()
            if remainder:
                self._collect(dict(event, text=remainder), state)
            return "자료 스레드를 열었어요. 이 스레드에 글 본문과 원문 링크를 댓글로 넣어주세요. 저장에는 AI를 쓰지 않아요. 다 넣으면 저를 멘션해서 ‘관점 정리’를 요청해주세요. 링크만으로 본문을 가져오지는 않아요."
        if not state or state["status"] == "cancelled":
            return "먼저 저를 멘션해 ‘자료 추가’로 자료 스레드를 열어주세요."
        if text == "취소":
            state["status"] = "cancelled"
            self.store.put("learning_threads", key, state)
            return "수집을 종료했어요. 미승인 초안은 적용하지 않아요. 이미 승인한 원칙은 유지돼요."
        if text == "관점 정리" or text.startswith("수정:"):
            feedback = text[3:].strip() if text.startswith("수정:") else ""
            if text.startswith("수정:") and not feedback:
                return "‘수정: 바꿀 내용’으로 입력해주세요."
            return self._extract(key, state, feedback)
        if text == "승인":
            return self._approve(key, state)
        return self._collect(dict(event, text=text), state)

    def _collect(self, event, state):
        text = event.get("text", "").strip()
        if not text or len(text) > 30000:
            return "본문은 한 댓글당 30,000자 이하로 넣어주세요."
        self.store.save_learning_post(self.key(event), dict(ts=event["ts"], text=text, user=event["user"],
                                                         channel=event["channel"]))
        state["status"] = "collecting"
        self.store.put("learning_threads", self.key(event), state)
        return "원문을 저장했어요. 더 넣어도 되고, 다 넣었으면 저를 멘션해 ‘관점 정리’를 요청해주세요."

    def _materials(self, key):
        result = []
        for p in self.store.learning_posts(key):
            url = "https://slack.com/archives/" + p["channel"] + "/p" + p["ts"].replace(".", "")
            result.append(dict(id="MAT-" + digest([key, p["ts"]]), text=p["text"], url=url))
        return result

    def _extract(self, key, state, feedback):
        materials = self._materials(key)
        body_text = "\n".join(re.sub(r"<https?://[^>]+>|https?://\S+", "", s["text"]) for s in materials).strip()
        if len(body_text) < 20:
            return "관점을 추출할 글 본문이 부족해요. 링크뿐 아니라 본문도 붙여넣어주세요. AI는 호출하지 않았어요."
        if len(materials) > 40 or sum(len(s["text"]) for s in materials) > 100000:
            return "한 스레드에서 최대 40개 댓글·본문 100,000자까지 정리해요. 자료를 나눠주세요. AI는 호출하지 않았어요."
        fingerprint = digest(materials)
        previous = self.store.get("learning_drafts", state["draft"]) if state.get("draft") else None
        if not feedback and previous and previous["fingerprint"] == fingerprint:
            return self._render_draft(previous, cached=True)
        if feedback and previous and previous.get("feedback") == feedback and previous["fingerprint"] == fingerprint:
            return self._render_draft(previous, cached=True)
        if feedback and not previous:
            return "먼저 ‘관점 정리’로 초안을 만들어주세요."
        if self.generate is None:
            return "Claude API 키가 설정되지 않았어요. 원문은 저장돼 있으며 아직 AI를 호출하지 않았어요."
        context = dict(task="extract_viewpoint", persona=self.persona, sources=materials,
                       version=EXTRACTION_VERSION, feedback=feedback,
                       previous=previous["principles"] if feedback else [])
        draft_id = digest([context, getattr(self.generate, "model", "injected")])
        draft = self.store.get("learning_drafts", draft_id)
        if draft is None:
            output = self.generate(context)
            self._validate(output, materials)
            draft = dict(id=draft_id, fingerprint=fingerprint, feedback=feedback, principles=output["principles"], sources=materials)
            self.store.put("learning_drafts", draft_id, draft)
        state.update(draft=draft_id, status="review")
        self.store.put("learning_threads", key, state)
        return self._render_draft(draft)

    @staticmethod
    def _validate(output, materials):
        if not isinstance(output, dict) or set(output) != {"principles"} or not isinstance(output["principles"], list) or not 1 <= len(output["principles"]) <= 3:
            raise ValueError("초안 형식 오류")
        by_id = {s["id"]: s for s in materials}
        for p in output["principles"]:
            if set(p) != {"statement", "conditions", "kind", "source_id", "quote"}:
                raise ValueError("원칙 필드 오류")
            if any(not isinstance(p[k], str) or not p[k].strip() or len(p[k]) > 400 for k in p):
                raise ValueError("원칙 길이 오류")
            if p["kind"] not in {"principle", "situational"} or p["source_id"] not in by_id:
                raise ValueError("원칙 분류 또는 출처 오류")
            if p["quote"] not in by_id[p["source_id"]]["text"]:
                raise ValueError("원문에 없는 인용")

    @staticmethod
    def _render_draft(draft, cached=False):
        lines = ["저장된 초안 재사용 · API 호출 없음" if cached else "관점 초안 · 아직 적용하지 않았어요."]
        for i, p in enumerate(draft["principles"], 1):
            label = "판단 원칙" if p["kind"] == "principle" else "상황별 의견 (영구 원칙으로 적용 안 함)"
            lines += [f"\n{i}. [{label}] {p['statement']}", "적용 조건: " + p["conditions"],
                      "원문 인용: “" + p["quote"] + "” · " + p["source_id"]]
        lines.append("\n같은 스레드에서 저를 멘션해 ‘승인’ 또는 ‘수정: 바꿀 내용’을 보내주세요.")
        return "\n".join(lines)

    def _approve(self, key, state):
        draft = self.store.get("learning_drafts", state["draft"]) if state.get("draft") else None
        if not draft or draft["fingerprint"] != digest(self._materials(key)):
            return "원문이 바뀌었거나 검토할 초안이 없어요. ‘관점 정리’를 다시 요청해주세요."
        if state["status"] == "approved":
            return "이미 승인된 초안이에요. AI는 호출하지 않았어요."
        day = datetime.now(timezone(timedelta(hours=9))).date().isoformat()
        common = dict(ticker="*", persona=self.persona, learning_thread=key, published_at=day,
                      scope_channel=state["channel"], pool="perspective",
                      observed_at=day, valid_until="9999-12-31", synthetic=False, reviewed=True)
        sources = [dict(common, id=s["id"], kind="perspective_material", title="승인된 Slack 원문 (원래 작성일 미확인)",
                        text=s["text"], url=s["url"]) for s in draft["sources"]]
        for i, p in enumerate(draft["principles"]):
            if p["kind"] == "principle":
                original = next(s for s in draft["sources"] if s["id"] == p["source_id"])
                sources.append(dict(common, id="PR-" + draft["id"] + "-" + str(i), kind="principle",
                                    title=p["statement"], text=p["statement"] + "\n적용 조건: " + p["conditions"],
                                    url=original["url"], evidence=p))
        state["status"] = "approved"
        self.store.approve_learning(key, state, sources)
        return "승인했어요. 원문과 판단 원칙을 이 봇의 자료로 반영했어요. 상황별 의견은 당시 발언으로만 참고하며 현재 매수 추천으로 쓰지 않아요. 승인에는 AI를 호출하지 않았어요."
