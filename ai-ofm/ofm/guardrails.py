"""Hard content rules applied to every prompt and caption before anything is generated or posted."""

import re

MINOR_PATTERNS = [
    r"\bteen", r"\bpre-?teen", r"\bunder-?age", r"\bminors?\b", r"\bchild", r"\bkids?\b",
    r"\bschool ?girls?\b", r"\bschool uniform", r"\bhigh ?school", r"\bloli", r"\bbarely legal",
    r"\byoung[- ]looking", r"\blittle girl", r"\bjailbait", r"\bbaby ?face",
    r"\b1[0-7][- ]?(year|yr|yo\b|y/o)",
    r"ανήλικ", r"μαθήτρι", r"σχολικ", r"κοριτσάκι",
]

REAL_PERSON_PATTERNS = [
    r"\bdeep ?fake", r"\blook-?alike", r"\bcelebrity", r"\bcelebrities", r"\bfamous (actress|singer|model)",
]

HUMAN_CLAIM_PATTERNS = [
    r"\bnot (an? )?ai\b", r"\bno ai\b", r"\b100% real\b", r"\bi'?m (a )?real\b", r"\breal (girl|woman|person)\b",
    r"\bnot a bot\b", r"\bnot fake\b", r"δεν είμαι ai",
]

DISCLOSURE_TAGS = {"#ai", "#aigenerated", "#aiart", "#aimodel", "#aiinfluencer", "#aigirl", "#aicreator"}

_RULES = [
    ("minor", MINOR_PATTERNS),
    ("real_person", REAL_PERSON_PATTERNS),
    ("claims_human", HUMAN_CLAIM_PATTERNS),
]


def violations(*texts):
    """Return the names of the rules any of the texts break."""
    found = []
    blob = "\n".join(t for t in texts if t)
    for name, patterns in _RULES:
        if any(re.search(p, blob, re.IGNORECASE) for p in patterns):
            found.append(name)
    return found


def with_disclosure(hashtags):
    """Normalise hashtags and make sure at least one AI disclosure tag is present."""
    tags = []
    for tag in hashtags or []:
        tag = "#" + tag.strip().lstrip("#").replace(" ", "")
        if len(tag) > 1 and tag.lower() not in {t.lower() for t in tags}:
            tags.append(tag)
    if not any(t.lower() in DISCLOSURE_TAGS for t in tags):
        tags.insert(0, "#AI")
    return tags
