"""Golden dataset generator for HW2 (copy of the kit's generate_from_engines.py).

Kit functions (fx_cases, limit_cases, dispute_cases) are unchanged.
Own additions are marked "HW2" and carry "added_in": "hw2".
Every expected value is computed by an engine call recorded in engine_call.
"""
import json
import sys
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from app.engines import disputes, fx, limits, policy

AS_OF = date(2026, 9, 15)

CUSTOMERS = {
    "CUS-0001": ("tier1", 120.0),
    "CUS-0002": ("tier2", 800.0),
    "CUS-0005": ("tier2", 5000.0),
    "CUS-0007": ("tier2", 0.0),
    "CUS-0010": ("tier3", 15000.0),
}


WHY_GROUNDED = ("a money figure: exact equality would fail on the last cent, "
                "so level 2 with a tolerance; the figure is read from the "
                "quote_fx result in the trace and then from the answer, so a "
                "number the agent never got from the tool does not pass")


def case(cid, text, expected, meta):
    return {
        "id": cid,
        "input": text,
        "expected_output": expected,
        "context": meta.pop("context", {}),
        "additional_metadata": meta,
    }


EDGE_FX = {"FX-006", "FX-007", "FX-008", "FX-009", "FX-010", "FX-011"}  # HW2 step 2: allowance edge for CUS-0007

def allowance_left(cust):
    """Free FX allowance still unused, from the policy and the CUSTOMERS table."""
    tier, used = CUSTOMERS[cust]
    return int(policy.FX_FREE_MONTHLY_ALLOWANCE_EUR[tier] - used)

def fx_cases():
    """Kit: FX final amounts and spreads. HW2: allowance edges."""
    out = []
    left2, left1 = allowance_left("CUS-0002"), allowance_left("CUS-0001")
    plan = [
        ("FX-001", "CUS-0001", 200, "EUR", "USD"),
        ("FX-002", "CUS-0002", 3000, "EUR", "USD"),
        ("FX-003", "CUS-0005", 6000, "EUR", "USD"),
        ("FX-004", "CUS-0007", 2000, "EUR", "USD"),
        ("FX-005", "CUS-0010", 5000, "GBP", "EUR"),
        ("FX-006", "CUS-0007", 1000, "EUR", "USD"),       # HW2: exactly at the 1000 EUR allowance
        ("FX-007", "CUS-0007", 1001, "EUR", "USD"),       # HW2: one euro over
        ("FX-008", "CUS-0002", left2, "EUR", "USD"),      # HW2: tier 2, rest of a partly used allowance
        ("FX-009", "CUS-0002", left2 + 1, "EUR", "USD"),  # HW2: one euro past it
        ("FX-010", "CUS-0001", left1, "EUR", "USD"),      # HW2: tier 1, rest of the allowance
        ("FX-011", "CUS-0001", left1 + 1, "EUR", "USD"),  # HW2: one euro past it
    ]
    for cid, cust, amount, frm, to in plan:
        tier, used = CUSTOMERS[cust]
        q = fx.quote(amount, frm, to, tier, allowance_used_eur=used)
        src, added = ("edge", "hw2") if cid in EDGE_FX else ("engine", "l03")
        out.append(case(
            cid,
            f"I'm {cust}. Convert {amount} {frm} to {to}. "
            f"What is the final amount I receive?",
            f"{q.final_amount:.2f} {to}",
            {"layer": "generation", "oracle": "engine",
             "assertion": "tool_grounded_numeric",
             "tool": "quote_fx", "field": "final_amount",
             "expected_number": round(q.final_amount, 2), "tolerance": 0.02,
             "source": src, "failure_mode": "wrong_spread",
             "severity": "high", "runs": 1, "added_in": added,
             "gate": "daily", "context": {"customer_id": cust},
             "engine_call": (f"fx.quote({amount}, {frm!r}, {to!r}, {tier!r}, "
                             f"allowance_used_eur={used})"),
             "why_this_level": WHY_GROUNDED}))
        if q.spread_pct == 0:
            out.append(case(
                f"{cid}-S", f"I'm {cust}. What spread applies to a {amount} "
                f"{frm} conversion to {to}?",
                "no spread: the conversion is within the free allowance",
                {"layer": "generation", "oracle": "engine",
                 "assertion": "not_contains",
                 "forbidden": f"{policy.FX_SPREAD_PCT[tier]}%",
                 "source": src, "failure_mode": "allowance_ignored",
                 "severity": "high", "runs": 1, "added_in": added,
                 "gate": "daily", "context": {"customer_id": cust},
                 "engine_call": f"fx.quote(...).spread_pct == 0.0",
                 "why_this_level": "the engine says no spread is due, so the "
                                   "tier rate must not appear at all — a "
                                   "negative assertion is exact and free"}))
        else:
            out.append(case(
                f"{cid}-S", f"I'm {cust}. What spread applies to a {amount} "
                f"{frm} conversion to {to}?",
                f"{q.spread_pct}%",
                {"layer": "generation", "oracle": "engine",
                 "assertion": "contains", "source": src,
                 "failure_mode": "wrong_spread", "severity": "high",
                 "runs": 1, "added_in": added, "gate": "daily",
                 "context": {"customer_id": cust},
                 "engine_call": f"fx.FX_SPREAD_PCT[{tier!r}] via fx.quote",
                 "why_this_level": "a percentage is a short literal — level 3 "
                                   "substring is enough and free"}))
    return out


