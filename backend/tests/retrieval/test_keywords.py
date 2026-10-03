import pytest

from app.retrieval.keywords import extract_keywords


@pytest.mark.parametrize("query, expected", [
    ("What is Apple's iPhone vs Services revenue mix?", ["apple", "iphone", "services", "revenue", "mix"]),
    ("Please show Microsoft's Azure revenue in fiscal 2024.", ["microsoft", "azure", "revenue", "fiscal", "2024"]),
    ("Apple's revenue, APPLE revenue and margins", ["apple", "revenue", "margins"]),
    ("Compare AWS and AI infrastructure costs", ["aws", "ai", "infrastructure", "costs"]),
    ("What is the operating margin?", ["operating", "margin"]),
    ("What is NVIDIA's 5 year growth?", ["nvidia", "5", "year", "growth"]),
    ("revenue | !profits:* & (costs)", ["revenue", "profits", "costs"]),
    ("Please tell me what it is", []),
    ("  ", []),
    ("!@#$%^&*()", []),
])
def test_extracts_deduplicated_content_keywords(query, expected):
    assert extract_keywords(query) == expected
