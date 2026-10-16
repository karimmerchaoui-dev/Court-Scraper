import json
import os

from dotenv import load_dotenv
from mistralai import Mistral

load_dotenv()

client = Mistral(api_key=os.getenv("MISTRAL_API_KEY", ""))

schema = {
    "type": "object",
    "properties": {
        "name": {
            "type": ["string", "null"]
        },
        "obituary_text": {
            "type": ["string", "null"]
        },
        "age": {
            "type": ["integer", "null"]
        },
        "friends": {
            "type": "array",
            "items": {"type": "string"}
        },
        "associates": {
            "type": "array",
            "items": {"type": "string"}
        },
        "heirs": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "relationship": {"type": "string"}
                },
                "required": ["name", "relationship"],
                "additionalProperties": False
            }
        },
        "date_of_death": {
            "type": ["string", "null"]
        },
        "place_of_death": {
            "type": ["string", "null"]
        },
        "date_of_birth": {
            "type": ["string", "null"]
        },
        "place_of_birth": {
            "type": ["string", "null"]
        }
    },
    "required": [
        "name",
        "obituary_text",
        "age",
        "friends",
        "associates",
        "heirs",
        "date_of_death",
        "place_of_death",
        "date_of_birth",
        "place_of_birth"
    ],
    "additionalProperties": False
}

def extract_obituary(html):
    prompt = f"""
Extract information from the following obituary HTML.

Return ONLY the JSON object matching the provided schema.

Rules:
- Extract only information explicitly supported by the HTML.
- Do not guess or infer missing information.
- Use null for missing scalar values.
- Use [] for missing lists.
- Keep obituary_text as the actual obituary text, without HTML.
- age must be an integer when explicitly stated.
- Dates should be returned as YYYY-MM-DD when the exact date is available.
- If only a partial date is available, preserve the available information rather than inventing it.
- friends should contain names explicitly identified as friends.
- associates should contain people explicitly identified as associates.
- heirs should contain objects with:
  - name: the person's full name
  - relationship: their relationship to the deceased (e.g., "spouse", "son", "daughter", "sister", "brother", "grandson", "granddaughter", "nephew", "niece", "cousin", etc.)
- Do not put the deceased person's name in friends, associates, or heirs.
- For heirs, if the relationship is not explicitly stated but can be inferred from context (e.g., "survived by his wife Jane" → spouse), include it.
- If the relationship is unclear, use "family member" as the relationship.

HTML:

{html}
"""

    response = client.chat.complete(
        model="mistral-large-latest",
        messages=[
            {
                "role": "user",
                "content": prompt
            }
        ],
        response_format={
            "type": "json_schema",
            "json_schema": {
                "name": "obituary_extraction",
                "schema": schema,
                "strict": True
            }
        }
    )

    return json.loads(response.choices[0].message.content)


with open("cleaned_html.html", "r", encoding="utf-8") as f:
    html = f.read()

result = extract_obituary(html)
print(json.dumps(result, indent=2))