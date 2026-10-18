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


def with_disclosure(hashtags, tag="#aigenerated"):
    """Normalise hashtags and put the persona's AI disclosure tag quietly at the end.

    Captions themselves do not talk about being AI (the bio and the platforms' AI labels do). With an
    empty `tag` the owner discloses on the profile only, and AI tags the model added are dropped too."""
    tags = []
    for t in hashtags or []:
        t = "#" + t.strip().lstrip("#").replace(" ", "")
        if len(t) > 1 and t.lower() not in {x.lower() for x in tags}:
            tags.append(t)
    if not tag:
        return [t for t in tags if t.lower() not in DISCLOSURE_TAGS]
    if not any(t.lower() in DISCLOSURE_TAGS for t in tags):
        tags.append(tag)
    return tags
