# llm/langchain_scorer.py

import os
import json
import sys
from pathlib import Path

# ── Path fix ──────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / "config" / ".env")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
MODEL_NAME   = "llama-3.3-70b-versatile"
TEMPERATURE  = 0.1


# ══════════════════════════════════════════════════════
# PROMPT TEMPLATE
# ══════════════════════════════════════════════════════
SCORING_PROMPT = """
You are a strict call centre quality auditor. Analyze this transcript and return ONLY a valid JSON object. No explanation. No markdown. Just JSON.

TRANSCRIPT:
{transcript}

{context}

You MUST return ALL fields below. Never leave a field as null or missing.
If you cannot determine a value, use 0 for numbers and "unknown" for strings.

Return this exact JSON structure:

{{
  "grade": "A|B|C|D|F",
  "overall_score": <0-100>,
  "call_outcome": "Resolved|Unresolved|Escalated|Callback Required",
  "was_resolved": true|false,
  "sentiment": "positive|negative|neutral|mixed",
  "summary": "<2 sentence summary>",
  "issue_detected": "<main issue>",

  "satisfaction": {{
    "sentiment": "positive|negative|neutral|mixed",
    "sentiment_score": <0.0-1.0>,
    "emotional_stability": "Excellent|Good|Fair|Poor",
    "customer_frustration": "None|Low|Medium|High|Very High",
    "frustration_reason": "<reason or None>",
    "rating": <0.0-5.0>
  }},

  "agent_quality": {{
    "language_clarity": <0-20>,
    "professionalism": <0-20>,
    "time_efficiency": <0-20>,
    "response_efficiency": <0-20>,
    "empathy_score": <0.0-10.0>,
    "bias_detected": false,
    "calmed_customer": true|false,
    "empathy_phrases_used": ["<phrase1>", "<phrase2>"]
  }},

  "dimension_scores": {{
    "empathy": <0-10>,
    "professionalism": <0-10>,
    "compliance": <0-10>,
    "resolution_effectiveness": <0-10>,
    "communication_clarity": <0-10>
  }},

  "model_metrics": {{
    "precision": <0.0-1.0>,
    "recall": <0.0-1.0>,
    "f1_score": <0.0-1.0>,
    "confidence": <0.0-1.0>,
    "notes": "<brief note>"
  }},

  "violations": [
    {{
      "type": "<violation type>",
      "severity": "critical|high|medium|low",
      "quote": "<exact quote from transcript>",
      "explanation": "<why this is a violation>"
    }}
  ],

  "improvements": [
    {{
      "area": "<area name>",
      "suggestion": "<specific suggestion>",
      "example": "<example phrase agent could use>"
    }}
  ],

  "highlights": [
    "<something agent did well>"
  ]
}}

RULES:
- overall_score must reflect grade: A=90-100, B=75-89, C=60-74, D=45-59, F=0-44
- agent_quality scores must add up logically with overall_score
- violations array must be empty [] if no violations found
- highlights array must have at least 1 item always
- improvements array must have at least 2 suggestions always
- Return ONLY the JSON object. Nothing else.
"""


# ══════════════════════════════════════════════════════
# HELPER — SPLIT ENRICHED TRANSCRIPT
# ══════════════════════════════════════════════════════
def _split_enriched(enriched_transcript: str) -> tuple:
    """
    Splits enriched transcript into transcript + context.
    Returns (transcript, context)
    """
    if "[SIMILAR PAST CALLS" in enriched_transcript:
        parts      = enriched_transcript.split("[SIMILAR PAST CALLS", 1)
        transcript = parts[0].strip()
        context    = "[SIMILAR PAST CALLS" + parts[1]

    elif "[POLICY RULES" in enriched_transcript:
        parts      = enriched_transcript.split("[POLICY RULES", 1)
        transcript = parts[0].strip()
        context    = "[POLICY RULES" + parts[1]

    else:
        transcript = enriched_transcript.strip()
        context    = "No additional context available."

    return transcript, context


# ══════════════════════════════════════════════════════
# HELPER — PARSE JSON RESPONSE
# ══════════════════════════════════════════════════════
def _parse_response(response: str) -> dict:
    """
    Safely parses JSON from LLM response.
    Handles markdown code blocks if present.
    """
    clean = response.strip()

    # Remove markdown code blocks if present
    if "```" in clean:
        parts = clean.split("```")
        for part in parts:
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            if part.startswith("{"):
                clean = part
                break

    # Find JSON boundaries
    start = clean.find("{")
    end   = clean.rfind("}") + 1
    if start != -1 and end > start:
        clean = clean[start:end]

    return json.loads(clean)


