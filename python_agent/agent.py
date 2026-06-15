import os
import io
import json
import base64
import time
import psutil
import requests
from typing import TypedDict, Optional, Union, List

# Load environment variables if dotenv is installed
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Try importing Pillow
try:
    from PIL import Image
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False
    print("Warning: 'Pillow' module not found. Image encoding will use fallbacks.")

# Mock LangGraph if not installed in the current environment
try:
    from langgraph.graph import StateGraph, START, END
    HAS_LANGGRAPH = True
except ImportError:
    HAS_LANGGRAPH = False
    print("Warning: 'langgraph' module not found. Using custom state graph simulation.")
    START = "__start__"
    END = "__end__"

# Try importing OpenAI
try:
    from openai import OpenAI
    HAS_OPENAI = True
except ImportError:
    HAS_OPENAI = False
    print("Warning: 'openai' module not found. Using dry-run mode for decisions.")

# Supermemory API Configuration
SUPERMEMORY_API_KEY = os.environ.get("SUPERMEMORY_API_KEY", "")
SUPERMEMORY_API_URL = "https://api.supermemory.ai/v4"

# Try to import our compiled Rust core (available after running maturin develop/build)
try:
    import rust_core
except ImportError:
    print("Warning: 'rust_core' module not found. Build the Rust extension using Maturin to run natively.")
    # Fallback mock to allow the script to execute for testing
    class MockRustCore:
        @staticmethod
        def move_mouse_to(x: int, y: int):
            print(f"[Mock Rust Core] Moving mouse to ({x}, {y})")
        @staticmethod
        def click_mouse():
            print("[Mock Rust Core] Simulating left click")
        @staticmethod
        def type_text(text: str):
            print(f"[Mock Rust Core] Simulating typing: '{text}'")
        @staticmethod
        def press_key(key_name: str):
            print(f"[Mock Rust Core] Simulating pressing key: '{key_name}'")
        @staticmethod
        def capture_screen():
            print("[Mock Rust Core] Simulating screen capture (1920x1080)")
            # 1920 * 1080 * 4 bytes of mock RGBA/BGRA pixels
            return (1920, 1080, b'\x00' * (1920 * 1080 * 4))
    rust_core = MockRustCore()

class RPAState(dict):
    objective: str
    screenshot_data: Optional[tuple]
    fs_state: str
    process_state: str
    memory_context: str
    last_command_result: Optional[str]
    next_action: Optional[str]
    final_response: Optional[str]
    completed: bool
    history: List[str]

# Helper to convert raw BGRA pixels to base64 encoded JPEG
def convert_bgra_to_base64_jpeg(width: int, height: int, raw_bgra: bytes) -> str:
    if not HAS_PILLOW:
        # Fallback empty 1x1 black pixel base64 GIF string if Pillow is missing
        return "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"
        
    try:
        # Load raw BGRA pixels using PIL raw decoder
        img = Image.frombytes("RGBA", (width, height), raw_bgra, "raw", "BGRA")
        # Convert to RGB (required for JPEG format)
        rgb_img = img.convert("RGB")
        # Save to memory buffer
        buffer = io.BytesIO()
        rgb_img.save(buffer, format="JPEG", quality=65, optimize=True)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")
    except Exception as e:
        print(f"Error converting screen image: {e}")
        return "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"

# Node 1: Capture screen using the Rust core extension
def capture_screen_node(state: RPAState) -> dict:
    print("\n--- Node: Capture Screen & Context ---")
    
    # Gather FS context
    try:
        fs_state = "Current Directory Contents:\n" + "\n".join(os.listdir("."))
    except Exception as e:
        fs_state = f"Failed to read directory: {e}"
        
    # Gather Process context
    try:
        procs = []
        for p in psutil.process_iter(['pid', 'name', 'cpu_percent']):
            try:
                procs.append(p.info)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        procs.sort(key=lambda x: x.get('cpu_percent', 0) or 0, reverse=True)
        top_procs = [f"PID {p['pid']}: {p['name']}" for p in procs[:10]]
        process_state = "Top Active Processes:\n" + "\n".join(top_procs)
    except Exception as e:
        process_state = f"Failed to read processes: {e}"

    try:
        width, height, raw_pixels = rust_core.capture_screen()
        print(f"[Rust Core Success] Captured display: {width}x{height} (Buffer size: {len(raw_pixels)} bytes)")
        return {"screenshot_data": (width, height, raw_pixels), "fs_state": fs_state, "process_state": process_state}
    except Exception as e:
        print(f"[Rust Core Error] Screen capture failed: {e}")
        return {"screenshot_data": (1920, 1080, b''), "fs_state": fs_state, "process_state": process_state}

