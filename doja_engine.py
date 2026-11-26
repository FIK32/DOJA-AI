import json
import os
import random
import urllib.parse
from contextvars import ContextVar
import requests
from duckduckgo_search import DDGS
from openai import OpenAI
import database

API_KEY = os.getenv("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")
if not API_KEY:
    raise RuntimeError("GROQ_API_KEY is not configured in the environment.")
client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=API_KEY)
CURRENT_USER_ID = ContextVar("doja_user_id", default=None)

PLATFORM_DOMAINS = {"google":"google.com","wikipedia":"en.wikipedia.org","wikimedia":"commons.wikimedia.org","britannica":"britannica.com","scholar":"scholar.google.com","archive":"archive.org","github":"github.com","gitlab":"gitlab.com","stackoverflow":"stackoverflow.com","mdn":"developer.mozilla.org","npm":"npmjs.com","pypi":"pypi.org","replit":"replit.com","coursera":"coursera.org","edx":"edx.org","khanacademy":"khanacademy.org","udemy":"udemy.com","youtube":"youtube.com","notion":"notion.so","slack":"slack.com","reddit":"reddit.com","linkedin":"linkedin.com","twitter":"x.com","telegram":"t.me","flickr":"flickr.com","unsplash":"unsplash.com"}


def search_internet(query):
    with DDGS() as ddgs:
        results = [f"Title: {r.get('title','')}\nSnippet: {r.get('body','')}\nSource: {r.get('href','')}" for r in ddgs.text(query, max_results=5)]
    return "\n\n".join(results) if results else "No results found."


def platform_search(platform, query):
    key = platform.lower().strip()
    domain = PLATFORM_DOMAINS.get(key, f"{key}.com")
    with DDGS() as ddgs:
        results = [f"Platform: {platform.upper()}\nTitle: {r.get('title','')}\nSnippet: {r.get('body','')}\nLink: {r.get('href','')}" for r in ddgs.text(f"site:{domain} {query}", max_results=5)]
    return "\n\n".join(results) if results else f"No direct results on {platform}."


def live_github_lookup(repo_or_user):
    try:
        response = requests.get(f"https://api.github.com/repos/{repo_or_user.strip()}", timeout=10, headers={"User-Agent":"DOJA-AI"})
        if response.status_code == 200:
            data = response.json()
            return f"Repo: {data.get('full_name')}\nStars: {data.get('stargazers_count')}\nLanguage: {data.get('language')}\nURL: {data.get('html_url')}"
    except requests.RequestException:
        pass
    return platform_search("github", repo_or_user)


def create_project_file(filename, content):
    from pathlib import Path
    user_id = CURRENT_USER_ID.get()
    if not user_id:
        return "Error: sign in before creating workspace files."
    target = Path(filename)
    if target.is_absolute() or ".." in target.parts:
        return "Error: file path must stay inside the workspace."
    database.save_workspace_file(target.name, content.encode("utf-8"), user_id)
    return f"File '{target.name}' saved to your Appwrite workspace."


def find_real_images(query, platform=""):
    search_query = query.strip()
    if platform:
        domain = PLATFORM_DOMAINS.get(platform.lower().strip(), platform)
        search_query = f"site:{domain} {search_query}"
    try:
        with DDGS() as ddgs:
            results = []
            for result in ddgs.images(search_query, max_results=3):
                image_url = result.get("image") or result.get("thumbnail")
                title = result.get("title", query)
                source_page = result.get("url", "")
                if image_url:
                    results.append(f"![{title}]({image_url})\n*Photo source: [{title}]({source_page})*")
    except Exception:
        results = []
    return "\n\n".join(results) if results else f"No live photos found for '{query}'."


def generate_ai_image(prompt, style="photorealistic", aspect_ratio="16:9", count=1):
    dimensions = {"16:9":(1280,720),"1:1":(1024,1024),"9:16":(720,1280),"4:3":(1024,768)}
    width, height = dimensions.get(aspect_ratio.strip(), (1280,720))
    modifiers = {"diagram":"scientific technical diagram, clear educational labels, professional clean infographic","blueprint":"architectural engineering blueprint, precise geometry, white technical lines on a blue grid","flowchart":"clean organizational flowchart, clear process nodes, modern vector infographic","photorealistic":"photorealistic, natural lighting, detailed textures, professional photography","cinematic":"cinematic film still, dramatic lighting, rich color grading","3d":"high-quality 3D render, detailed geometry, realistic lighting","anime":"anime aesthetic, vibrant colors, clean line art","logo":"minimalist professional vector logo, clean geometric design"}
    full_prompt = f"{prompt.strip()}, {modifiers.get(style.lower().strip(), modifiers['photorealistic'])}"
    images = []
    for index in range(max(1, min(count, 3))):
        seed = random.randint(1000,999999)
        url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(full_prompt)}?model=turbo&width={width}&height={height}&seed={seed}&nologo=true&enhance=true"
        caption = f"{prompt[:30]} (Variation {index + 1})" if count > 1 else prompt[:40]
        images.append(f"![{caption}]({url})")
    return "\n\n".join(images) + "\n\n"


