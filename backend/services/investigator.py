import json
from typing import Dict, List

import ollama


LLM_MODEL = "llama3:latest"


def build_context(
    matches: List[Dict],
    candidates: List[Dict] | None = None
) -> str:
    source_blocks = []

    for index, match in enumerate(matches, start=1):
        source_blocks.append(
            "\n".join(
                [
                    f"[SOURCE {index}]",
                    f"DOCUMENT: {match.get('document', 'Unknown')}",
                    f"PAGE: {match.get('page') or 'N/A'}",
                    f"SECTION: {match.get('section') or 'N/A'}",
                    f"SIMILARITY: {match.get('score', 0)}",
                    "CONTENT:",
                    match.get("text", ""),
                ]
            )
        )

    candidate_block = ""

    if candidates:
        candidate_block = (
            "\n\nPOSSIBLE CONFLICT SIGNALS (NOT YET PROVEN):\n"
            + json.dumps(candidates, ensure_ascii=False)
        )

    return "\n\n".join(source_blocks) + candidate_block


def safe_result(raw_result: Dict) -> Dict:
    verdict = str(
        raw_result.get("verdict", "INSUFFICIENT")
    ).upper().strip()

    if verdict not in {"SUPPORTED", "CONFLICT", "INSUFFICIENT"}:
        verdict = "INSUFFICIENT"

    try:
        confidence = int(float(raw_result.get("confidence", 0)))
    except (TypeError, ValueError):
        confidence = 0

    confidence = max(0, min(100, confidence))

    # Always calculate the label ourselves.
    if confidence >= 75:
        confidence_label = "High"
    elif confidence >= 50:
        confidence_label = "Medium"
    else:
        confidence_label = "Low"

    findings = raw_result.get("key_findings")
    if not isinstance(findings, list):
        findings = []

    conflicts = raw_result.get("conflicts")
    if not isinstance(conflicts, list):
        conflicts = []

    cleaned_conflicts = []

    for item in conflicts:
        if not isinstance(item, dict):
            continue

        docs = item.get("documents")

        if not isinstance(docs, list) or len(docs) < 2:
            continue

        documents = [
            str(doc).strip()
            for doc in docs
            if str(doc).strip()
        ][:5]

        reason = str(item.get("reason", "")).strip()

        if documents and reason:
            entry = {
                "documents": documents,
                "reason": reason,
            }

            if item.get("values") is not None:
                entry["values"] = item.get("values")

            cleaned_conflicts.append(entry)

    # A verified conflict overrides the model verdict.
    if cleaned_conflicts:
        verdict = "CONFLICT"
        confidence = min(confidence, 70)

        if confidence >= 75:
            confidence_label = "High"
        elif confidence >= 50:
            confidence_label = "Medium"
        else:
            confidence_label = "Low"

    # Never show CONFLICT without actual conflict evidence.
    elif verdict == "CONFLICT":
        verdict = "INSUFFICIENT"
        confidence = min(confidence, 40)
        confidence_label = "Low"

    return {
        "answer": str(
            raw_result.get(
                "answer",
                "No reliable conclusion was produced."
            )
        ).strip(),
        "verdict": verdict,
        "confidence": confidence,
        "confidence_label": confidence_label,
        "key_findings": [
            str(x).strip()
            for x in findings
            if str(x).strip()
        ][:5],
        "conflicts": cleaned_conflicts[:8],
    }


def fallback_result(matches: List[Dict]) -> Dict:
    if not matches:
        return {
            "answer": (
                "The selected documents do not contain enough relevant "
                "evidence to answer this question reliably."
            ),
            "verdict": "INSUFFICIENT",
            "confidence": 10,
            "confidence_label": "Low",
            "key_findings": [],
            "conflicts": [],
        }

    scores = [
        float(match.get("score", 0))
        for match in matches
        if match.get("score") is not None
    ]

    average_score = (
        sum(scores) / len(scores)
        if scores
        else 0
    )

    confidence = max(
        20,
        min(60, int(average_score * 100))
    )

    return {
        "answer": (
            "Relevant evidence was retrieved, but the investigation "
            "model could not produce a reliable structured conclusion. "
            "Review the cited evidence below."
        ),
        "verdict": "INSUFFICIENT",
        "confidence": confidence,
        "confidence_label": (
            "Medium" if confidence >= 50 else "Low"
        ),
        "key_findings": [
            (
                f"Relevant evidence was retrieved from "
                f"{len({m.get('document') for m in matches})} document(s)."
            )
        ],
        "conflicts": [],
    }


