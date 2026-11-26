"""DOJA's AI engine: Groq chat, DuckDuckGo search, and image prompt links."""
import os
import urllib.parse
from dotenv import load_dotenv
from openai import OpenAI
load_dotenv()
GROQ_KEY = os.getenv("GROQ_API_KEY", "")
MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
client = OpenAI(api_key=GROQ_KEY, base_url="https://api.groq.com/openai/v1") if GROQ_KEY else None
SYSTEM_PROMPT = "You are DOJA AI, a helpful assistant in DOJA AI Studio. Answer directly, accurately, and clearly. For coding, provide runnable code and useful explanations. Do not claim to have searched the web unless search results were supplied."

def web_search(query: str, max_results: int = 5) -> str:
    try:
        from duckduckgo_search import DDGS
        with DDGS() as ddgs:
            hits = list(ddgs.text(query, max_results=max_results))
        return "\n".join(f"- {h.get('title','Result')}: {h.get('body','')} ({h.get('href','')})" for h in hits) or "No web results found."
    except Exception as e:
        return f"Search unavailable: {type(e).__name__}: {e}"

def generate_image_markdown(prompt: str, count: int = 1, ratio: str = "16:9") -> str:
    dims = {"16:9": (1280,720), "1:1": (1024,1024), "9:16": (720,1280), "4:3": (1024,768)}
    w, h = dims.get(ratio, (1280,720))
    lines = []
    for i in range(max(1, min(int(count), 3))):
        url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt)}?width={w}&height={h}&seed={81400+i*193}&nologo=true"
        lines.append(f"![DOJA image {i+1}]({url})")
    return "\n\n".join(lines)

def chat_with_doja(user_prompt: str, history=None, model_name=None, file_context="") -> str:
    if not client:
        raise RuntimeError("GROQ_API_KEY is missing. Add it to .env and restart DOJA.")
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for item in (history or [])[-16:]:
        role, content = item.get("role"), item.get("content", "")
        if role in ("user", "assistant") and isinstance(content, str) and content.strip():
            messages.append({"role": role, "content": content[:12000]})
    prompt = user_prompt
    if file_context:
        prompt += "\n\nUploaded file text:\n" + file_context[:18000]
    if any(phrase in user_prompt.lower() for phrase in ["search the web", "search online", "look up", "latest news", "current price", "today's"]):
        prompt += "\n\nSearch results:\n" + web_search(user_prompt)
    messages.append({"role": "user", "content": prompt})
    try:
        result = client.chat.completions.create(model=model_name or MODEL, messages=messages, temperature=0.65, max_tokens=4096)
        answer = result.choices[0].message.content
        if not answer:
            raise RuntimeError("The AI provider returned an empty answer.")
        return answer
    except Exception as exc:
        raise RuntimeError(f"Groq request failed: {exc}") from exc
