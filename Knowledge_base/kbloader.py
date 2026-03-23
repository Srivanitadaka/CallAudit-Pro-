# knowledge_base/kb_loader.py
"""
Knowledge Base Loader
─────────────────────────────────────────────
14 entries across 3 categories:
  - Policy Rules     (7) — compliance violations
  - Quality Rubrics  (3) — scoring instructions
  - Best Practices   (4) — agent guidance

Run directly to generate kb_store.json:
  python knowledge_base/kb_loader.py
"""

import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
KB_FILE  = BASE_DIR / "knowledge_base" / "kb_store.json"


# ══════════════════════════════════════════════════════
# POLICY RULES
# ══════════════════════════════════════════════════════
POLICY_RULES = [
    {
        "id":       "POL-001",
        "title":    "GDPR — Card Data",
        "severity": "critical",
        "tags":     ["gdpr", "card", "cvv", "pin", "data"],
        "content": (
            "Agents must NEVER request a customer's full card number, CVV, or PIN. "
            "This is a critical GDPR and PCI-DSS violation. "
            "Trigger words: 'card number', 'cvv', 'security code', 'your pin'. "
            "If a customer volunteers card data, agent must immediately stop them and "
            "redirect to a secure payment channel."
        )
    },
    {
        "id":       "POL-002",
        "title":    "Escalation Policy",
        "severity": "high",
        "tags":     ["escalation", "manager", "supervisor", "transfer"],
        "content": (
            "Customers have the right to speak to a manager at any time. "
            "Agents must never refuse or delay escalation requests. "
            "Saying 'managers are too busy', 'managers don't deal with this', "
            "or 'I cannot transfer you' is a direct policy violation. "
            "Correct response: 'Let me connect you with a manager right away.'"
        )
    },
    {
        "id":       "POL-003",
        "title":    "False Promises",
        "severity": "high",
        "tags":     ["promise", "guarantee", "refund", "compensation"],
        "content": (
            "Agents must never make promises they cannot keep. "
            "Forbidden phrases: 'I guarantee', 'I promise you', '100% sure', "
            "'definitely will be resolved by'. "
            "Correct approach: Use conditional language — "
            "'I will do my best to', 'I will escalate this and follow up'."
        )
    },
    {
        "id":       "POL-004",
        "title":    "Rude Language",
        "severity": "high",
        "tags":     ["rude", "unprofessional", "dismissive", "language"],
        "content": (
            "Agents must remain professional and respectful at all times. "
            "Forbidden phrases: 'not my problem', 'I don't care', "
            "'there is nothing I can do', 'calm down', 'that's your issue'. "
            "Even when a customer is aggressive, the agent must stay calm "
            "and use empathetic, solution-focused language."
        )
    },
    {
        "id":       "POL-005",
        "title":    "Consumer Rights — Refunds",
        "severity": "high",
        "tags":     ["refund", "consumer", "rights", "policy"],
        "content": (
            "Customers are entitled to a refund within 30 days of purchase "
            "for faulty or misrepresented products under consumer rights law. "
            "Agents must not deny valid refund requests. "
            "If unsure, escalate to supervisor — do not refuse outright."
        )
    },
    {
        "id":       "POL-006",
        "title":    "Emergency Claims",
        "severity": "critical",
        "tags":     ["emergency", "urgent", "safety", "medical"],
        "content": (
            "If a customer mentions a safety emergency, medical situation, "
            "or immediate danger, the agent must treat this as highest priority. "
            "Do not put such customers on hold. "
            "Follow emergency escalation protocol immediately. "
            "Document the interaction fully."
        )
    },
    {
        "id":       "POL-007",
        "title":    "Repeat Contact Escalation",
        "severity": "high",
        "tags":     ["repeat", "contact", "escalation", "unresolved"],
        "content": (
            "If a customer mentions they have called more than twice about "
            "the same issue, the agent must escalate to a senior agent or supervisor. "
            "Repeat contacts indicate a systemic failure. "
            "Do not attempt to resolve repeat issues at first-line level."
        )
    },
]


