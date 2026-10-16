import os
import sys

import pysnooper
import requests
from bs4 import BeautifulSoup

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
import json

from dotenv import load_dotenv
from mistralai import Mistral

from ai.llm_helper import get_obituary_link_data

load_dotenv()


def extract_obituary_legacy_paragraph(url):
    html = request_url(url)
    soup = BeautifulSoup(html, "html.parser")
    elements = soup.find_all(attrs={"data-component": "ObituaryParagraph"})
    if elements:
        return "\n".join([element.get_text().strip() for element in elements]) 
    return ""

def extract_obituary_legacy(url):
    paragraph = extract_obituary_legacy_paragraph(url)
    return get_obituary_link_data(paragraph)
    

def request_url(url):
    api_response = requests.post(
    "https://api.zyte.com/v1/extract",
    auth=("11e14fb2fc29447997af371494c0f695", ""),  # Your API key goes in place of the dots
    json={
        "url": url,
        "browserHtml": True,
    },
)
    api_response.raise_for_status()

    browser_html = api_response.json()["browserHtml"]
    return browser_html


@pysnooper.snoop()
def extract_obituary_data(url):
    browser_html = request_url(url)
    if not("legacy.com" in url):
        browser_html = clean_html(browser_html)
        data=extract_obituary(browser_html)
    else:
        data,obituary_text=extract_obituary_legacy(url)
        data["obituary_text"]=obituary_text
    return data


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
    with open("obit.html", "w", encoding="utf-8") as f:
        f.write(html)
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
        model="mistral-small-latest",
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


def clean_html(html):
    original_size = len(html)

    soup = BeautifulSoup(html, "html.parser")

    # Remove useless tags
    for tag in soup([
        "img","select","button",
        "script",
        "style",
        "svg",
        "noscript",
        "iframe",
        "link",
        "meta",
        "head"
    ]):
        tag.decompose()



    cleaned_html = str(soup)

    cleaned_size = len(cleaned_html)

    removed = original_size - cleaned_size
    removed_percentage = (
        removed / original_size * 100
        if original_size
        else 0
    )

    print(f"Original size : {original_size:,} characters")
    print(f"Cleaned size  : {cleaned_size:,} characters")
    print(f"Removed       : {removed_percentage:.2f}%")

    return cleaned_html





def get_obituary_info(first_name,last_name,state):
    if "nj" or "jersey" in state.lower():
        state = "New+Jersey"
    elif "fl" or "florida" in state.lower():
        state = "Florida"
    else:
        state = state.replace(" ", "+")
    url = f"https://www.legacy.com/obituaries/search?query={first_name}+{last_name}&country=United+States&state={state}"
    browser_html = request_url(url)

    soup = BeautifulSoup(browser_html, "html.parser")

    main_results = soup.select_one(
        "body > div:nth-of-type(5) > div:nth-of-type(2) > "
        "div:nth-of-type(2) > div:nth-of-type(1)"
    )

    articles = main_results.find_all("article")
    search_results = []

    for article in articles:
        name = article.select_one("a").select_one("div").select_one("div").get_text()
        date_birth_death = article.select_one("a").select_one("div").select_one("span").get_text()
        obituary_snippet = article.select_one("a").select_one("p").get_text()   
        link = article.select_one("div").select_one("div").select_one("a").get("href")
        undercard = article.select_one("div").select_one("div")
        children = undercard.find_all(recursive=False)
        link = children[1].find(href=True)
        birth_date = None
        death_date = None
        if "-" in date_birth_death:
            date_split = date_birth_death.split("-")
            birth_date = date_split[0]
            death_date = date_split[1]
        extracted_data = extract_obituary_data(link.get("href"))
        result = {
                "full_name": name,
                "url": link,
                "person_id": None,
                "birth_date": extracted_data.get("date_of_birth") or birth_date,
                "death_date": extracted_data.get("date_of_death") or death_date,
                "bio": extracted_data.get("obituary_text") or obituary_snippet,
                "locations": [state.replace("+", " ")],
                
                # All LLM extracted fields
                "obituary_text": extracted_data.get("obituary_text"),
                "age": extracted_data.get("age"),
                "place_of_birth": extracted_data.get("place_of_birth") or birth_date,
                "place_of_death": extracted_data.get("place_of_death") or death_date,
                "friends": extracted_data.get("friends", []),
                "associates": extracted_data.get("associates", []),
                "heirs": extracted_data.get("heirs", [])
            }
        
        search_results.append(result)
    return search_results

#print(process_obituary_link("https://www.legacy.com/person/anthony-idris-ibrahim-taylor-50383664"))
print(get_obituary_info("William","Shortall","nj"))




