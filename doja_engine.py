import os
import json
import urllib.parse
import requests
from openai import OpenAI
from duckduckgo_search import DDGS
import database

# Put your real Groq API key here:
API_KEY = "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"

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=API_KEY
)

PLATFORM_DOMAINS = {
    "google": "google.com", "wikipedia": "en.wikipedia.org", "britannica": "britannica.com",
    "scholar": "scholar.google.com", "archive": "archive.org", "github": "github.com",
    "gitlab": "gitlab.com", "stackoverflow": "stackoverflow.com", "mdn": "developer.mozilla.org",
    "npm": "npmjs.com", "pypi": "pypi.org", "replit": "replit.com", "coursera": "coursera.org",
    "edx": "edx.org", "khanacademy": "khanacademy.org", "udemy": "udemy.com", "youtube": "youtube.com",
    "notion": "notion.so", "slack": "slack.com", "reddit": "reddit.com", "linkedin": "linkedin.com",
    "twitter": "x.com", "telegram": "t.me"
}

def search_internet(query: str) -> str:
    print(f"\n🔍 [DOJA AI Searching: '{query}']...")
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=5):
            results.append(f"Title: {r['title']}\nSnippet: {r['body']}\nSource: {r['href']}")
    return "\n\n".join(results) if results else "No results found."

def platform_search(platform: str, query: str) -> str:
    platform_key = platform.lower().strip()
    domain = PLATFORM_DOMAINS.get(platform_key, f"{platform_key}.com")
    targeted_query = f"site:{domain} {query}"
    print(f"\n🌐 [DOJA AI Connecting to {platform.upper()}: '{query}']...")
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(targeted_query, max_results=5):
            results.append(f"Platform: {platform.upper()}\nTitle: {r['title']}\nSnippet: {r['body']}\nLink: {r['href']}")
    return "\n\n".join(results) if results else f"No direct results on {platform}."

def live_github_lookup(repo_or_user: str) -> str:
    print(f"\n🐙 [DOJA AI Querying GitHub: '{repo_or_user}']...")
    try:
        res = requests.get(f"https://api.github.com/repos/{repo_or_user.strip()}", timeout=5, headers={"User-Agent": "DOJA-AI"})
        if res.status_code == 200:
            d = res.json()
            return f"Repo: {d.get('full_name')}\nStars: {d.get('stargazers_count')}\nLanguage: {d.get('language')}\nURL: {d.get('html_url')}"
    except Exception:
        pass
    return platform_search("github", repo_or_user)

def create_project_file(filename: str, content: str) -> str:
    os.makedirs("workspace", exist_ok=True)
    filepath = os.path.join("workspace", filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"\n⚡ [DOJA AI Created: {filepath}]")
    return f"File '{filename}' generated and saved in workspace."

def generate_image(prompt: str) -> str:
    print(f"\n🎨 [DOJA AI Generating Image: '{prompt}']...")
    clean_prompt = urllib.parse.quote(prompt.strip())
    image_url = f"https://image.pollinations.ai/prompt/{clean_prompt}?width=1024&height=600&nologo=true"
    return f"\n\n![{prompt}]({image_url})\n\n"

available_tools = {
    "search_internet": search_internet,
    "platform_search": platform_search,
    "live_github_lookup": live_github_lookup,
    "create_project_file": create_project_file,
    "generate_image": generate_image
}

tools_definition = [
    {
        "type": "function",
        "function": {
            "name": "search_internet",
            "description": "General web search across the internet.",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "platform_search",
            "description": "Targeted search on github, stackoverflow, mdn, wikipedia, reddit, youtube, etc.",
            "parameters": {
                "type": "object",
                "properties": {"platform": {"type": "string"}, "query": {"type": "string"}},
                "required": ["platform", "query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "live_github_lookup",
            "description": "Directly check GitHub repositories for code and star count.",
            "parameters": {"type": "object", "properties": {"repo_or_user": {"type": "string"}}, "required": ["repo_or_user"]}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_project_file",
            "description": "Save code files into workspace for web, 2D/3D games, calculators, or scripts.",
            "parameters": {
                "type": "object",
                "properties": {"filename": {"type": "string"}, "content": {"type": "string"}},
                "required": ["filename", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_image",
            "description": "Generate an AI visual illustration, diagram, logo, or poster.",
            "parameters": {"type": "object", "properties": {"prompt": {"type": "string"}}, "required": ["prompt"]}
        }
    }
]

SYSTEM_PROMPT = """You are DOJA AI — an advanced autonomous intelligence, engineer, educator, and research platform.

CORE CAPABILITIES:
- Coding in all languages (Python, JavaScript, C++, C#, Java, Rust, Go, SQL).
- 2D and 3D browser games (Three.js/Canvas), interactive calculators, and full websites saved to 'workspace' using 'create_project_file' to preview live.
- Multi-source research across connected platforms (GitHub, MDN, Stack Overflow, Wikipedia, PyPI, npm).
- Visual concept art and diagrams using 'generate_image'.

STRICT TEXT FORMATTING:
- NO horizontal lines (never use '---' or '===').
- NO markdown pipe tables (never use '|---|---|').
- Clean, well-spaced paragraphs with bold titles followed by a colon.
"""

def chat_with_doja(user_prompt: str, user_id: int = 1, history: list = None, model_name: str = "openai/gpt-oss-120b"):
    custom_inst = database.get_user_instructions(user_id)
    system_text = SYSTEM_PROMPT
    if custom_inst:
        system_text += f"\n\nUSER CUSTOM INSTRUCTIONS:\n{custom_inst}"

    messages = [{"role": "system", "content": system_text}]

    # Load multi-turn conversation memory (last 6 exchanges)
    if history and isinstance(history, list):
        for msg in history[-6:]:
            messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})

    messages.append({"role": "user", "content": user_prompt})

    last_response = ""
    while True:
        response = client.chat.completions.create(
            model=model_name or "openai/gpt-oss-120b",
            messages=messages,
            tools=tools_definition,
            tool_choice="auto"
        )
        msg = response.choices[0].message
        messages.append(msg)

        if msg.tool_calls:
            for tool_call in msg.tool_calls:
                fn_name = tool_call.function.name
                fn_args = json.loads(tool_call.function.arguments)
                tool_func = available_tools[fn_name]
                result = tool_func(**fn_args)

                messages.append({
                    "tool_call_id": tool_call.id,
                    "role": "tool",
                    "name": fn_name,
                    "content": result
                })
        else:
            last_response = msg.content or "Completed."
            break

    try:
        title = user_prompt[:35] + ("..." if len(user_prompt) > 35 else "")
        database.save_project(user_id, title, user_prompt, last_response)
    except Exception as e:
        print(f"Database error: {e}")

    return last_response