# ══════════════════════════════════════════════════════
# QUALITY RUBRICS
# ══════════════════════════════════════════════════════
QUALITY_RUBRICS = [
    {
        "id":       "RUB-001",
        "title":    "Empathy Scoring",
        "severity": "info",
        "tags":     ["empathy", "scoring", "rubric"],
        "content": (
            "Score empathy 0-100 based on: "
            "Did the agent acknowledge the customer's emotion before solving the problem? "
            "Did they use phrases like 'I understand how frustrating this must be'? "
            "Did they apologize appropriately? "
            "Score 0 if agent jumped straight to solution without acknowledgment. "
            "Score 100 if agent fully acknowledged emotion AND provided solution."
        )
    },
    {
        "id":       "RUB-002",
        "title":    "Resolution Scoring",
        "severity": "info",
        "tags":     ["resolution", "scoring", "rubric"],
        "content": (
            "Score resolution_effectiveness 0-100 based on: "
            "Was the customer's issue fully resolved? "
            "Was a clear next step given if not resolved immediately? "
            "Score 0 if issue completely unresolved with no follow-up plan. "
            "Score 50 if escalated properly but not yet resolved. "
            "Score 100 if issue fully resolved and customer confirmed satisfaction."
        )
    },
    {
        "id":       "RUB-003",
        "title":    "Compliance Scoring",
        "severity": "info",
        "tags":     ["compliance", "scoring", "rubric", "policy"],
        "content": (
            "Score compliance 0-100 based on: "
            "Did the agent follow all policy rules? "
            "Score 0 if any CRITICAL violation occurred (GDPR, emergency). "
            "Score 0 if escalation was refused. "
            "Score 0 if false promises were made. "
            "Score 50 if minor policy deviation occurred. "
            "Score 100 if all policies followed perfectly."
        )
    },
]


# ══════════════════════════════════════════════════════
# BEST PRACTICES
# ══════════════════════════════════════════════════════
BEST_PRACTICES = [
    {
        "id":       "BP-001",
        "title":    "Handling Angry Customers",
        "severity": "info",
        "tags":     ["angry", "frustrated", "difficult", "customer"],
        "content": (
            "Step 1: Let customer finish speaking without interrupting. "
            "Step 2: Acknowledge emotion first — not the problem. "
            "Step 3: Take ownership: 'This should not have happened.' "
            "Step 4: Give specific action: 'Here is what I will do right now.' "
            "Step 5: Confirm resolution and ask if anything else is needed. "
            "Never say 'calm down' — it escalates anger."
        )
    },
    {
        "id":       "BP-002",
        "title":    "Proactive Compensation",
        "severity": "info",
        "tags":     ["compensation", "goodwill", "retention", "discount"],
        "content": (
            "For customers who have experienced significant inconvenience, "
            "proactively offer goodwill compensation without waiting to be asked. "
            "This reduces churn and increases satisfaction scores. "
            "Examples: discount on next order, waived fee, priority support. "
            "Document all compensation offered."
        )
    },
    {
        "id":       "BP-003",
        "title":    "Closing a Call Correctly",
        "severity": "info",
        "tags":     ["closing", "sign-off", "end", "call"],
        "content": (
            "Always close with: "
            "1. Summary of what was done. "
            "2. Confirmation of next step with timeframe. "
            "3. Ask: 'Is there anything else I can help with?' "
            "4. Warm sign-off: 'Thank you for your patience. Have a great day.' "
            "Never end a call abruptly or without confirming resolution."
        )
    },
    {
        "id":       "BP-004",
        "title":    "Opening a Call Correctly",
        "severity": "info",
        "tags":     ["opening", "greeting", "introduction", "start"],
        "content": (
            "Always open with: "
            "1. Warm greeting: 'Thank you for calling [Company], my name is [Name].' "
            "2. Ask how you can help. "
            "3. Verify customer identity if required by policy. "
            "4. Repeat back the issue to confirm understanding before starting. "
            "A good opening sets the tone for the entire interaction."
        )
    },
]


