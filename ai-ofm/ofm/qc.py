"""Claude looks at every generated image before the owner does: same face, adult look, no visible defects."""

from . import llm

QC_SCHEMA = {
    "type": "object",
    "properties": {
        "same_person": {"type": "boolean"},
        "clearly_adult": {"type": "boolean"},
        "defects": {"type": "array", "items": {"type": "string"}},
        "verdict": {"type": "string", "enum": ["pass", "fail"]},
        "reason": {"type": "string"},
    },
    "required": ["same_person", "clearly_adult", "defects", "verdict", "reason"],
    "additionalProperties": False,
}

INSTRUCTIONS = """You check images for an AI influencer account before they are posted.
Image 1 is the persona's reference photo. Image 2 is a new photo that should show the same adult woman.

Fail the new photo if any of these is true:
- it is not clearly the same person as the reference (face shape, eyes, hair colour)
- she does not look clearly adult (21+), or anything in the scene suggests youth or school
- visible defects: extra or merged fingers, warped hands, distorted face or eyes, broken limbs, melted objects
- it looks AI-generated instead of a real phone photo: plastic or waxy skin with no pores, airbrushed or glowing look, over-perfect symmetry, painterly background, impossible lighting
- readable text, watermarks, brand logos, or other people's faces in focus

Small lighting or style differences are fine. Keep reason to one short sentence."""


def check_image(app, image_url, reference_url):
    """Returns (passed, reason); passed is None when the check could not run, so the post goes to review."""
    content = [
        {"type": "image", "source": {"type": "url", "url": reference_url}},
        {"type": "image", "source": {"type": "url", "url": image_url}},
        {"type": "text", "text": INSTRUCTIONS},
    ]
    try:
        result = llm.ask_json(app, system=None, content=content, schema=QC_SCHEMA, kind="qc", effort="low", max_tokens=4000)
    except llm.LLMRefusal:
        return False, "ο έλεγχος αρνήθηκε την εικόνα"
    except llm.LLMError as e:
        return None, f"ο έλεγχος δεν έγινε ({e}), πάει για έγκριση"
    if not isinstance(result.get("defects"), list):
        result["defects"] = []
    passed = result["verdict"] == "pass" and result["same_person"] and result["clearly_adult"]
    reason = result["reason"] or ", ".join(result["defects"])
    return passed, reason