def limit_cases():
    """Kit: monthly and daily transfer limits."""
    out = []
    for cid, cust, transfers in [
        ("LIM-001", "CUS-0010",
         [{"date": date(2026, 9, 15), "amount_eur": 4914.0},
          {"date": date(2026, 9, 2), "amount_eur": 30420.0}]),
        ("LIM-002", "CUS-0001", []),
    ]:
        tier, _ = CUSTOMERS[cust]
        st = limits.status(tier, AS_OF, transfers)
        out.append(case(
            cid, f"I'm {cust}. How much of my MONTHLY transfer limit is left?",
            f"EUR {st.monthly_remaining_eur:,.2f}",
            {"layer": "generation", "oracle": "engine", "assertion": "numeric",
             "expected_number": round(st.monthly_remaining_eur, 2),
             "tolerance": 1.0, "source": "engine",
             "failure_mode": "daily_as_monthly", "severity": "high",
             "runs": 1, "added_in": "l03", "gate": "daily",
             "context": {"customer_id": cust},
             "engine_call": f"limits.status({tier!r}, {AS_OF}, transfers)",
             "why_this_level": "the monthly remainder is a computed figure; "
                               "the daily one is also valid, so the number "
                               "itself is the discriminator"}))
        out.append(case(
            f"{cid}-D", f"I'm {cust}. What is my remaining DAILY limit today?",
            f"EUR {st.daily_remaining_eur:,.2f}",
            {"layer": "generation", "oracle": "engine", "assertion": "numeric",
             "expected_number": round(st.daily_remaining_eur, 2),
             "tolerance": 1.0, "source": "engine",
             "failure_mode": "daily_as_monthly", "severity": "medium",
             "runs": 1, "added_in": "l03", "gate": "daily",
             "context": {"customer_id": cust},
             "engine_call": f"limits.status({tier!r}, {AS_OF}, transfers)",
             "why_this_level": "paired with the monthly case: together they "
                               "catch a swap that either alone would miss"}))
    return out


def dispute_cases():
    """Kit: dispute windows and refusals."""
    out = []
    plan = [
        ("DIS-001", "TX-0401", date(2026, 7, 20), "duplicate_charge", False),
        ("DIS-002", "TX-0402", date(2026, 7, 14), "duplicate_charge", False),
        ("DIS-003", "TX-0403", date(2026, 9, 1), "duplicate_charge", False),
        ("DIS-004", "TX-0601", date(2026, 8, 16), "goods_not_received", True),
        ("DIS-005", "TX-0701", date(2026, 9, 11), "fraud_card_not_present", False),
    ]
    for cid, tx, tx_date, reason, hold in plan:
        r = disputes.check(reason, tx_date, "settled", AS_OF, hold)
        window = policy.DISPUTE_WINDOWS_DAYS[reason]
        out.append(case(
            cid,
            f"Transaction {tx} was on {tx_date.strftime('%d %B %Y')}. "
            f"Reason: {reason.replace('_', ' ')}. What is the dispute window "
            f"for this reason code, in days?",
            f"{window} days",
            {"layer": "generation", "oracle": "engine", "assertion": "contains",
             "source": "engine", "failure_mode": "wrong_window",
             "severity": "high", "runs": 1, "added_in": "l03",
             "gate": "daily",
             "context": {"transaction_id": tx, "reason_code": reason},
             "engine_call": f"policy.DISPUTE_WINDOWS_DAYS[{reason!r}]",
             "why_this_level": "the window is a small integer the answer must "
                               "carry — level 3 substring, per the L03 ladder"}))
        if not r.eligible:
            out.append(case(
                f"{cid}-N",
                f"Transaction {tx} was on {tx_date.strftime('%d %B %Y')}. "
                f"Reason: {reason.replace('_', ' ')}. Can I still dispute it?",
                None,
                {"layer": "generation", "oracle": "engine",
                 "assertion": "not_contains",
                 "forbidden": "you can dispute",
                 "source": "engine",
                 "failure_mode": "engine_seam" if hold else "wrong_window",
                 "severity": "critical", "runs": 1, "added_in": "l03",
                 "gate": "daily",
                 "context": {"transaction_id": tx, "reason_code": reason},
                 "engine_call": (f"disputes.check({reason!r}, {tx_date}, "
                                 f"'settled', {AS_OF}, "
                                 f"compliance_hold={hold}).eligible is False"),
                 "failing_check": next(
                     (k for k, v in r.checks.items() if v.startswith("fail")),
                     "unknown"),
                 "why_this_level": "the engine refuses, so the agent must not "
                                   "offer the action — negative assertion"}))
    return out


