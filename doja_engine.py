import json
import os
import random
import urllib.parse
from pathlib import Path

import requests
from duckduckgo_search import DDGS
from openai import OpenAI

import database


API_KEY = os.getenv("GROQ_API_KEY")
if not API_KEY:
    raise RuntimeError("GROQ_API_KEY is not configured in the environment.")

client = OpenAI(
    base_url="https://api.groq.com/openai/v1",
    api_key=API_KEY,
)


PLATFORM_DOMAINS = {
    "google": "google.com",
    "wikipedia": "en.wikipedia.org",
    "wikimedia": "commons.wikimedia.org",
    "britannica": "britannica.com",
    "scholar": "scholar.google.com",
    "archive": "archive.org",
    "github": "github.com",
    "gitlab": "gitlab.com",
    "stackoverflow": "stackoverflow.com",
    "mdn": "developer.mozilla.org",
    "npm": "npmjs.com",
    "pypi": "pypi.org",
    "replit": "replit.com",
    "coursera": "coursera.org",
    "edx": "edx.org",
    "khanacademy": "khanacademy.org",
    "udemy": "udemy.com",
    "youtube": "youtube.com",
    "notion": "notion.so",
    "slack": "slack.com",
    "reddit": "reddit.com",
    "linkedin": "linkedin.com",
    "twitter": "x.com",
    "telegram": "t.me",
    "flickr": "flickr.com",
    "unsplash": "unsplash.com",
}


# -------------------------------------------------------------------
# Web and platform search
# -------------------------------------------------------------------

def search_internet(query: str) -> str:
    print(f"\n🔍 [DOJA AI Searching Web: {query!r}]")

    results = []
    with DDGS() as ddgs:
        for result in ddgs.text(query, max_results=5):
            results.append(
                f"Title: {result.get('title', '')}\n"
                f"Snippet: {result.get('body', '')}\n"
                f"Source: {result.get('href', '')}"
            )

    return "\n\n".join(results) if results else "No results found."


def platform_search(platform: str, query: str) -> str:
    platform_key = platform.lower().strip()
    domain = PLATFORM_DOMAINS.get(platform_key, f"{platform_key}.com")
    targeted_query = f"site:{domain} {query}"

    print(f"\n🌐 [DOJA AI Searching {platform.upper()}: {query!r}]")

    results = []
    with DDGS() as ddgs:
        for result in ddgs.text(targeted_query, max_results=5):
            results.append(
                f"Platform: {platform.upper()}\n"
                f"Title: {result.get('title', '')}\n"
                f"Snippet: {result.get('body', '')}\n"
                f"Link: {result.get('href', '')}"
            )

    return "\n\n".join(results) if results else f"No direct results on {platform}."


def live_github_lookup(repo_or_user: str) -> str:
    print(f"\n🐙 [DOJA AI Querying GitHub: {repo_or_user!r}]")

    try:
        response = requests.get(
            f"https://api.github.com/repos/{repo_or_user.strip()}",
            timeout=10,
            headers={"User-Agent": "DOJA-AI"},
        )

        if response.status_code == 200:
            data = response.json()
            return (
                f"Repo: {data.get('full_name')}\n"
                f"Stars: {data.get('stargazers_count')}\n"
                f"Language: {data.get('language')}\n"
                f"URL: {data.get('html_url')}"
            )
    except requests.RequestException as error:
        print(f"GitHub lookup error: {error}")

    return platform_search("github", repo_or_user)


# -------------------------------------------------------------------
# Workspace file creation
# -------------------------------------------------------------------

def create_project_file(filename: str, content: str) -> str:
    """Create a file inside the workspace directory."""
    workspace = Path("workspace").resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    # Keep generated files inside workspace; reject paths that escape it.
    target = (workspace / filename).resolve()
    if target != workspace and workspace not in target.parents:
        return "Error: file path must stay inside the workspace."

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")

    print(f"\n⚡ [DOJA AI Created: {target}]")
    return f"File '{target.relative_to(workspace)}' generated and saved in workspace."


# -------------------------------------------------------------------
# Real image search
# -------------------------------------------------------------------

