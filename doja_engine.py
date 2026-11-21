import os
import json
import random
import urllib.parse
import requests
from openai import OpenAI
from duckduckgo_search import DDGS
import database

# Ensure your real Groq API key is on line 11:
API_KEY = os.getenv("GROQ_API_KEY")
client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=API_KEY
)

PLATFORM_DOMAINS = {
    "google": "google.com", "wikipedia": "en.wikipedia.org", "wikimedia": "commons.wikimedia.org",
    "britannica": "britannica.com", "scholar": "scholar.google.com", "archive": "archive.org",
    "github": "github.com", "gitlab": "gitlab.com", "stackoverflow": "stackoverflow.com",
    "mdn": "developer.mozilla.org", "npm": "npmjs.com", "pypi": "pypi.org", "replit": "replit.com",
    "coursera": "coursera.org", "edx": "edx.org", "khanacademy": "khanacademy.org",
    "udemy": "udemy.com", "youtube": "youtube.com", "notion": "notion.so", "slack": "slack.com",
    "reddit": "reddit.com", "linkedin": "linkedin.com", "twitter": "x.com", "telegram": "t.me",
    "flickr": "flickr.com", "unsplash": "unsplash.com"
}

# ==========================================================
# 1. LIVE WEB & PLATFORM SEARCH
# ==========================================================
def search_internet(query: str) -> str:
    print(f"\n🔍 [DOJA AI Searching Web: '{query}']...")
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
# 2. REAL PHOTO FINDER ACROSS PLATFORMS
# ==========================================================
def find_real_images(query: str, platform: str = "") -> str:
    """Finds authentic real-world photos, social media images, and platform visuals."""
    search_query = query.strip()
    if platform:
        domain = PLATFORM_DOMAINS.get(platform.lower().strip(), platform)
        search_query = f"site:{domain} {search_query}"
        
    print(f"\n📸 [DOJA AI Finding Real Photos: '{search_query}']...")
    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.images(search_query, max_results=3):
                img_url = r.get("image") or r.get("thumbnail")
                title = r.get("title", query)
                source_page = r.get("url", "")
                if img_url:
                    results.append(f"![{title}]({img_url})\n*Photo Source: [{title}]({source_page})*")
    except Exception as e:
        print(f"Image search error: {e}")
        
    return "\n\n".join(results) if results else f"No live photos found for '{query}'."

# ==========================================================
# 3. TECHNICAL DIAGRAM & CREATIVE IMAGE GENERATOR
# ==========================================================
def generate_ai_image(prompt: str, style: str = "photorealistic", aspect_ratio: str = "16:9", count: int = 1) -> str:
    """Generates high-definition AI images, any type of scientific/technical diagram, or artwork."""
    print(f"\n🎨 [DOJA AI Studio: Generating {count} image(s) | Style: {style} | Ratio: {aspect_ratio}]...")
    
    dimensions = {
        "16:9": (1280, 720),
        "1:1": (1024, 1024),
        "9:16": (720, 1280),
        "4:3": (1024, 768)
    }
    width, height = dimensions.get(aspect_ratio.strip(), (1280, 720))

    style_modifiers = {
        "diagram": "scientific technical diagram, clean educational biological or engineering schematic, high-contrast labels, detailed visual breakdown, professional vector infographic, white or dark presentation background",
        "blueprint": "architectural engineering blueprint, technical CAD drawing, white grid lines on blue blueprint background, precise geometric dimensions",
        "flowchart": "clean organizational flowchart diagram, clear process nodes, modern vector UI layout, infographic structure",
        "photorealistic": "photorealistic, raw photo, natural lighting, 50mm f/1.8 lens, 8k resolution, ultra-detailed textures",
        "cinematic": "cinematic film still, anamorphic lens, dramatic moody lighting, 35mm film grain, Hollywood color grading",
        "3d": "3D render, Octane render, Unreal Engine 5, raytraced reflections, volumetric lighting, smooth 3D geometry",
        "anime": "anime aesthetic, Studio Ghibli and Makoto Shinkai style, vibrant colors, clean lineart",
        "logo": "minimalist vector logo, flat design, clean geometric lines, professional branding emblem, white background"
    }
    modifier = style_modifiers.get(style.lower().strip(), style_modifiers["photorealistic"])
    full_prompt = f"{prompt.strip()}, {modifier}"

    num_images = max(1, min(count, 3))
    markdown_output = []

    for i in range(num_images):
        seed = random.randint(1000, 999999)
        clean_url_prompt = urllib.parse.quote(full_prompt)
        image_url = f"https://image.pollinations.ai/prompt/{clean_url_prompt}?model=turbo&width={width}&height={height}&seed={seed}&nologo=true&enhance=true"
        caption = f"{prompt[:30]} (Variation {i+1})" if num_images > 1 else prompt[:40]
        markdown_output.append(f"![{caption}]({image_url})")

    return "\n\n".join(markdown_output) + "\n\n"