available_tools = {"search_internet":search_internet,"platform_search":platform_search,"live_github_lookup":live_github_lookup,"find_real_images":find_real_images,"generate_ai_image":generate_ai_image,"create_project_file":create_project_file}

tools_definition = [
{"type":"function","function":{"name":"search_internet","description":"Search the internet for current information.","parameters":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}}},
{"type":"function","function":{"name":"platform_search","description":"Search a particular website or platform.","parameters":{"type":"object","properties":{"platform":{"type":"string"},"query":{"type":"string"}},"required":["platform","query"]}}},
{"type":"function","function":{"name":"live_github_lookup","description":"Look up a GitHub repository by owner/repository name.","parameters":{"type":"object","properties":{"repo_or_user":{"type":"string"}},"required":["repo_or_user"]}}},
{"type":"function","function":{"name":"find_real_images","description":"Find real-world photos from the internet.","parameters":{"type":"object","properties":{"query":{"type":"string"},"platform":{"type":"string"}},"required":["query"]}}},
{"type":"function","function":{"name":"generate_ai_image","description":"Generate an image URL for artwork or a diagram.","parameters":{"type":"object","properties":{"prompt":{"type":"string"},"style":{"type":"string","enum":["diagram","blueprint","flowchart","photorealistic","cinematic","3d","anime","logo"]},"aspect_ratio":{"type":"string","enum":["16:9","1:1","9:16","4:3"]},"count":{"type":"integer"}},"required":["prompt"]}}},
{"type":"function","function":{"name":"create_project_file","description":"Save a generated code or text file in the workspace.","parameters":{"type":"object","properties":{"filename":{"type":"string"},"content":{"type":"string"}},"required":["filename","content"]}}}
]

SYSTEM_PROMPT = """You are DOJA AI, an assistant for research, coding, creative work, and development. Use web and platform search tools when useful. Use image search for real photos and image generation for artwork, diagrams, blueprints, and flowcharts. Use create_project_file when the user asks you to save a workspace file. Be clear and helpful, do not invent search results, explain uncertainty, and avoid horizontal-rule separators and Markdown pipe tables."""


def chat_with_doja(user_prompt, user_id, history=None, model_name="openai/gpt-oss-120b", image_b64=None):
    token = CURRENT_USER_ID.set(str(user_id))
    try:
        custom_instructions = database.get_user_instructions(user_id)
        system_text = SYSTEM_PROMPT
        if custom_instructions:
            system_text += f"\n\nUSER CUSTOM INSTRUCTIONS:\n{custom_instructions}"
        messages = [{"role":"system","content":system_text}]
        if isinstance(history, list):
            for message in history[-6:]:
                role = message.get("role","user")
                content = message.get("content","")
                if role in {"user","assistant"}:
                    messages.append({"role":role,"content":content})
        if image_b64:
            model_name = "llama-3.2-11b-vision-preview"
            messages.append({"role":"user","content":[{"type":"text","text":user_prompt or "Analyze this image in detail."},{"type":"image_url","image_url":{"url":f"data:image/jpeg;base64,{image_b64}"}}]})
        else:
            messages.append({"role":"user","content":user_prompt})
        visual_attachments = []
        for _ in range(8):
            options = {"model":model_name or "openai/gpt-oss-120b","messages":messages}
            if not image_b64:
                options.update(tools=tools_definition, tool_choice="auto")
            response = client.chat.completions.create(**options)
            assistant_message = response.choices[0].message
            tool_calls = assistant_message.tool_calls or []
            if not tool_calls:
                answer = assistant_message.content or "Completed."
                break
            messages.append(assistant_message.model_dump(exclude_none=True))
            for call in tool_calls:
                name = call.function.name
                try:
                    args = json.loads(call.function.arguments or "{}")
                    result = available_tools[name](**args) if name in available_tools else f"Unknown tool: {name}"
                except Exception as error:
                    print(f"Tool {name} failed: {error}")
                    result = "Tool failed. Please try again."
                if name in {"generate_ai_image","find_real_images"}:
                    visual_attachments.append(str(result))
                messages.append({"tool_call_id":call.id,"role":"tool","name":name,"content":str(result)})
        else:
            answer = "Tool call limit reached. Please try a simpler request."
        if visual_attachments:
            answer = "\n\n".join(visual_attachments) + "\n\n" + answer
        saved_history = (history or []) + [{"role":"user","content":user_prompt},{"role":"assistant","content":answer}]
        title = user_prompt[:35] + ("..." if len(user_prompt) > 35 else "")
        try:
            database.save_project(user_id, title, user_prompt, answer, messages=saved_history)
        except Exception as error:
            print(f"Appwrite project save failed: {error}")
        return answer
    finally:
        CURRENT_USER_ID.reset(token)
