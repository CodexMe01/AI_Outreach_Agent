# Smart Outreach Emailer

![GitHub stars](https://img.shields.io/github/stars/yourusername/Smart_Outreach_Emailer?style=social)

A **smart outreach email automation** tool powered by LangChain, LangGraph, Groq LLM, and Notion integration. It helps you generate personalized B2B outreach emails at scale while keeping a clean record of each interaction in your Notion CRM.

## Table of Contents
- [Features](#features)
- [Demo](#demo)
- [Installation](#installation)
- [Configuration](#configuration)
- [Usage](#usage)
- [Agent Workflow Details](#agent-workflow-details)
- [Project Structure](#project-structure)
- [Contributing](#contributing)
- [License](#license)

## Features
- **AI‑generated personalized emails** using the latest Groq LLM models.
- **LangGraph workflow orchestration** for multi‑step email creation, validation, and logging.
- **Notion CRM sync** – automatically push email content and recipient metadata to a Notion database.
- **Extensible architecture** with clear separation of concerns (email generation, Notion handling, CLI/GUI entry points).
- **Environment‑based configuration** for secret keys and Notion IDs.

## Demo
![Demo GIF](demo.gif)

## Installation
```bash
# Clone the repository
git clone https://github.com/yourusername/Smart_Outreach_Emailer.git
cd Smart_Outreach_Emailer

# Create a virtual environment (recommended)
python -m venv venv
venv\Scripts\activate  # Windows
# or source venv/bin/activate on macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

## Configuration
Create a `.env` file in the project root (already present) with the following variables:

```
GROQ_API_KEY=your_groq_api_key
NOTION_API_KEY=your_notion_integration_key
NOTION_DATABASE_ID=your_notion_database_id
```

> **Tip:** Use a password manager or secret‑manager to keep these keys safe.

## Usage
```bash
# Run the main script to generate and send an outreach email
python main.py
```

The script will:
1. Load the workflow defined in `Reasearcher.py` (LangGraph).
2. Generate an email draft based on the provided prompt.
3. Log the draft and recipient information to Notion via `notion_crm.py`.
4. (Optional) Send the email using your SMTP configuration (extend `Emailer.py`).

## Agent Workflow Details

The Smart Outreach Emailer agent performs the following steps to craft a highly relevant outreach email:

1. **Research Company Names** – Generates a list of target companies based on industry, size, and other criteria.
2. **Research Sender & Receiver** – Retrieves information about the sender (e.g., user profile) and the receiver (prospect) such as role, recent news, LinkedIn activity, and contact details.
3. **Analyze Relevance** – Scores each prospect for relevance, filters out low‑fit candidates, and selects the most promising ones.
4. **Compose Prompt** – Assembles a detailed prompt that includes company insights, sender background, and personalization cues.
5. **Generate Email Draft** – Calls the Groq LLM via LangChain to produce a personalized outreach email.
6. **Validate & Refine** – Optionally runs validation nodes (tone check, length check) and refines the draft.



You can also import the core functions into your own Python projects: (In progress)
```python
from Emailer import send_email
from notion_crm import upload_to_notion
```

## Project Structure
```
Smart_Outreach_Emailer/
│
├─ .env                 # Environment variables (not tracked in Git)
├─ main.py              # Entry point script
├─ Emailer.py           # Email sending utilities (In progress)
├─ notion_crm.py        # Notion integration helpers (In progress)
├─ Reasearcher.py       # LangGraph workflow definition
├─ requirements.txt     # Python dependencies
├─ README.md            # This documentation
└─ ...
```

## Contributing
Contributions are welcome! Please follow these steps:
1. Fork the repository.
2. Create a feature branch (`git checkout -b feature/awesome-feature`).
3. Write tests and ensure they pass.
4. Submit a Pull Request with a clear description of changes.

## License
This project is licensed under the **MIT License** – see the [LICENSE](LICENSE) file for details.

*Happy outreaching!*