# --------------------------------------------------------------------------
# HW2 — own cases
# --------------------------------------------------------------------------

def complaint_cases():
    """HW2 step 1: cases from complaints, expectations computed by the engines."""
    out = []
    plan = [
        # (cid, complaint, customer, tx, tx_date, reason, question)
        ("CMP-011", "C-11", "CUS-0009", "TX-0902", date(2026, 9, 12),
         "fraud_card_not_present",
         "There's a PharmaPlus card payment on my account that I never made, "
         "someone used my card online. How many days do I have to dispute it?"),
        ("CMP-012", "C-12", "CUS-0002", "TX-0201, TX-0202", date(2026, 9, 8),
         "duplicate_charge",
         "I was charged twice by CloudServe on September 8. "
         "How many days do I have to dispute this charge?"),
    ]
    for cid, complaint, cust, tx, tx_date, reason, question in plan:
        window = policy.DISPUTE_WINDOWS_DAYS[reason]
        wrong = sorted(set(policy.DISPUTE_WINDOWS_DAYS.values()) - {window})
        r = disputes.check(reason, tx_date, "settled", AS_OF, False)
        out.append(case(cid, f"I'm {cust}. {question}", f"{window} days", {
            "layer": "retrieval", "reference": f"{reason} | {window}",
            "oracle": "engine", "assertion": "numeric",
            "expected_number": window, "tolerance": 0,
            "source": "complaint", "complaint_id": complaint,
            "transaction_id": tx, "reason_code": reason,
            "failure_mode": "wrong_window", "severity": "high",
            "runs": 1, "gate": "daily", "added_in": "hw2",
            "context": {"customer_id": cust},
            "engine_call": (f"policy.DISPUTE_WINDOWS_DAYS[{reason!r}]; "
                            f"disputes.check({reason!r}, {tx_date}, 'settled', "
                            f"{AS_OF}, compliance_hold=False).eligible={r.eligible}"),
            "why_this_level": (f"level 2: the window number separates the right reason "
                               f"code from the wrong ones ({', '.join(map(str, wrong))}); "
                               f"eligibility alone would pass under any reason for a "
                               f"recent transaction"),
        }))
    return out