def find_real_images(query: str, platform: str = "") -> str:
    """Find real-world photos and return image links in Markdown."""
    search_query = query.strip()

    if platform:
        domain = PLATFORM_DOMAINS.get(platform.lower().strip(), platform)
        search_query = f"site:{domain} {search_query}"

    print(f"\n📸 [DOJA AI Finding Images: {search_query!r}]")

    results = []
    try:
        with DDGS() as ddgs:
            for result in ddgs.images(search_query, max_results=3):
                image_url = result.get("image") or result.get("thumbnail")
                title = result.get("title", query)
                source_page = result.get("url", "")

                if image_url:
                    results.append(
                        f"![{title}]({image_url})\n"
                        f"*Photo source: [{title}]({source_page})*"
                    )
    except Exception as error:
        print(f"Image search error: {error}")

    return "\n\n".join(results) if results else f"No live photos found for '{query}'."


# -------------------------------------------------------------------
# AI image generation
# -------------------------------------------------------------------

def generate_ai_image(
    prompt: str,
    style: str = "photorealistic",
    aspect_ratio: str = "16:9",
    count: int = 1,
) -> str:
    """Create image URLs for generated artwork or diagrams."""
    print(
        f"\n🎨 [DOJA AI Image Generation: "
        f"{count} image(s), style={style}, ratio={aspect_ratio}]"
    )

    dimensions = {
        "16:9": (1280, 720),
        "1:1": (1024, 1024),
        "9:16": (720, 1280),
        "4:3": (1024, 768),
    }
    width, height = dimensions.get(aspect_ratio.strip(), (1280, 720))

    style_modifiers = {
        "diagram": (
            "scientific technical diagram, clear educational labels, "
            "professional clean infographic"
        ),
        "blueprint": (
            "architectural engineering blueprint, precise geometry, "
            "white technical lines on a blue grid"
        ),
        "flowchart": (
            "clean organizational flowchart, clear process nodes, "
            "modern vector infographic"
        ),
        "photorealistic": (
            "photorealistic, natural lighting, detailed textures, "
            "professional photography"
        ),
        "cinematic": (
            "cinematic film still, dramatic lighting, rich color grading"
        ),
        "3d": (
            "high-quality 3D render, detailed geometry, realistic lighting"
        ),
        "anime": (
            "anime aesthetic, vibrant colors, clean line art"
        ),
        "logo": (
            "minimalist professional vector logo, clean geometric design"
        ),
    }

    modifier = style_modifiers.get(
        style.lower().strip(),
        style_modifiers["photorealistic"],
    )
    full_prompt = f"{prompt.strip()}, {modifier}"

    number_of_images = max(1, min(count, 3))
    markdown_images = []

    for index in range(number_of_images):
        seed = random.randint(1000, 999999)
        encoded_prompt = urllib.parse.quote(full_prompt)
        image_url = (
            f"https://image.pollinations.ai/prompt/{encoded_prompt}"
            f"?model=turbo&width={width}&height={height}"
            f"&seed={seed}&nologo=true&enhance=true"
        )

        if number_of_images > 1:
            caption = f"{prompt[:30]} (Variation {index + 1})"
        else:
            caption = prompt[:40]

        markdown_images.append(f"![{caption}]({image_url})")

    return "\n\n".join(markdown_images) + "\n\n"


# -------------------------------------------------------------------
# Functions available to the AI
# -------------------------------------------------------------------

available_tools = {
    "search_internet": search_internet,
    "platform_search": platform_search,
    "live_github_lookup": live_github_lookup,
    "find_real_images": find_real_images,
    "generate_ai_image": generate_ai_image,
    "create_project_file": create_project_file,
}