def query_supermemory(query: str) -> str:
    if not SUPERMEMORY_API_KEY:
        return ""
    try:
        headers = {"Authorization": f"Bearer {SUPERMEMORY_API_KEY}", "Content-Type": "application/json"}
        payload = {"q": query, "searchMode": "hybrid", "limit": 3, "containerTag": "rpa_agent_memory"}
        resp = requests.post(f"{SUPERMEMORY_API_URL}/search", headers=headers, json=payload, timeout=10)
        if resp.status_code == 200:
            results = resp.json().get("results", [])
            context_list = []
            for r in results:
                content = r.get("memory") or r.get("chunk")
                if content:
                    context_list.append(str(content))
            return "\n---\n".join(context_list)
        return ""
    except Exception as e:
        print(f"[Supermemory Warning] Search failed: {e}")
        return ""

def save_to_supermemory(title: str, content: str):
    if not SUPERMEMORY_API_KEY:
        return
    try:
        headers = {"Authorization": f"Bearer {SUPERMEMORY_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "memories": [
                {
                    "content": f"{title}\n\n{content}",
                    "metadata": {
                        "source": "RPA_Agent"
                    }
                }
            ],
            "containerTag": "rpa_agent_memory"
        }
        resp = requests.post(f"{SUPERMEMORY_API_URL}/memories", headers=headers, json=payload, timeout=10)
        if resp.status_code not in (200, 201):
            print(f"[Supermemory Warning] Failed to save memory: HTTP {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"[Supermemory Warning] Save failed: {e}")

def query_memory_node(state: RPAState) -> dict:
    print("\n--- Node: Query Supermemory ---")
    objective = state.get("objective", "")
    history = state.get("history", [])
    
    # We query for the objective, and if we are repeatedly failing, we query the last action.
    query = f"Task: {objective}"
    if history:
        query += f" Recent action: {history[-1]}"
        
    memory_context = query_supermemory(query)
    if memory_context:
        print("[Supermemory] Found relevant past context!")
    else:
        print("[Supermemory] No prior context found.")
    
    return {"memory_context": memory_context}

# Node 2: Analyze screenshot and determine action using Hugging Face (Gemma 4)
def analyze_screen_node(state: RPAState) -> dict:
    print("\n--- Node: Analyze Screen & Decide ---")
    objective = state.get("objective", "")
    print(f"Goal: {objective}")
    
    screenshot = state.get("screenshot_data")
    if not screenshot:
        print("[Warning] No screenshot data available. Waiting...")
        return {"next_action": '{"action": "wait", "reason": "No screenshot"}'}
        
    width, height, raw_pixels = screenshot
    if isinstance(raw_pixels, list):
        raw_pixels = bytes(raw_pixels)
    base64_image = convert_bgra_to_base64_jpeg(width, height, raw_pixels)
    
    api_key = os.environ.get("HF_TOKEN")
    if not HAS_OPENAI or not api_key:
        print("[Simulation Mode] OpenAI API client or HF_TOKEN missing. Simulating steps...")
        # Simulate a sequence of steps for testing
        history = state.get("history", [])
        step = len(history)
        
        if step == 0:
            action = {"action": "click", "reason": "Locate and click the search box", "x": 500, "y": 200}
        elif step == 1:
            action = {"action": "type", "reason": "Search for system settings", "text": "System Settings"}
        elif step == 2:
            action = {"action": "press", "reason": "Press Enter to submit search", "key": "enter"}
        else:
            action = {"action": "done", "reason": "Target screen reached, objective complete"}
            
        action_json = json.dumps(action)
        return {"next_action": action_json}
        
    # Real API client call
    print(f"Connecting to Hugging Face API (Model: google/gemma-4-31B-it:novita)...")
    client = OpenAI(
        base_url="https://router.huggingface.co/v1",
        api_key=api_key,
    )
    
    history = state.get("history", [])
    recent_history = history[-5:]
    history_str = "\n".join([f"- {step}" for step in recent_history])
    if not history_str:
        history_str = "None (this is the first step)"

    prompt = f"""You are a cross-platform OS-level Agentic RPA system.
Your current objective is: "{objective}"

Based on the attached screen capture, determine the next logical action to achieve this objective.
The screen resolution is {width}x{height}. 

SYSTEM CONTEXT:
{state.get('fs_state', 'No FS state')}
{state.get('process_state', 'No process state')}

LAST BACKGROUND TERMINAL OUTPUT:
{state.get('last_command_result', 'No previous command output')}

SUPERMEMORY PAST KNOWLEDGE (Past errors or successful runs):
{state.get('memory_context', 'No relevant past memory found.')}

PREVIOUS ACTIONS YOU HAVE ALREADY TAKEN (Last 5 steps):
{history_str}
If you see that you already executed a command to open an app or typed text, DO NOT repeat it immediately even if the screen hasn't fully updated. Instead, output a "wait" action or proceed to the next logical step.

CRITICAL BEHAVIOR RULES:
1. APP LAUNCHING: DO NOT try to click taskbar icons, start menus, or desktop shortcuts to open applications. If the required application is not currently open and visible, you MUST use the "command" action to launch it via an OS-level terminal command. For example, to open a search engine or web page on Windows, output a "command" action with `start chrome "https://url.com"`.
2. VISION CONFIRMATION: Once an application is open, use the vision model to confirm the correct tab or window is visible before proceeding.
3. IN-APP INTERACTION: ONLY use "click", "type", and "press" actions to interact with elements *inside* an application after it has been opened.
4. BACKGROUND EXECUTION: "command" and "python_tool" run entirely in the background. Their output will appear in the LAST BACKGROUND TERMINAL OUTPUT section on the next turn. Do NOT open visible cmd.exe or terminal windows just to see output.
5. FILE SAVING: If your objective requires you to create, save, or download a file, you MUST save it into a folder named `results` located in the current working directory. Always prepend `results\\` or `results/` to the filename when typing it into a save dialog or command.
6. TOOL USE (BASH vs PYTHON): You can dynamically choose to execute raw OS terminal commands using the "command" action, or execute Python automation scripts using the "python_tool" action. If you need to perform complex data manipulation, file processing, or API calls, use "python_tool". For simple OS integrations (launching apps, moving files), use "command".
7. LEVERAGE SUPERMEMORY: If the SUPERMEMORY PAST KNOWLEDGE section contains a past successful run for a similar task, you MUST prioritize using the exact commands or steps that were successful previously, rather than starting from scratch or re-inventing the solution.

You MUST respond ONLY with a raw JSON block in this exact format (no markdown code blocks, no ```json wrapper):
{{
  "action": "click" | "type" | "press" | "wait" | "command" | "python_tool" | "save_file" | "done",
  "reason": "Brief explanation of what this action does and why you chose it",
  "x": <integer x coordinate, required if action is click>,
  "y": <integer y coordinate, required if action is click>,
  "text": "<string to type if action is type, or final summary message for the user if action is done>",
  "key": "enter" | "escape" | "tab" | "backspace" | "space" <required if action is press>,
  "command": "<terminal/os command to run, required if action is command>",
  "python_code": "<raw python code to execute via exec(), required if action is python_tool>",
  "filename": "<relative path starting with results/, required if action is save_file>",
  "content": "<the full string content to write, required if action is save_file>"
}}

Notes:
- Output only the raw JSON string. Do not output any surrounding text, explanations, or code formatting marks."""

    try:
        response = client.chat.completions.create(
            model="google/gemma-4-31B-it:novita",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            temperature=0.1,
            max_tokens=2048
        )
        
        result_text = response.choices[0].message.content.strip()
        print(f"Model Raw Output:\n{result_text}")
        
        # Strip markdown ```json ... ``` formatting if the model ignored instructions and added it anyway
        cleaned_text = result_text
        if "```" in result_text:
            import re
            match = re.search(r'```(?:json)?\s*(.*?)\s*```', result_text, re.DOTALL)
            if match:
                cleaned_text = match.group(1).strip()
                
        return {"next_action": cleaned_text}
    except Exception as e:
        print(f"[API Error] Request failed: {e}")
        return {"next_action": '{"action": "wait", "reason": "API request failed"}'}

# Node 3: Execute the action via Rust core input simulation
def execute_action_node(state: RPAState) -> dict:
    print("\n--- Node: Execute Action ---")
    action_str = state.get("next_action", "")
    print(f"Executing JSON Action: {action_str}")
    
    completed = False
    action_type = "unknown"
    command_result = None
    final_msg = None
    
    try:
        action_data = json.loads(action_str)
        action_type = action_data.get("action", "").lower()
        reason = action_data.get("reason", "")
        if reason:
            print(f"AI Decision Reason: {reason}")
            
        if action_type == "click":
            x = int(action_data.get("x", 0))
            y = int(action_data.get("y", 0))
            print(f"Executing: Mouse click at ({x}, {y})")
            rust_core.move_mouse_to(x, y)
            time.sleep(0.1)  # Allow hover state to register (fast)
            rust_core.click_mouse()
            time.sleep(0.1)  # Allow UI to react before next screenshot
        elif action_type == "type":
            text = action_data.get("text", "")
            print(f"Executing: Typing text: '{text}'")
            rust_core.type_text(text)
            time.sleep(0.1)  # Fast typed state
        elif action_type == "press":
            key = action_data.get("key", "")
            print(f"Executing: Pressing key: '{key}'")
            rust_core.press_key(key)
            time.sleep(0.1)  # Fast key press state
        elif action_type == "command":
            cmd = action_data.get("command", "")
            print(f"Executing OS Command: '{cmd}'")
            import subprocess
            try:
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=30)
                print(f"Command Output:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")
                command_result = f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
            except Exception as e:
                print(f"Command execution failed: {e}")
                command_result = f"Command execution failed: {e}"
        elif action_type == "python_tool":
            code = action_data.get("python_code", "")
            print(f"Executing Custom Python Script:\n{code}")
            try:
                import sys
                from io import StringIO
                old_stdout = sys.stdout
                sys.stdout = mystdout = StringIO()
                exec(code, globals())
                sys.stdout = old_stdout
                output_val = mystdout.getvalue()
                print(f"Python Output:\n{output_val}")
                command_result = f"Python Output:\n{output_val}"
            except Exception as e:
                import sys
                sys.stdout = old_stdout
                print(f"Python execution failed: {e}")
                command_result = f"Python execution failed: {e}"
        elif action_type == "save_file":
            filename = action_data.get("filename", "results/output.txt")
            content = action_data.get("content", "")
            print(f"Executing: Saving file to '{filename}'")
            try:
                # Ensure it goes into the results folder if AI forgot
                if not filename.startswith("results") and not filename.startswith("results\\") and not filename.startswith("results/"):
                    filename = os.path.join("results", os.path.basename(filename))
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(content)
                print("File saved successfully.")
            except Exception as e:
                print(f"Failed to save file: {e}")
        elif action_type == "wait":
            print("Executing: Waiting 2 seconds...")
            time.sleep(2)
        elif action_type == "done":
            print("Objective successfully accomplished according to the AI model.")
            completed = True
            # Capture final message if provided
            final_msg = action_data.get("text", "") or action_data.get("reason", "")
            if final_msg:
                print(f"Final Message to User: {final_msg}")
        else:
            print(f"[Warning] Unknown action type: {action_type}")
    except Exception as e:
        error_msg = f"[Execution Error] Failed to parse or execute action: {e}"
        print(error_msg)
        # Save error to Supermemory
        objective = state.get("objective", "")
        error_content = f"Objective: {objective}\nAction Attempted: {action_str}\nError Encountered: {e}\nHow to fix: (To be learned)"
        save_to_supermemory(f"Error in RPA: {action_type}", error_content)
        
    # Append this action to history
    history = state.get("history", [])
    new_history = history.copy()
    compact_action = json.dumps(action_data) if action_type != "unknown" else action_str
    new_history.append(compact_action)
    
    return {"completed": completed, "history": new_history, "last_command_result": command_result, "final_response": final_msg}

