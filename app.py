"""Local CLI and Slack Socket Mode entry point."""
import argparse
import json
import os
import re

from bot import Bot, TICKERS, render
from model import Claude, DEFAULT_MODEL
from storage import Store


def handle_mention(event_id, event, bot, post):
    if event.get("bot_id") or not bot.store.claim_event(event_id):
        return
    try:
        reply = bot.store.get("replies", event_id)
        if reply is None:
            text = re.sub(r"<@[A-Z0-9]+>", "", event["text"]).strip()
            thread = event.get("thread_ts", event["ts"])
            key = event["channel"] + ":" + thread + ":" + event["user"]
            context = bot.store.get("threads", key) or {}
            horizon_match = re.search(r"(?:\d+\s*[~～-]\s*)?\d+\s*(?:개월|주|년)(?:\s*이상)?|장기|단기", text)
            horizon = horizon_match.group(0) if horizon_match else None
            matched = {code for name, code in TICKERS.items()
                       if name.lower() in text.lower() or code in text}
            previous = {code for name, code in TICKERS.items()
                        if name.lower() in context.get("question", "").lower() or code in context.get("question", "")}
            has_ticker = bool(matched)
            question = text
            if context and not has_ticker:
                question = context["question"]
                if not horizon_match or horizon_match.group(0) != text:
                    question += "\n추가 질문: " + text
                horizon = horizon or context.get("horizon")
            elif context and len(matched) == 1 and matched == previous:
                horizon = horizon or context.get("horizon")
            result = bot.ask(question, horizon)
            if result["status"] != "unsupported":
                bot.store.put("threads", key, dict(question=question, horizon=horizon))
            # Cache before delivery: network retry reuses the original analysis.
            reply = dict(channel=event["channel"], thread_ts=thread, text=render(result),
                         unfurl_links=False, unfurl_media=False)
            bot.store.put("replies", event_id, reply)
        post(**reply)
        bot.store.finish_event(event_id)
    except Exception:
        bot.store.release_event(event_id)
        raise


def run_slack(bot):
    from slack_bolt import App
    from slack_bolt.adapter.socket_mode import SocketModeHandler
    for name in ("SLACK_BOT_TOKEN", "SLACK_APP_TOKEN"):
        if not os.environ.get(name):
            raise ValueError(name + "을 설정해주세요")
    app = App(token=os.environ["SLACK_BOT_TOKEN"])

    @app.event("app_mention")
    def mention(body, event, client, logger):
        try:
            handle_mention(body["event_id"], event, bot, client.chat_postMessage)
        except Exception:
            logger.error("응답 처리 실패. 원문 이벤트와 토큰은 로그에 기록하지 않습니다.")
            client.chat_postMessage(channel=event["channel"], thread_ts=event.get("thread_ts", event["ts"]),
                                    text="분석 저장 또는 전달에 실패했어요. 잠시 후 다시 멘션해주세요.")

    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()


def main():
    parser = argparse.ArgumentParser(description="국내 주식 관점 봇")
    parser.add_argument("--db", default=os.environ.get("BOT_DB", "data/bot.db"))
    commands = parser.add_subparsers(dest="command", required=True)
    ingest = commands.add_parser("import", help="자료 JSON 배열 저장")
    ingest.add_argument("file")
    ask = commands.add_parser("ask", help="로컬 질문")
    ask.add_argument("question")
    ask.add_argument("--horizon")
    ask.add_argument("--as-of")
    ask.add_argument("--json", action="store_true")
    commands.add_parser("history", help="저장한 판단 기록")
    commands.add_parser("slack", help="Slack Socket Mode 실행")
    args = parser.parse_args()
    try:
        store = Store(args.db)
        if args.command == "import":
            with open(args.file, encoding="utf-8") as file:
                records = json.load(file)
            store.import_sources(records)
            print(str(len(records)) + "개 자료 저장")
        elif args.command == "history":
            print(json.dumps(store.history(), ensure_ascii=False, indent=2))
        else:
            api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
            model = Claude(api_key, os.environ.get("CLAUDE_MODEL", DEFAULT_MODEL)) if api_key else None
            bot = Bot(store, model)
            if args.command == "slack":
                run_slack(bot)
            else:
                result = bot.ask(args.question, args.horizon, args.as_of)
                print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else render(result))
    except (ValueError, OSError, ImportError):
        # Never print external HTTP exceptions: request URLs may carry secrets.
        parser.exit(1, "실행 실패: 자료 형식, 파일 경로, 환경변수와 의존성을 확인해주세요.\n")


if __name__ == "__main__":
    main()
