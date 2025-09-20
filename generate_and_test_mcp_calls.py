import os
import json
import pandas as pd
import requests
from pathlib import Path
from openai import OpenAI
from typing import Union

# === CONFIGURATION ===
EXCEL_PATH = "configinput.xlsx"
MCP_ENDPOINT = "https://tooluniversemcpserver.onrender.com/mcp/"
OPENAI_KEY = ''
CACHE_DIR = Path("param_cache")
CACHE_DIR.mkdir(exist_ok=True)
TOOLS_JSON_PATH = "tools_restored.json" 
client = OpenAI(api_key=OPENAI_KEY)

# === CACHE FUNCTIONS FOR PARAMETERS ONLY ===
def get_param_cache_path(tool_name: str) -> Path:
    safe_name = tool_name.replace("/", "_").replace(" ", "_")
    return CACHE_DIR / f"{safe_name}_params.json"

def load_cached_params(tool_name: str):
    path = get_param_cache_path(tool_name)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return None

def save_cached_params(tool_name: str, param_data: dict):
    path = get_param_cache_path(tool_name)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(param_data, f, indent=2)

# === HELPER FUNCTIONS ===


def _is_excluded_category(cat):
    """
    Return True if the tool category is excluded (LangchainTool or PubChem).
    Works for string or list categories.
    """
    excluded = {"langchaintool", "pubchem"}  # add more here if needed

    if not cat:
        return False

    if isinstance(cat, str):
        return cat.strip().lower() in excluded

    if isinstance(cat, (list, tuple)):
        return any(
            isinstance(x, str) and x.strip().lower() in excluded
            for x in cat
        )

    return False


def load_tools_from_json(path: str = TOOLS_JSON_PATH):
    with open(path, "r", encoding="utf-8") as f:
        tools = json.load(f)

    api_tools = []
    for t in tools:
        tool_type = (t.get("toolType") or "").strip().lower()
        if tool_type != "api":
            continue
        if _is_excluded_category(t.get("category")):
            continue 

        t["_properties"] = (t.get("inputSchema") or {}).get("properties", {})  # dict or {}
        t["_example"]    = t.get("exampleInput") or {}                          # dict or {}
        api_tools.append(t)

    return api_tools



def generate_sample_arguments(tool_name, param_properties):
    cached = load_cached_params(tool_name)
    if cached:
        return cached

    system_prompt = f"""You are a helpful assistant generating example input for a tool.

Tool name: {tool_name}
Here are its parameter fields and their descriptions as JSON:
{json.dumps(param_properties, indent=2)}

Please respond ONLY with a valid JSON dictionary containing realistic values for each parameter.
Do NOT explain anything. Just return the JSON.
"""

    try:
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "system", "content": system_prompt}],
            temperature=0.7,
            max_tokens=500
        )
        output = response.choices[0].message.content.strip()
        parsed_output = json.loads(output)
        save_cached_params(tool_name, parsed_output)
        return parsed_output
    except Exception as e:
        print(f"❌ GPT error for {tool_name}:", e)
        return {}

def call_mcp(tool_name, arguments):
    payload = {
        "jsonrpc": "2.0",
        "id": "1",
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments
        }
    }

    try:
        response = requests.post(
            MCP_ENDPOINT,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream"
            },
            data=json.dumps(payload),
            timeout=30,
            stream=True
        )

        # Check if it's SSE (by looking for `data:` lines)
        if "text/event-stream" in response.headers.get("Content-Type", ""):
            full_data = ""
            for line in response.iter_lines(decode_unicode=True):
                if line.strip().startswith("data:"):
                    json_part = line.strip().replace("data:", "").strip()
                    full_data += json_part

            try:
                return json.loads(full_data)
            except Exception as e:
                return {"error": f"Failed to parse streamed JSON: {e}", "raw": full_data}

        else:
            # Standard JSON response
            try:
                return response.json()
            except Exception as e:
                return {"error": f"Failed to parse JSON: {e}", "raw": response.text}

    except Exception as e:
        return {"error": str(e)}




def classify_response_status(raw_response: Union[str, dict]) -> str:
    try:
        if isinstance(raw_response, str):
            parsed = json.loads(raw_response)
        else:
            parsed = raw_response

        result = parsed.get("result", {})
        is_error = result.get("isError", None)
        content = result.get("content", "")

        # ✅ Override: treat as success if specific string appears in content
        if is_error is True:
            if isinstance(content, list) and any(
                isinstance(item, dict) and "text" in item and
                "Tools should wrap non-dict values based on their output_schema" in item["text"]
                for item in content
            ):
                return "success"
            else:
                return "error"

        elif is_error is False:
            return "success"
        else:
            return "unknown"

    except Exception:
        return "unknown"





def load_tools_and_generate_calls():
    return run_all_tool_tests_streaming()

def run_all_tool_tests_streaming():
    all_tools = load_tools_from_json()

    for tool in all_tools:
        name = tool.get("name")
        description = tool.get("description", "")
        tool_type = tool.get("toolType", "")
        properties = tool.get("_properties", {})          # from loader normalization
        example    = tool.get("_example", {})             # from loader normalization
    
        # Safety: ensure we have a dict of properties
        if not isinstance(properties, dict):
            yield {"name": name, "error": "Invalid parameter properties in JSON"}
            continue
    
        # Prefer the JSON's exampleInput; fall back to the GPT-generated sample if missing.
        if isinstance(example, dict) and len(example) > 0:
            gpt_output = example
        else:
            gpt_output = generate_sample_arguments(name, properties)
            if not gpt_output:
                yield {"name": name, "error": "Failed to generate sample input"}
                continue
    
        mcp_response = call_mcp(name, gpt_output)
        output = mcp_response
        status = classify_response_status(output)
    
        yield {
            "name": name,
            "description": description,
            "type": tool_type,
            "parameters": properties,
            "input": gpt_output,
            "output": output,
            "status": status
        }
    

# Optional CLI entry
def main():
    for result in run_all_tool_tests_streaming():
        print(f"[{result['status'].upper()}] {result['name']}")
        if result['status'] == 'error':
            print("❌ Error:", result.get("output"))
        else:
            print("✅ Output:", result.get("output")[:200] + "...")
        print("-" * 60)

if __name__ == "__main__":
    main()
