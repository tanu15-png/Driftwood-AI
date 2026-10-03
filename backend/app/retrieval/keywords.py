"""Deterministic keyword extraction for the lexical search branch."""

import re

# Conversational instructions should not be required to occur in a filing.
_STOP_WORDS = frozenset((
    "a", "an", "and", "are", "as", "at", "be", "been", "being", "but", "by",
    "can", "could", "did", "do", "does", "doing", "for", "from", "had", "has",
    "have", "having", "he", "her", "hers", "herself", "him", "himself", "his",
    "how", "i", "if", "in", "into", "is", "it", "its", "itself", "me", "more",
    "most", "my", "myself", "no", "nor", "not", "of", "on", "only", "or",
    "other", "our", "ours", "ourselves", "out", "over", "own", "same", "she",
    "should", "so", "some", "such", "than", "that", "the", "their", "theirs",
    "them", "themselves", "then", "there", "these", "they", "this", "those",
    "through", "to", "too", "under", "until", "up", "very", "was", "we", "were",
    "what", "when", "where", "which", "while", "who", "whom", "why", "will",
    "with", "would", "you", "your", "yours", "yourself", "yourselves",
    "according", "answer", "based", "between", "compare", "describe", "detail",
    "details", "explain", "find", "give", "include", "list", "please", "provide",
    "question", "show", "summarize", "tell", "using", "versus", "vs",
))


def extract_keywords(query: str) -> list[str]:
    normalized = query.casefold().replace("’", "'")
    normalized = re.sub(r"\b(\w+)'s\b", r"\1", normalized)
    words = re.findall(r"[^\W_]+", normalized)
    return list(dict.fromkeys(
        word for word in words
        if word not in _STOP_WORDS and (len(word) > 1 or word.isdecimal())
    ))