available_tools = {
    "search_internet": search_internet,
    "platform_search": platform_search,
    "live_github_lookup": live_github_lookup,
    "find_real_images": find_real_images,
    "generate_ai_image": generate_ai_image,
    "create_project_file": create_project_file
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
            "description": "Search specific platforms (github, stackoverflow, mdn, wikipedia, reddit, etc.).",
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
            "name": "find_real_images",
            "description": "Find and display real-world photos, real people, historical figures, landmarks, or social media photos from across platforms (Wikipedia, Reddit, Flickr, Unsplash, etc.).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Subject, person, or landmark to search for."},
                    "platform": {"type": "string", "description": "Optional specific platform name (e.g. 'wikipedia', 'reddit', 'flickr', 'unsplash')."}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_ai_image",
            "description": "Generate AI images, any kind of scientific/technical diagram (biology, circuits, anatomy, flowcharts), or creative artwork.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string", "description": "Detailed visual description."},
                    "style": {
                        "type": "string",
                        "enum": ["diagram", "blueprint", "flowchart", "photorealistic", "cinematic", "3d", "anime", "logo"],
                        "description": "Style or diagram type."
                    },
                    "aspect_ratio": {"type": "string", "enum": ["16:9", "1:1", "9:16", "4:3"]},
                    "count": {"type": "integer"}
                },
                "required": ["prompt"]
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
    }
]

SYSTEM_PROMPT = """You are DOJA AI — an advanced intelligence connected to real-world platforms, developer tools, live web images, and AI visual generators.

VISUAL & IMAGE RULES:
1. FOR REAL PHOTOS, REAL PEOPLE, REAL PLACES & SOCIAL MEDIA:
   - When asked to show photos of real people, celebrities, landmarks, historical figures, or social media pictures, use 'find_real_images'. You can specify a platform like 'wikipedia', 'reddit', 'flickr', or 'unsplash'.
2. FOR TECHNICAL & SCIENTIFIC DIAGRAMS:
   - When asked for flowcharts, circuit blueprints, plant/human biology diagrams, or architecture maps, use 'generate_ai_image' with style='diagram', 'blueprint', or 'flowchart'.
3. FOR ARTWORK & CONCEPT ART:
   - Use 'generate_ai_image' with photorealistic, cinematic, 3d, anime, or logo styles.

TEXT STYLE RULES:
- NO horizontal lines ('---' or '===').
- NO markdown pipe tables ('|---|---|').
- Clean, well-spaced paragraphs with bold titles followed by a colon.
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
    visual_attachments = []

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

                    # Capture rendered diagrams or found real photos!
                    if fn_name in ["generate_ai_image", "find_real_images"]:
                        visual_attachments.append(result)

                    messages.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": fn_name,
                        "content": result
                    })
            else:
                last_response = msg.content or "Completed."
                break

    # Attach any found photos or diagrams directly at the top of the answer
    if visual_attachments:
        last_response = "\n\n".join(visual_attachments) + "\n\n" + last_response

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