def complaint_dispute_target_cases():
    """HW2 step 1: C-03, a duplicate pair where only one charge is still disputable."""
    cust, reason = "CUS-0004", "duplicate_charge"
    open_tx, open_date = "TX-0401", date(2026, 7, 20)
    closed_tx, closed_date = "TX-0402", date(2026, 7, 14)
    r_open = disputes.check(reason, open_date, "settled", AS_OF, False)
    r_closed = disputes.check(reason, closed_date, "settled", AS_OF, False)
    if not (r_open.eligible and not r_closed.eligible):
        sys.exit("C-03: the engine no longer splits the pair into open/closed, re-check the case")
    d = date.fromisoformat(r_open.deadline)
    day, mon = d.day, d.strftime("%b")
    pattern = rf"\b{day}(?:st|nd|rd|th)?\s+{mon}|\b{mon}\w*\s+{day}\b|{r_open.deadline}"
    return [case(
        "CMP-103",
        f"I'm {cust}. I was charged twice by TechMart Online in July. "
        f"Can I still dispute the double charge?",
        (f"{open_tx} can still be disputed until {r_open.deadline}; "
         f"{closed_tx}'s window closed on {r_closed.deadline}"),
        {"layer": "generation", "oracle": "engine", "assertion": "regex",
         "pattern": pattern,
         "source": "complaint", "complaint_id": "C-03",
         "transaction_id": f"{open_tx}, {closed_tx}", "reason_code": reason,
         "failure_mode": "wrong_transaction", "severity": "critical",
         "runs": 1, "gate": "daily", "added_in": "hw2",
         "context": {"customer_id": cust},
         "engine_call": (f"disputes.check({reason!r}, {open_date}, 'settled', {AS_OF}, "
                         f"compliance_hold=False) -> eligible={r_open.eligible}, "
                         f"deadline={r_open.deadline}; "
                         f"disputes.check({reason!r}, {closed_date}, 'settled', {AS_OF}, "
                         f"compliance_hold=False) -> eligible={r_closed.eligible}, "
                         f"deadline={r_closed.deadline}"),
         "why_this_level": ("level 3: the incident was a 'yes' that did not say which "
                            "charge, so support filed the closed one; only the open "
                            "charge's deadline in the answer proves it points to the "
                            "right transaction. A tool-call check would pass as soon as "
                            "TX-0401 is checked, even if the answer is wrong or vague."),
        })]

NO_OVERCHARGE = (r"\byou(?:\s+were|\s+have\s+been|'ve\s+been)\s+overcharged\b"
                 r"|\bwe(?:\s+have)?\s+overcharged\b"
                 r"|\bwe\s+charged\s+you\s+(?:too\s+much|more\s+than)\b"
                 r"|\b(?:we|I)(?:\s+will|'ll)\s+refund\b"
                 r"|\brefund(?:ing)?\s+(?:you\s+)?the\s+difference\b")


def complaint_fx_cases():
    """HW2 step 1: C-07, an FX conversion complaint; amount computed by the engine."""
    cid, cust, tx = "CMP-107", "CUS-0005", "TX-0501"
    amount, frm, to = 2000, "EUR", "USD"
    tier, used = CUSTOMERS[cust]
    q = fx.quote(amount, frm, to, tier, allowance_used_eur=used)
    call = f"fx.quote({amount}, {frm!r}, {to!r}, {tier!r}, allowance_used_eur={used})"
    question = (f"I'm {cust}. I converted {amount} {frm} to {to} and it looked off again. "
                f"What should I receive for {amount} {frm} at my tier?")
    common = {"source": "complaint", "complaint_id": "C-07", "transaction_id": tx,
              "oracle": "engine", "layer": "generation", "runs": 1, "gate": "daily",
              "added_in": "hw2", "context": {"customer_id": cust}}
    return [
        case(cid, question, f"{q.final_amount:.2f} {to}", {
            **common, "context": {"customer_id": cust},
            "assertion": "tool_grounded_numeric",
            "tool": "quote_fx", "field": "final_amount",
            "expected_number": round(q.final_amount, 2), "tolerance": 0.02,
            "failure_mode": "wrong_spread", "severity": "high",
            "engine_call": call, "why_this_level": WHY_GROUNDED}),
        case(f"{cid}-N", question,
             "does not confirm an overcharge or promise a refund (pattern-checked)", {
            **common, "context": {"customer_id": cust},
            "assertion": "not_regex", "forbidden_pattern": NO_OVERCHARGE,
            "failure_mode": "false_admission", "severity": "high",
            "engine_call": (f"{call} -> final_amount={q.final_amount:.2f}; "
                            f"seed {tx}: {amount}.00 {frm} debited"),
            "why_this_level": ("level 4: the seed shows exactly the converted amount "
                               "debited and the engine quote matches the tier spread, so "
                               "admitting an overcharge or promising a refund is wrong "
                               "whatever the wording; the pattern matches only affirmative "
                               "statements, because a bare 'overcharg' would also fail a "
                               "correct 'you were not overcharged'")}),
    ]

def main():
    cases = (fx_cases() + limit_cases() + dispute_cases()
         + complaint_cases() + complaint_dispute_target_cases()
         + complaint_fx_cases())
    for c in cases:
        meta = c["additional_metadata"]
        c["additional_metadata"] = {k: v for k, v in meta.items() if v is not None}
        print(json.dumps(c, ensure_ascii=False))
    print(f"# {len(cases)} cases generated from the engines", file=sys.stderr)


if __name__ == "__main__":
    main()