tools_definition = [
    {
        "type": "function",
        "function": {
            "name": "search_internet",
            "description": "Search the internet for current information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "platform_search",
            "description": "Search a particular website or platform.",
            "parameters": {
                "type": "object",
                "properties": {
                    "platform": {"type": "string"},
                    "query": {"type": "string"},
                },
                "required": ["platform", "query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "live_github_lookup",
            "description": "Look up a GitHub repository by owner/repository name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_or_user": {"type": "string"},
                },
                "required": ["repo_or_user"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_real_images",
            "description": "Find real-world photos from the internet.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "platform": {
                        "type": "string",
                        "description": "Optional platform such as Wikipedia or Reddit.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_ai_image",
            "description": "Generate an image URL for artwork or a diagram.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {"type": "string"},
                    "style": {
                        "type": "string",
                        "enum": [
                            "diagram",
                            "blueprint",
                            "flowchart",
                            "photorealistic",
                            "cinematic",
                            "3d",
                            "anime",
                            "logo",
                        ],
                    },
                    "aspect_ratio": {
                        "type": "string",
                        "enum": ["16:9", "1:1", "9:16", "4:3"],
                    },
                    "count": {"type": "integer"},
                },
                "required": ["prompt"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_project_file",
            "description": "Save a generated code or text file in the workspace.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["filename", "content"],
            },
        },
    },
]


SYSTEM_PROMPT = """You are DOJA AI, an assistant for research, coding, creative work,
and development.

Use web and platform search tools when they are useful for answering a question.
Use image search for real photos, real people, places, and landmarks.
Use the image generation tool for artwork, diagrams, blueprints, and flowcharts.
Use create_project_file when the user asks you to create or save a workspace file.

Be clear and helpful. Do not invent search results. Explain uncertainty when needed.
Avoid horizontal-rule separators and Markdown pipe tables.
"""


# -------------------------------------------------------------------
# Chat, tools, and persistent project history
# -------------------------------------------------------------------

def chat_with_doja(
    user_prompt: str,
    user_id: int = 1,
    history: list = None,
    model_name: str = "openai/gpt-oss-120b",
    image_b64: str = None,
):
    custom_instructions = database.get_user_instructions(user_id)
    system_text = SYSTEM_PROMPT

    if custom_instructions:
        system_text += f"\n\nUSER CUSTOM INSTRUCTIONS:\n{custom_instructions}"

    messages = [{"role": "system", "content": system_text}]

    if isinstance(history, list):
        for message in history[-6:]:
            role = message.get("role", "user")
            content = message.get("content", "")

            if role in {"user", "assistant"}:
                messages.append({"role": role, "content": content})

    if image_b64:
        model_name = "llama-3.2-11b-vision-preview"
        messages.append({
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": user_prompt or "Analyze this image in detail.",
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_b64}"
                    },
                },
            ],
        })
    else:
        messages.append({"role": "user", "content": user_prompt})

    last_response = ""
    visual_attachments = []

    while True:
        if image_b64:
            response = client.chat.completions.create(
                model=model_name,
                messages=messages,
            )
        else:
            response = client.chat.completions.create(
                model=model_name or "openai/gpt-oss-120b",
                messages=messages,
                tools=tools_definition,
                tool_choice="auto",
            )

        assistant_message = response.choices[0].message
        tool_calls = assistant_message.tool_calls or []

        if not tool_calls:
            last_response = assistant_message.content or "Completed."
            break

        # Add the assistant tool-call message in the format expected by the API.
        messages.append(assistant_message.model_dump(exclude_none=True))

        for tool_call in tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments or "{}")
            function = available_tools.get(function_name)

            if function is None:
                result = f"Unknown tool: {function_name}"
            else:
                try:
                    result = function(**function_args)
                except Exception as error:
                    print(f"Tool {function_name} failed: {error}")
                    result = f"Tool error: {error}"

            if function_name in {"generate_ai_image", "find_real_images"}:
                visual_attachments.append(result)

            messages.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": function_name,
                "content": str(result),
            })

    if visual_attachments:
        last_response = (
            "\n\n".join(visual_attachments)
            + "\n\n"
            + last_response
        )

    # Save the user's question and DOJA's answer in PostgreSQL.
    try:
        title = user_prompt[:35] + ("..." if len(user_prompt) > 35 else "")
        saved_history = (history or []) + [
            {"role": "user", "content": user_prompt},
            {"role": "assistant", "content": last_response},
        ]

        # IMPORTANT: messages= ensures history goes into the messages column.
        database.save_project(
            user_id,
            title,
            user_prompt,
            last_response,
            messages=saved_history,
        )
    except Exception as error:
        # Check Render logs for this message if the save still fails.
        print(f"Database save error for user {user_id}: {error}")

    return last_response
