"""Bounded metric assertions and source-aware sentiment checks; no inference."""
from decimal import Decimal, InvalidOperation
import re

SLOTS = {"1": "content_1", "2": "content_2"}
METRIC = r"(?P<metric>(?:(?:confirmed|public|observed|lifetime) )*(?:views|reach|engagement rate))"
SUBJECT = r"content (?P<slot>[12])"
DIRECTIONAL = (
    re.compile(SUBJECT + r" has (?P<direction>more|higher|fewer|lower|less) " + METRIC + r"(?: than content (?P<other>[12]))?", re.I),
    re.compile(SUBJECT + r" (?P<direction>leads|is ahead) (?:in|on) " + METRIC + r"(?: (?:compared with|over) content (?P<other>[12]))?", re.I),
    re.compile(r"(?P<direction>more|higher|fewer|lower) " + METRIC + r" (?:were|was) recorded for " + SUBJECT, re.I),
    re.compile(r"the " + METRIC + r" (?P<direction>leader) is " + SUBJECT, re.I),
)
COUNT = re.compile(SUBJECT + r" (?:has|received|recorded) (?P<value>(?:[0-9]{1,3}(?:,[0-9]{3})+|[0-9]+)(?:\.[0-9]+)?) (?:confirmed |public |observed )?(?P<count>views|likes|comments|reactions|shares)", re.I)
METRIC_ASSERTION = re.compile(r"\bcontent [12]\b.*\b(?:views|reach|likes|comments|reactions|shares|engagement rate)\b|\b(?:views|reach|engagement rate)\b.*\bcontent [12]\b", re.I)
ACTOR = r"(?:audience|viewers?|people|fans?|users?|watchers?|everyone|comments?|reactions?)"
EMOTION = r"(?:ador(?:e[ds]?|ing)|lov(?:e[ds]?|ing)|hat(?:e[ds]?|ing)|enjoy(?:s|ed)?|prefer(?:s|red)?|dislik(?:e[ds]?|ing)|lik(?:e[ds]?|ing)|satisfied|captivated|positive|negative|happy|angry|bored|delighted|enthusiastic|amused|disappointed)"
SENTIMENT = re.compile(r"\bsentiment\b|\b" + ACTOR + r"\b.{0,70}\b" + EMOTION + r"\b|\b" + EMOTION + r"\b.{0,70}\b" + ACTOR + r"\b", re.I)
UNCERTAINTY = re.compile(r"(?:the (?:available|public|observed) metrics (?:do not|cannot|can't) (?:establish|measure|determine|show) (?:audience )?sentiment|(?:audience )?sentiment (?:is|remains) (?:unknown|unavailable|not assessable)(?: from (?:the )?(?:available|public) metrics)?)", re.I)
QUOTATION = re.compile(r'the (?P<type>transcript|description|opening) (?:says|states|quotes|contains)[: ]+["\u201c](?P<quote>.+)["\u201d]', re.I)


def normalized(text):
    return " ".join(text.strip().split()).rstrip(".").casefold()


def sentiment_uncertainty(text):
    # Full-match prevents a disclaimer from laundering a following factual assertion.
    return UNCERTAINTY.fullmatch(normalized(text)) is not None


def source_quotation(text, evidence):
    match = QUOTATION.fullmatch(" ".join(text.strip().split()).rstrip("."))
    if not match:
        return None
    quote = match["quote"]
    return quote if any(e.source_type == match["type"].lower() and quote in (e.excerpt or "") for e in evidence) else None


def _owned_metadata(context, citations, slot):
    decision = context["summary"]["goal_comparison"]
    identity = decision.get(slot) or {}
    content = context["summary"].get(slot) or {}
    if (not identity.get("content_id") or not identity.get("metric_input_revision") or identity.get("project_id") != context["project_id"]
            or identity.get("content_id") != content.get("content_id")):
        return False
    return any(c.source_type == "metadata" and c.project_id == context["project_id"]
               and c.content_id == identity["content_id"] and c.slot == slot
               and c.platform == identity.get("platform")
               and c.evidence_revision == identity.get("metric_input_revision") for c in citations)


def supported_metric_claim(text, context, citations, *, source=None):
    """Accept only a complete bounded assertion matched to current canonical contracts."""
    text = normalized(text)
    count = COUNT.fullmatch(text)
    if count:
        slot = SLOTS[count["slot"]]
        if not _owned_metadata(context, citations, slot):
            return False
        if source is not None and (source.source_type != "metadata" or source.slot != slot):
            return False
        metrics = ((context["summary"].get(slot) or {}).get("scoring") or {}).get("metrics") or {}
        value = metrics.get("counts", {}).get(count["count"])
        if value is None:
            return False
        try:
            return Decimal(count["value"].replace(",", "")) == Decimal(str(value))
        except InvalidOperation:
            return False
    for pattern in DIRECTIONAL:
        match = pattern.fullmatch(text)
        if not match:
            continue
        slot = SLOTS[match["slot"]]
        if source is not None and source.source_type != "metadata":
            return False
        peer = "content_2" if slot == "content_1" else "content_1"
        if match.groupdict().get("other") and SLOTS[match["other"]] != peer:
            return False
        objective = "engagement" if "engagement rate" in match["metric"] else "reach"
        decision = context["summary"]["goal_comparison"]
        dimension = decision.get("objective_decisions", {}).get(objective) or {}
        if (dimension.get("eligibility", {}).get("status") != "eligible"
                or dimension.get("outcome") not in {"content_1", "content_2"}
                or any(not _owned_metadata(context, citations, s) for s in (slot, peer))):
            return False
        winner = dimension.get("winner_slot")
        if winner != dimension["outcome"] or dimension.get("winner_content_id") != decision.get(winner, {}).get("content_id"):
            return False
        values = dimension.get("values", {})
        if any(values.get(s) is None for s in (slot, peer)):
            return False
        lower = match["direction"].lower() in {"fewer", "lower", "less"}
        return (slot != winner) if lower else (slot == winner)
    return False
