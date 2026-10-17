"""Claude looks at every generated image before the owner does: same face, adult look, no visible defects."""

import json

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
- readable text, watermarks, brand logos, or other people's faces in focus

Small lighting or style differences are fine. Keep reason to one short sentence."""


def check_image(app, image_url, reference_url):
    """Returns (passed, reason). Costs are recorded as kind 'qc'."""
    response = app.claude.beta.messages.create(
        model=app.cfg.models["claude"],
        max_tokens=4000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": QC_SCHEMA}},
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "url", "url": reference_url}},
                {"type": "image", "source": {"type": "url", "url": image_url}},
                {"type": "text", "text": INSTRUCTIONS},
            ],
        }],
    )
    price = app.cfg.models["claude_usd_per_mtok"]
    usage = response.usage
    app.db.add_cost("qc", (usage.input_tokens * price["input"] + usage.output_tokens * price["output"]) / 1_000_000, image_url[-40:])
    if response.stop_reason == "refusal":
        return False, "ο έλεγχος αρνήθηκε την εικόνα"
    text = next((b.text for b in response.content if b.type == "text"), "")
    try:
        result = json.loads(text)
    except ValueError:
        return True, "ο έλεγχος δεν απάντησε καθαρά, πάει για έγκριση"
    passed = result["verdict"] == "pass" and result["same_person"] and result["clearly_adult"]
    reason = result["reason"] or ", ".join(result["defects"])
    return passed, reason
