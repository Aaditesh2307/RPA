import os
import io
import json
import base64
import time
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

# Try importing Groq
try:
    from groq import Groq
    HAS_GROQ = True
except ImportError:
    HAS_GROQ = False
    print("Warning: 'groq' module not found. Using dry-run mode for decisions.")

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

# Define the state shape for the RPA graph
class RPAState(dict):
    objective: str
    screenshot_data: Optional[tuple]
    next_action: Optional[str]
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
        rgb_img.save(buffer, format="JPEG", quality=80)
        return base64.b64encode(buffer.getvalue()).decode("utf-8")
    except Exception as e:
        print(f"Error converting screen image: {e}")
        return "R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7"

# Node 1: Capture screen using the Rust core extension
def capture_screen_node(state: RPAState) -> dict:
    print("\n--- Node: Capture Screen ---")
    try:
        width, height, raw_pixels = rust_core.capture_screen()
        print(f"[Rust Core Success] Captured display: {width}x{height} (Buffer size: {len(raw_pixels)} bytes)")
        return {"screenshot_data": (width, height, raw_pixels)}
    except Exception as e:
        print(f"[Rust Core Error] Screen capture failed: {e}")
        return {"screenshot_data": (1920, 1080, b'')}

# Node 2: Analyze screenshot and determine action using Groq (Llama 3.2 Vision)
def analyze_screen_node(state: RPAState) -> dict:
    print("\n--- Node: Analyze Screen & Decide ---")
    objective = state.get("objective", "")
    print(f"Goal: {objective}")
    
    screenshot = state.get("screenshot_data")
    if not screenshot:
        print("[Warning] No screenshot data available. Waiting...")
        return {"next_action": '{"action": "wait", "reason": "No screenshot"}'}
        
    width, height, raw_pixels = screenshot
    base64_image = convert_bgra_to_base64_jpeg(width, height, raw_pixels)
    
    api_key = os.environ.get("GROQ_API_KEY")
    if not HAS_GROQ or not api_key:
        print("[Simulation Mode] Groq API client or GROQ_API_KEY missing. Simulating steps...")
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
        
    # Real Groq API client call
    print(f"Connecting to Groq API (Model: llama-3.2-11b-vision-preview)...")
    client = Groq(api_key=api_key)
    
    prompt = f"""You are a cross-platform OS-level Agentic RPA system.
Your current objective is: "{objective}"

Based on the attached screen capture, determine the next logical GUI action to achieve this objective.
The screen resolution is {width}x{height}. 

You MUST respond ONLY with a raw JSON block in this exact format (no markdown code blocks, no ```json wrapper):
{{
  "action": "click" | "type" | "press" | "wait" | "done",
  "reason": "Brief explanation of what this action does and why you chose it",
  "x": <integer x coordinate, required if action is click>,
  "y": <integer y coordinate, required if action is click>,
  "text": "<text string to type, required if action is type>",
  "key": "enter" | "escape" | "tab" | "backspace" | "space" <required if action is press>
}}

Notes:
- Output only the raw JSON string. Do not output any surrounding text, explanations, or code formatting marks."""

    try:
        response = client.chat.completions.create(
            model="llama-3.2-11b-vision-preview",
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
            max_tokens=256
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
        print(f"[Groq API Error] Request failed: {e}")
        return {"next_action": '{"action": "wait", "reason": "Groq request failed"}'}

# Node 3: Execute the action via Rust core input simulation
def execute_action_node(state: RPAState) -> dict:
    print("\n--- Node: Execute Action ---")
    action_str = state.get("next_action", "")
    print(f"Executing JSON Action: {action_str}")
    
    completed = False
    action_type = "unknown"
    
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
            rust_core.click_mouse()
        elif action_type == "type":
            text = action_data.get("text", "")
            print(f"Executing: Typing text: '{text}'")
            rust_core.type_text(text)
        elif action_type == "press":
            key = action_data.get("key", "")
            print(f"Executing: Pressing key: '{key}'")
            rust_core.press_key(key)
        elif action_type == "wait":
            print("Executing: Waiting 2 seconds...")
            time.sleep(2)
        elif action_type == "done":
            print("Objective successfully accomplished according to the AI model.")
            completed = True
        else:
            print(f"[Warning] Unknown action type: {action_type}")
    except Exception as e:
        print(f"[Execution Error] Failed to parse or execute action: {e}")
        
    # Append this action type to history
    history = state.get("history", [])
    new_history = history.copy()
    new_history.append(action_type)
    
    return {"completed": completed, "history": new_history}

# Conditional edge logic to run the loop
def should_continue(state: RPAState):
    if state.get("completed", False):
        print("\n=== Goal Completed: Stopping workflow ===")
        return END
        
    history = state.get("history", [])
    if len(history) >= 10:
        print("\n=== Loop Limit Reached: Terminating to prevent infinite loops ===")
        return END
        
    print("\nLooping back to capture next frame...")
    return "capture_screen"

# Build and compile the Graph
if HAS_LANGGRAPH:
    builder = StateGraph(RPAState)
    builder.add_node("capture_screen", capture_screen_node)
    builder.add_node("analyze_screen", analyze_screen_node)
    builder.add_node("execute_action", execute_action_node)

    builder.add_edge(START, "capture_screen")
    builder.add_edge("capture_screen", "analyze_screen")
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
            
            while len(state["history"]) < 10:
                # Run Node 1
                res1 = capture_screen_node(state)
                state.update(res1)
                
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

def run_agent(objective: str):
    print("=" * 60)
    print(f"Starting Groq RPA Workflow with Objective: '{objective}'")
    print("=" * 60)
    
    initial_state = {
        "objective": objective,
        "screenshot_data": None,
        "next_action": None,
        "completed": False,
        "history": []
    }
    
    result = rpa_workflow.invoke(initial_state)
    print("\n" + "=" * 60)
    print(f"Workflow Complete! Steps executed: {len(result.get('history', []))}")
    print(f"Actions taken: {', '.join(result.get('history', []))}")
    print("=" * 60)

if __name__ == "__main__":
    run_agent("Open the search engine, search for 'Groq API keys', and press enter.")
