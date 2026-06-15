import threading
import customtkinter as ctk
from pynput import keyboard
from agent import run_agent
import sys
import os

class RPAUI:
    def __init__(self):
        # Set up appearance
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")
        
        self.root = ctk.CTk()
        self.root.title("RPA Agent UI")
        
        # Dimensions
        window_width = 800
        window_height = 100
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        x = (screen_width // 2) - (window_width // 2)
        # Position slightly above center like Spotlight
        y = (screen_height // 3) - (window_height // 2)
        
        self.root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        self.root.overrideredirect(True) # Frameless Spotlight style
        self.root.attributes("-topmost", True)
        
        # Border frame to make it look nicer
        self.frame = ctk.CTkFrame(self.root, corner_radius=15, border_width=2, border_color="#3b3b3b")
        self.frame.pack(fill="both", expand=True)
        
        # Input Element
        self.entry = ctk.CTkEntry(
            self.frame, 
            width=760, 
            height=60, 
            font=("Segoe UI", 24), 
            placeholder_text="Enter your objective (Ctrl+Space to hide/show)...",
            fg_color="transparent",
            border_width=0
        )
        self.entry.pack(padx=20, pady=(20, 10))
        self.entry.bind("<Return>", self.on_enter)
        self.entry.bind("<Escape>", lambda e: self.hide_window())
        
        # Result Textbox (hidden initially)
        self.textbox = ctk.CTkTextbox(
            self.frame,
            width=760,
            height=300,
            font=("Segoe UI", 16),
            wrap="word",
            fg_color="transparent"
        )
        # We don't pack it yet
        
        # Initially visible
        self.is_visible = True
        self.entry.focus_force()
        
        # Start global hotkey listener
        self.listener = keyboard.GlobalHotKeys({
            '<ctrl>+<space>': self.on_hotkey
        })
        self.listener.start()
        
    def on_hotkey(self):
        # Thread-safe UI update
        self.root.after(0, self.toggle_visibility)
        
    def toggle_visibility(self):
        if self.is_visible:
            self.hide_window()
        else:
            self.show_window()
            
    def show_window(self):
        self.root.deiconify()
        self.root.attributes("-topmost", True)
        self.entry.focus_force()
        self.is_visible = True
        
    def hide_window(self):
        self.root.withdraw()
        self.is_visible = False
        # Reset window size and hide textbox for next run
        self.textbox.pack_forget()
        self.root.geometry(f"{800}x{100}")
        
    def show_result(self, message):
        # Update geometry to be taller
        self.root.geometry(f"{800}x{400}")
        self.textbox.pack(padx=20, pady=(0, 20), fill="both", expand=True)
        self.textbox.delete("0.0", "end")
        self.textbox.insert("0.0", message)
        self.show_window()
        
    def on_enter(self, event):
        objective = self.entry.get().strip()
        if objective:
            self.entry.delete(0, 'end')
            self.hide_window()
            print(f"\n[UI] Starting agent with objective: {objective}")
            
            # Change directory to the script's directory so results/ logic works
            script_dir = os.path.dirname(os.path.abspath(__file__))
            os.chdir(script_dir)
            
            # Wrapper to run agent and capture result
            def _run_and_show():
                result_state = run_agent(objective)
                if result_state:
                    final_msg = result_state.get("final_response")
                    if not final_msg:
                        final_msg = "Task completed successfully (No specific summary provided)."
                else:
                    final_msg = "Task failed or was interrupted."
                
                # Thread-safe UI update
                self.root.after(0, lambda: self.show_result(final_msg))

            # Run agent in background thread to avoid freezing UI
            # Daemon=True so it closes if the main window closes
            threading.Thread(target=_run_and_show, daemon=True).start()

def run_ui():
    try:
        app = RPAUI()
        app.root.mainloop()
    except KeyboardInterrupt:
        sys.exit(0)

if __name__ == "__main__":
    run_ui()