# Conditional edge logic to run the loop
def should_continue(state: RPAState):
    if state.get("completed", False):
        print("\n=== Goal Completed: Stopping workflow ===")
        return END
        
    history = state.get("history", [])
    if len(history) >= 50:
        print("\n=== Loop Limit Reached: Terminating to prevent infinite loops ===")
        return END
        
    print("\nLooping back to capture next frame...")
    return "capture_screen"

if HAS_LANGGRAPH:
    builder = StateGraph(RPAState)
    builder.add_node("capture_screen", capture_screen_node)
    builder.add_node("query_memory", query_memory_node)
    builder.add_node("analyze_screen", analyze_screen_node)
    builder.add_node("execute_action", execute_action_node)

    builder.add_edge(START, "capture_screen")
    builder.add_edge("capture_screen", "query_memory")
    builder.add_edge("query_memory", "analyze_screen")
    builder.add_edge("analyze_screen", "execute_action")
    builder.add_conditional_edges(
        "execute_action",
        should_continue,
        {
            "capture_screen": "capture_screen",
            END: END
        }
    )
    rpa_workflow = builder.compile()
else:
    # Custom state-machine simulator fallback
    class SimulationWorkflow:
        def invoke(self, state: dict) -> dict:
            # Inject history list
            if "history" not in state:
                state["history"] = []
            
            while len(state["history"]) < 50:
                # Run Node 1
                res1 = capture_screen_node(state)
                state.update(res1)
                
                # Run Node Query
                res_q = query_memory_node(state)
                state.update(res_q)
                
                # Run Node 2
                res2 = analyze_screen_node(state)
                state.update(res2)
                
                # Run Node 3
                res3 = execute_action_node(state)
                state.update(res3)
                
                # Check escape route
                next_step = should_continue(state)
                if next_step == END:
                    break
            return state
            
    rpa_workflow = SimulationWorkflow()