def investigate_documents(
    question: str,
    matches: List[Dict],
    candidates: List[Dict] | None = None,
) -> Dict:

    if not matches:
        return fallback_result(matches)

    # Keep the investigation context compact for faster local inference.
    matches = matches[:5]

    context = build_context(matches, candidates)

    prompt = f"""
You are DocuVerity AI, a professional evidence-investigation engine.

Answer the user's question using ONLY the supplied evidence.

Never use outside knowledge.
Never invent facts.
Never fill missing information with assumptions.

IMPORTANT RULES:

1. For descriptive questions such as:
   - "What is in this document?"
   - "What does this diary contain?"
   - "Summarize this document."

   return SUPPORTED when the retrieved evidence directly supports
   the description.

2. For eligibility, compliance, qualification, approval, or
   verification questions:
   every required criterion must have supporting evidence.

3. Missing important evidence = INSUFFICIENT.

4. If two documents make materially different claims about the
   same fact = CONFLICT.

5. A requirement is NOT proof that a person satisfies the requirement.

6. An application or intention is NOT proof of eligibility.

7. Do not call unrelated numbers a conflict.

8. Possible conflict signals are only hints.
   Verify them using the actual evidence.

9. Clearly communicate uncertainty whenever evidence is incomplete
   or contradictory.

VERDICTS:

SUPPORTED
Evidence directly supports the conclusion.

CONFLICT
The supplied documents contain materially incompatible claims
about the same fact.

INSUFFICIENT
Important evidence is missing or the supplied evidence does not
justify a reliable conclusion.

QUESTION:
{question}

EVIDENCE:
{context}

Return ONLY valid JSON.

Use exactly these keys:

{{
  "answer": "professional evidence-based conclusion",
  "verdict": "SUPPORTED | CONFLICT | INSUFFICIENT",
  "confidence": 0,
  "confidence_label": "High | Medium | Low",
  "key_findings": [
    "concise evidence-grounded finding"
  ],
  "conflicts": [
    {{
      "documents": [
        "Document A",
        "Document B"
      ],
      "reason": "specific disagreement between the documents"
    }}
  ]
}}

Confidence must reflect the quality, relevance and completeness
of the supplied evidence only.
"""

    try:
        response = ollama.chat(
            model=LLM_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            format="json",
            options={
                "temperature": 0,
                "num_predict": 220,
            },
            keep_alive="10m",
        )

        parsed = json.loads(response.message.content)

        result = safe_result(parsed)

        # Llama may sometimes return confidence = 0.
        # Calculate a reasonable evidence-based value instead.
        if result["confidence"] == 0:
            scores = [
                float(match.get("score", 0))
                for match in matches
                if match.get("score") is not None
            ]

            average_score = (
                sum(scores) / len(scores)
                if scores
                else 0
            )

            if result["verdict"] == "SUPPORTED":
                result["confidence"] = max(
                    60,
                    min(95, int(average_score * 100 + 25))
                )

            elif result["verdict"] == "CONFLICT":
                result["confidence"] = max(
                    45,
                    min(70, int(average_score * 100))
                )

            else:
                result["confidence"] = max(
                    20,
                    min(45, int(average_score * 80))
                )

            if result["confidence"] >= 75:
                result["confidence_label"] = "High"
            elif result["confidence"] >= 50:
                result["confidence_label"] = "Medium"
            else:
                result["confidence_label"] = "Low"

        return result

    except Exception:
        return fallback_result(matches)