# ══════════════════════════════════════════════════════
# VIOLATION KEYWORDS
# ══════════════════════════════════════════════════════
VIOLATION_KEYWORDS = {
    "gdpr_risk": [
        "card number", "cvv", "security code", "your pin",
        "full card", "card details"
    ],
    "rude_language": [
        "not my problem", "i don't care", "calm down",
        "that's your issue", "nothing i can do"
    ],
    "unprofessional_language": [
        "whatever", "i guess", "not sure why you", "obviously"
    ],
    "false_promise": [
        "i guarantee", "i promise", "100% sure",
        "definitely will", "absolutely will"
    ],
    "escalation_ignored": [
        "managers don't", "cannot transfer", "managers are busy",
        "no supervisor", "no manager available"
    ],
    "negative_language": [
        "can't do that", "not possible", "we don't do",
        "that's not our policy"
    ],
}


# ══════════════════════════════════════════════════════
# COMBINED KB
# ══════════════════════════════════════════════════════
ALL_KB_ENTRIES = POLICY_RULES + QUALITY_RUBRICS + BEST_PRACTICES


# ══════════════════════════════════════════════════════
# GET KB CONTEXT — keyword search
# ══════════════════════════════════════════════════════
def get_kb_context(topic: str = "") -> str:
    """
    Returns relevant KB entries as formatted scoring instructions.
    Matches by tags and content keywords.
    """
    topic_lower = topic.lower()
    matched     = []

    for entry in ALL_KB_ENTRIES:
        tags    = entry.get("tags", [])
        content = entry.get("content", "").lower()
        title   = entry.get("title", "").lower()

        # Match by tag
        tag_match = any(tag in topic_lower for tag in tags)

        # Match by content keyword
        content_match = any(
            word in topic_lower
            for word in content.split()
            if len(word) > 4
        )

        # Match by title word
        title_match = any(
            word in topic_lower
            for word in title.split()
            if len(word) > 3
        )

        if tag_match or title_match:
            matched.append(entry)
        elif content_match and entry.get("severity") in ["critical", "high"]:
            matched.append(entry)

    if not matched:
        # Default — return all policy rules if nothing matched
        matched = POLICY_RULES[:3]

    # Format as scoring instructions
    lines = ["\n\n[SCORING INSTRUCTIONS — apply strictly:]\n"]
    for entry in matched[:5]:
        lines.append(
            f"[{entry['id']} | {entry['title']} | "
            f"{entry['severity'].upper()}]\n"
            f"{entry['content']}\n"
        )

    return "\n".join(lines)


# ══════════════════════════════════════════════════════
# SAVE TO FILE
# ══════════════════════════════════════════════════════
def save_kb_to_file():
    """Save all KB entries to kb_store.json"""
    KB_FILE.parent.mkdir(parents=True, exist_ok=True)
    KB_FILE.write_text(
        json.dumps(ALL_KB_ENTRIES, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"✅ KB saved: {len(ALL_KB_ENTRIES)} entries → {KB_FILE.name}")
    print(f"   Policy Rules   : {len(POLICY_RULES)}")
    print(f"   Quality Rubrics: {len(QUALITY_RUBRICS)}")
    print(f"   Best Practices : {len(BEST_PRACTICES)}")


# ══════════════════════════════════════════════════════
# RUN DIRECTLY
# ══════════════════════════════════════════════════════
if __name__ == "__main__":
    save_kb_to_file()

    # Quick test
    print("\nTesting get_kb_context...")
    ctx = get_kb_context("agent refused to transfer to manager")
    print(ctx[:300])