def get_coordinates_for_element(objective: str, target_reason: str, width: int, height: int, raw_pixels: bytes) -> dict:
    base64_image = convert_bgra_to_base64_jpeg(width, height, raw_pixels)
    api_key = os.environ.get("HF_TOKEN")
    if not HAS_OPENAI or not api_key:
        return {"x": 0, "y": 0}
        
    client = OpenAI(
        base_url="https://router.huggingface.co/v1",
        api_key=api_key,
    )
    
    prompt = f"""You are an RPA visual extraction module. 
The current overall objective is: "{objective}"
Your ONLY goal is to find the exact X and Y coordinates for the element described by this intent:
"{target_reason}"

The screen resolution is {width}x{height}.
Return ONLY a raw JSON block in this exact format:
{{
  "x": <integer x coordinate>,
  "y": <integer y coordinate>
}}
"""
    try:
        response = client.chat.completions.create(
            model="google/gemma-4-31B-it:novita",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            temperature=0.0,
            max_tokens=50
        )
        
        result_text = response.choices[0].message.content.strip()
        cleaned_text = result_text
        if "```" in result_text:
            import re
            match = re.search(r'```(?:json)?\s*(.*?)\s*```', result_text, re.DOTALL)
            if match:
                cleaned_text = match.group(1).strip()
                
        return json.loads(cleaned_text)
    except Exception as e:
        print(f"[API Error] Coordinate extraction failed: {e}")
        return {"x": 0, "y": 0}

