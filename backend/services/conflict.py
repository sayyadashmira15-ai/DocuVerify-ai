import re
from collections import defaultdict
from typing import Dict, List, Tuple


NUMBER_PATTERN = re.compile(
    r"(?:₹\s?[\d,]+(?:\.\d+)?|\$\s?[\d,]+(?:\.\d+)?|\b\d+(?:,\d+)*(?:\.\d+)?\s?(?:%|lakh|lakhs|crore|crores|days|years|months)?)",
    re.IGNORECASE,
)


NEGATION_PATTERNS = [
    (re.compile(r"\bnot permitted\b|\bnot allowed\b|\bprohibited\b", re.I), "not allowed"),
    (re.compile(r"\bpermitted\b|\ballowed\b|\bmay\b", re.I), "allowed"),
    (re.compile(r"\brequired\b|\bmandatory\b|\bmust\b", re.I), "required"),
]


def extract_numbers(text: str) -> List[str]:
    return [x.strip() for x in NUMBER_PATTERN.findall(text)]


def find_numeric_conflict_candidates(matches: List[Dict]) -> List[Dict]:
    values_by_doc: Dict[str, set] = defaultdict(set)
    for match in matches:
        doc = match.get("document", "Unknown")
        values_by_doc[doc].update(extract_numbers(match.get("text", "")))

    documents = list(values_by_doc)
    candidates: List[Dict] = []

    for i, left in enumerate(documents):
        for right in documents[i + 1:]:
            a = values_by_doc[left]
            b = values_by_doc[right]
            if a and b and a != b:
                candidates.append(
                    {
                        "documents": [left, right],
                        "reason": "The retrieved evidence contains different numeric values. The investigator must determine whether they refer to the same fact.",
                        "values": {left: sorted(a), right: sorted(b)},
                    }
                )
    return candidates


def find_policy_signal_candidates(matches: List[Dict]) -> List[Dict]:
    signals_by_doc: Dict[str, set] = defaultdict(set)
    for match in matches:
        doc = match.get("document", "Unknown")
        text = match.get("text", "")
        lowered = text.lower()
        for pattern, label in NEGATION_PATTERNS:
            if pattern.search(lowered):
                signals_by_doc[doc].add(label)

    docs = list(signals_by_doc)
    candidates: List[Dict] = []
    for i, left in enumerate(docs):
        for right in docs[i + 1:]:
            left_sig = signals_by_doc[left]
            right_sig = signals_by_doc[right]
            if ("allowed" in left_sig and "not allowed" in right_sig) or (
                "not allowed" in left_sig and "allowed" in right_sig
            ):
                candidates.append(
                    {
                        "documents": [left, right],
                        "reason": "The retrieved policy language contains opposing permission signals. The exact statements should be compared before reaching a conclusion.",
                    }
                )
    return candidates


def detect_possible_conflicts(matches: List[Dict]) -> Tuple[bool, List[Dict]]:
    candidates = find_numeric_conflict_candidates(matches)
    candidates.extend(find_policy_signal_candidates(matches))

    # De-duplicate document pairs while preserving the strongest reason.
    unique: Dict[tuple, Dict] = {}
    for item in candidates:
        pair = tuple(sorted(item.get("documents", [])))
        unique.setdefault(pair, item)

    result = list(unique.values())
    return bool(result), result[:8]
