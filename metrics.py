"""Calculate auditable numerical evidence from supplied observations."""
import math
from datetime import date

LABELS = {"revenue": "매출", "operating_profit": "영업이익",
          "relative_return": "업종 대비 수익률", "volume_change": "거래량 변화"}


def number(value):
    if type(value) not in (int, float):
        raise ValueError("유한한 숫자가 필요합니다")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise ValueError("유한한 숫자가 필요합니다")
    return value


def percentage(current, previous):
    return round((current / previous - 1) * 100, 2) if previous > 0 else None


def price_series(source):
    points = source.get("prices", [])
    if not isinstance(points, list):
        raise ValueError("가격 배열 오류")
    seen = set()
    for p in points:
        day = date.fromisoformat(p["date"])
        if p["date"] in seen or day > date.fromisoformat(source["published_at"]):
            raise ValueError("중복 또는 미래 가격")
        seen.add(p["date"])
        if number(p["close"]) <= 0:
            raise ValueError("양수 가격 필요")
        if "volume" in p and number(p["volume"]) < 0:
            raise ValueError("음수 거래량")
    return sorted(points, key=lambda p: p["date"])


def calculate_metrics(sources):
    items = []
    series = {}
    # Use the latest eligible record per metric; do not combine financial bases.
    for source in sorted(sources, key=lambda s: (s["published_at"], s["id"]), reverse=True):
        if source["kind"] == "financial":
            measurements = source.get("measurements", {})
            if not isinstance(measurements, dict):
                continue
            for key in ("revenue", "operating_profit"):
                if key not in measurements or any(m["key"] == key for m in items):
                    continue
                try:
                    m = measurements[key]
                    current, previous = number(m["current"]), number(m["previous"])
                    end, prior = date.fromisoformat(m["period_end"]), date.fromisoformat(m["previous_period_end"])
                    if not prior < end <= date.fromisoformat(source["published_at"]):
                        continue
                    if any(not isinstance(m[k], str) or not m[k].strip() for k in ("unit", "basis", "period", "previous_period")):
                        continue
                    change = percentage(current, previous)
                    comparison = m["previous_period"] + " → " + m["period"] + " · " + m["basis"]
                    delta = f"{change:+.2f}%" if change is not None else "비교값이 0 이하라 증감률 계산 제외"
                    items.append(dict(key=key, current=current, previous=previous, unit=m["unit"],
                                      change_pct=change, comparison=comparison, source_ids=[source["id"]],
                                      display=f"{LABELS[key]}: {previous:,.2f} → {current:,.2f} {m['unit']} ({delta}) · {comparison}"))
                except (KeyError, ValueError, TypeError, OverflowError):
                    continue
        if source["kind"] in {"market", "sector"} and source["kind"] not in series:
            try:
                points = price_series(source)
                if points:
                    series[source["kind"]] = (source, points)
            except (KeyError, ValueError, TypeError):
                continue
    if "market" in series:
        market, prices = series["market"]
        if len(prices) >= 25 and all("volume" in p for p in prices[-25:]):
            previous = sum(p["volume"] for p in prices[-25:-5]) / 20
            recent = sum(p["volume"] for p in prices[-5:]) / 5
            change = percentage(recent, previous)
            if change is not None:
                comparison = f"직전 20개 관측일({prices[-25]['date']}~{prices[-6]['date']}) 대비 최근 5개 관측일({prices[-5]['date']}~{prices[-1]['date']})"
                items.append(dict(key="volume_change", recent_average=recent, previous_average=previous,
                                  change_pct=change, source_ids=[market["id"]], comparison=comparison,
                                  display=f"일평균 거래량: {previous:,.2f} → {recent:,.2f} 주 ({change:+.2f}%) · {comparison}"))
        if len(prices) >= 2 and "sector" in series:
            sector, sector_prices = series["sector"]
            # Returns must use identical endpoints, never nearby dates.
            lookup = {p["date"]: p for p in sector_prices}
            first, last = prices[0], prices[-1]
            if first["date"] in lookup and last["date"] in lookup:
                stock = percentage(last["close"], first["close"])
                benchmark = percentage(lookup[last["date"]]["close"], lookup[first["date"]]["close"])
                difference = round(stock - benchmark, 2)
                comparison = first["date"] + "~" + last["date"]
                items.append(dict(key="relative_return", stock_return_pct=stock, sector_return_pct=benchmark,
                                  difference_pp=difference, comparison=comparison,
                                  source_ids=[market["id"], sector["id"]],
                                  display=f"주가 {stock:+.2f}% / {sector.get('title', '업종')} {benchmark:+.2f}% · 차이 {difference:+.2f}%p · {comparison}"))
    found = {m["key"] for m in items}
    missing = [label + (" 증감률" if key in {"revenue", "operating_profit"} else "")
               for key, label in LABELS.items() if key not in found]
    return {"version": "1", "items": items, "missing": missing}
