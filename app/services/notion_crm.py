import os
import requests
from dotenv import load_dotenv
# from notion_client import Client
from app.core.config import ReceiverInfo
from typing import Optional
load_dotenv

NOTION_API_KEY  = os.getenv("NOTION_API_KEY")
NOTION_DB_ID    = os.getenv("NOTION_DATABASE_ID")   # from your Notion DB URL

# notion = Client(auth=NOTION_API_KEY)
url = "https://api.notion.com/v1/pages"

headers = {
        "Authorization": f"Bearer {NOTION_API_KEY}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

# ── Map ReceiverInfo → Notion page properties ──────────────────────────────────
def save_to_notion(receiver: ReceiverInfo) -> dict:
    properties = {
        # "Name" is the Title column (Aa) in Notion
        "Name": {
            "title": [{"text": {"content": receiver.company_name or "Unknown Company"}}]
        },
        # "Website" is rich_text (≡) in Notion — NOT url type
        "Website": {
            "rich_text": [{"text": {"content": receiver.company_website or ""}}]
        },
        # "Company Type" is rich_text (≡) in Notion — NOT select
        "Company Type": {
            "rich_text": [{"text": {"content": receiver.company_type or "startup"}}]
        },
        # "Industry" is rich_text (≡) in Notion — NOT select
        "Industry": {
            "rich_text": [{"text": {"content": receiver.industry or "Unknown"}}]
        },
    }
    
    payload = {
        "parent": {"database_id": NOTION_DB_ID},
        "properties": properties,
    }
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200:
        print(f"[Notion] Created: {receiver.company_name}")
    else:
        print(f"[Notion] Error {response.status_code}: {response.text}")

    