# ══════════════════════════════════════════════════════
# MAIN SCORER
# ══════════════════════════════════════════════════════
def score_with_langchain(enriched_transcript: str) -> dict:
    """
    Score a transcript using LangChain + Groq.

    enriched_transcript : output from RAGPipeline.enrich()
    Returns             : scored dict same format as score_conversation()
    """
    if not GROQ_API_KEY:
        print("  ❌ GROQ_API_KEY not set in config/.env")
        return None

    try:
        from langchain_groq import ChatGroq
        from langchain_core.prompts import PromptTemplate
        from langchain_core.output_parsers import StrOutputParser

        # ── Split transcript and context ───────────────
        transcript, context = _split_enriched(enriched_transcript)

        # ── Build LangChain components ──────────────────
        llm = ChatGroq(
            api_key     = GROQ_API_KEY,
            model_name  = MODEL_NAME,
            temperature = TEMPERATURE,
        )

        prompt = PromptTemplate(
            input_variables = ["transcript", "context"],
            template        = SCORING_PROMPT,
        )

        parser = StrOutputParser()

        # ── Build chain ────────────────────────────────
        # LangChain pipe operator: prompt → llm → parser
        chain = prompt | llm | parser

        print(f"  🔗 LangChain: PromptTemplate | ChatGroq | StrOutputParser")
        print(f"  📤 Sending to {MODEL_NAME}...")

        # ── Run chain ──────────────────────────────────
        response = chain.invoke({
            "transcript": transcript,
            "context":    context,
        })

        # ── Parse JSON ─────────────────────────────────
        result = _parse_response(response)

        grade = result.get("grade", "?")
        score = result.get("overall_score", 0)
        print(f"  ✅ LangChain scored: Grade {grade} | Score {score}/100")

        return result

    except json.JSONDecodeError as e:
        print(f"  ❌ JSON parse error: {e}")
        return None

    except Exception as e:
        print(f"  ❌ LangChain error: {e}")
        return None


# ══════════════════════════════════════════════════════
# RUN DIRECTLY — test the scorer
# ══════════════════════════════════════════════════════
if __name__ == "__main__":
    print("\n" + "="*50)
    print("  Testing LangChain Scorer")
    print("="*50 + "\n")

    # Simulate enriched transcript from RAGPipeline
    test_enriched = """
Agent: Thank you for calling support, how can I help?
Customer: I want to speak to a manager right now.
Agent: Managers are too busy, I cannot transfer you.
Customer: This is unacceptable, I have been waiting 3 days.
Agent: There is nothing I can do about that.
Customer: You are completely useless.
Agent: I understand your frustration but there is nothing I can do.

[SIMILAR PAST CALLS — use as grade reference:]

  - Grade F | Score 18/100 | Similarity 0.89 | Resolved: False
    Issue  : Agent refused manager escalation request
    Outcome: Unresolved

  - Grade D | Score 35/100 | Similarity 0.76 | Resolved: False
    Issue  : Agent showed no empathy to angry customer
    Outcome: Unresolved

→ Score the current call consistently with these reference cases.

[POLICY RULES — apply strictly when scoring:]

  [HIGH] Escalation Policy
  Customers have the right to speak to a manager at any time.
  Agents must never refuse or delay escalation requests.
  Saying 'managers are too busy' is a direct policy violation.
  (Relevance: 0.91)

  [HIGH] Rude Language
  Agents must remain professional at all times.
  Saying 'there is nothing I can do' dismissively is a violation.
  (Relevance: 0.82)
"""

    print("Running LangChain chain...\n")
    result = score_with_langchain(test_enriched)

    if result:
        print("\n" + "="*50)
        print("  SCORING RESULT")
        print("="*50)
        print(f"  Grade        : {result.get('grade')}")
        print(f"  Score        : {result.get('overall_score')}/100")
        print(f"  Sentiment    : {result.get('sentiment')}")
        print(f"  Outcome      : {result.get('call_outcome')}")
        print(f"  Resolved     : {result.get('was_resolved')}")
        print(f"  Issue        : {result.get('issue_detected')}")

        print(f"\n  Dimension Scores:")
        for k, v in result.get("dimension_scores", {}).items():
            bar = "█" * (v // 10) + "░" * (10 - v // 10)
            print(f"    {k:<28} {bar} {v}/100")

        print(f"\n  Violations ({len(result.get('violations', []))}):")
        for v in result.get("violations", []):
            print(f"    ❌ [{v.get('severity','').upper()}] "
                  f"{v.get('type','')} — "
                  f"{v.get('explanation','')[:70]}")

        print(f"\n  Improvements ({len(result.get('improvements', []))}):")
        for i in result.get("improvements", []):
            print(f"    💡 {i.get('area','')} — "
                  f"{i.get('suggestion','')[:70]}")

        print(f"\n  Summary:")
        print(f"    {result.get('summary','')}")
        print("="*50)

    else:
        print("❌ Scoring failed — check GROQ_API_KEY in config/.env")