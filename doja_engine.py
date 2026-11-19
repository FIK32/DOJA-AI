import os
import json
import random
import urllib.parse
import requests
from openai import OpenAI
from duckduckgo_search import DDGS
import database

# Ensure your real Groq API key is here:
API_KEY = "PASTE_YOUR_API_KEY_HERE"

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

# ==========================================================
# HIGH-FIDELITY FLUX IMAGE GENERATION ENGINE
# ==========================================================
def generate_image(prompt: str) -> str:
    """Generates studio-grade visuals using high-definition Flux models."""
    print(f"\n🎨 [DOJA AI Studio Rendering Image: '{prompt[:60]}...']...")
    clean_prompt = urllib.parse.quote(prompt.strip())
    seed = random.randint(1000, 999999)
    # Uses Flux with 1280x720 HD resolution, unique seed, and no watermarks
    image_url = f"https://image.pollinations.ai/prompt/{clean_prompt}?model=flux&width=1280&height=720&seed={seed}&nologo=true"
    return f"\n\n![{prompt[:40]}]({image_url})\n\n"

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
            "description": "Targeted search on specific platforms (github, stackoverflow, mdn, wikipedia, reddit, etc.).",
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
            "description": "Generate high-definition AI images, photographs, diagrams, or visual artwork.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Comprehensive visual prompt including subject, environment, lighting, camera lens, perspective, and color grading."
                    }
                },
                "required": ["prompt"]
            }
        }
    }
]

# ==========================================================
# MASTER SYSTEM PROMPT (8 IMAGE CRITERIA INCLUDED)
# ==========================================================
SYSTEM_PROMPT = """You are DOJA AI — an elite autonomous intelligence, developer, researcher, and visual artist.

### 🎨 8-POINT IMAGE GENERATION ARCHITECTURE:
Whenever the user asks for an image, diagram, illustration, or when a topic benefits from a visual, you MUST call 'generate_image' following these 8 rules:

1. Prompt Understanding: Analyze the core subject, background, lighting, color palette, camera angle, and artistic medium. Enhance brief user requests into descriptive, vivid prompts.
2. Image Quality: Target photorealism, 8k resolution, razor-sharp textures, natural raytraced shadows, and studio color grading.
3. Image Styles: Seamlessly produce Photorealistic Photography, Cinematic Film Still, 3D Octane Render, Scientific Biological Diagrams, Architectural Visualizations, or Digital Paintings based on user context.
4. Photographic Standards: Specify camera perspectives (eye-level, wide-angle, macro), lens properties (e.g. 50mm f/1.8 lens, shallow depth of field), exposure, and volumetric lighting (golden hour, studio rim light).
5. Composition: Establish a clean focal subject with balanced rule-of-thirds framing, avoiding distorted or cluttered elements.
6. Diagrams & Education: For biology, agriculture, or science, specify clean botanical/anatomical accuracy with structured visual organization.
7. Image Refinement: Ensure anatomical and structural accuracy before calling the tool.
8. Output: ALWAYS return the actual rendered image via the 'generate_image' tool. Never merely write a textual description of what an image should look like.

### 📝 CLEAN TEXT STYLING:
- NO horizontal divider lines ('---' or '===').
- NO markdown pipe tables ('|---|---|').
- Clean, well-spaced paragraphs with a bold heading followed by a colon.
"""

def chat_with_doja(user_prompt: str, user_id: int = 1, history: list = None, model_name: str = "openai/gpt-oss-120b", image_b64: str = None):
    custom_inst = database.get_user_instructions(user_id)
    system_text = SYSTEM_PROMPT
    if custom_inst:
        system_text += f"\n\nUSER CUSTOM INSTRUCTIONS:\n{custom_inst}"

    messages = [{"role": "system", "content": system_text}]

    if history and isinstance(history, list):
        for msg in history[-6:]:
            messages.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})

    if image_b64:
        model_name = "llama-3.2-11b-vision-preview"
        user_content = [
            {"type": "text", "text": user_prompt or "Analyze this image in detail and describe what you see."},
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}
        ]
        messages.append({"role": "user", "content": user_content})
    else:
        messages.append({"role": "user", "content": user_prompt})

    last_response = ""
    generated_images = []

    while True:
        if image_b64:
            response = client.chat.completions.create(model=model_name, messages=messages)
            last_response = response.choices[0].message.content or "Image analyzed successfully."
            break
        else:
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

                    # Capture rendered image
                    if fn_name == "generate_image":
                        generated_images.append(result)

                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": fn_name,
                        "content": result
                    })
            else:
                last_response = msg.content or "Completed."
                break

    # Guarantee the image is attached to the top of the answer
    if generated_images:
        last_response = "".join(generated_images) + "\n\n" + last_response

    try:
        title = user_prompt[:35] + ("..." if len(user_prompt) > 35 else "")
        saved_history = (history or []) + [
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": last_response}
        ]
        database.save_project(user_id, title, user_prompt, last_response, saved_history)
    except Exception as e:
        print(f"Database save error: {e}")

    return last_response