def run_agent(objective: str):
    # Ensure a results directory exists for saved files
    os.makedirs("results", exist_ok=True)
    
    # We no longer rely on a local task_memory.json file.
    # Supermemory is now dynamically integrated into the decision node via RAG.
    
    print("=" * 60)
    print(f"Starting Hugging Face RPA Workflow with Objective: '{objective}'")
    print("=" * 60)
    
    initial_state = {
        "objective": objective,
        "screenshot_data": None,
        "next_action": None,
        "memory_context": "",
        "completed": False,
        "history": []
    }
    
    result = rpa_workflow.invoke(initial_state)
    print("\n" + "=" * 60)
    print(f"Workflow Complete! Steps executed: {len(result.get('history', []))}")
    print(f"Actions taken: {', '.join(result.get('history', []))}")
    print("=" * 60)

    if result.get("completed", False):
        try:
            valid_history = []
            for step in result.get("history", []):
                try:
                    json.loads(step)
                    valid_history.append(step)
                    from ui import show_result
                    show_result(step)
                except:
                    pass
                    
            history_str = "\n".join(valid_history)
            content = f"Objective successfully completed: {objective}\nSuccessful Steps:\n{history_str}"
            save_to_supermemory(f"Completed Task: {objective}", content)
            print("Successfully saved workflow sequence to Supermemory.")
        except Exception as e:
            print(f"Failed to save task memory to Supermemory: {e}")
            
    return result

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        objective = " ".join(sys.argv[1:])
        if objective.strip():
            run_agent(objective.strip())
        else:
            print("No objective provided. Exiting.")
    else:
        print("Starting Spotlight UI. Press Ctrl+Space to toggle.")
        try:
            from ui import run_ui
            run_ui()
        except ImportError as e:
            print(f"Error loading UI: {e}")
            objective = input("Enter the objective for the RPA agent: ")
            if objective.strip():
                run_agent(objective.strip())
