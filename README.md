# Cross-Platform Agentic RPA System

A state-of-the-art, cross-platform OS-level Agentic Robotic Process Automation (RPA) system. This workspace integrates a high-performance **Rust Core** for OS-level control (mouse, keyboard, screen capture) with a flexible **Python Agent** driven by **LangGraph** and **Gemini**.

---

## Architecture Overview

```mermaid
graph TD
    subgraph Python Agent (Orchestration)
        LG[LangGraph State Machine] --> |Decision / Vision| AI[Gemini 2.5 API]
        LG --> |Commands| RC_Py[rust_core Python Binding]
    end

    subgraph Rust Core (Engine)
        RC_Py --> |PyO3 Bindings| RustLib[rust_core C-Dynamic Library]
        RustLib --> |Simulates OS Input| Enigo[Enigo Crate]
        RustLib --> |Captures Display| Scrap[Scrap Crate]
    end

    subgraph Operating System
        Enigo --> |Mouse / Keyboard events| OS[OS APIs: Win32 / CoreGraphics]
        OS --> |Screen Frame Buffer| Scrap
    end

    style Python Agent fill:#2c3e50,stroke:#34495e,stroke-width:2px,color:#fff
    style Rust Core fill:#d35400,stroke:#e67e22,stroke-width:2px,color:#fff
    style Operating System fill:#7f8c8d,stroke:#95a5a6,stroke-width:2px,color:#fff
```

---

## Directory Structure

```text
├── .devcontainer/
│   └── devcontainer.json   # Setup for unified Python 3.12 & Rust dev environment
├── .gitattributes          # Ensures LF-only line endings across Windows and macOS
├── rust_core/
│   ├── Cargo.toml          # Cargo package definition (pyo3, enigo, scrap dependencies)
│   └── src/
│       └── lib.rs          # PyO3 bindings for OS-level mouse and capture operations
├── python_agent/
│   ├── pyproject.toml      # UV / PEP 621 compliant configuration for agent
│   └── agent.py            # LangGraph RPA workflow linking AI and Rust core
└── README.md               # Getting started & compilation instructions (this file)
```

---

## Getting Started

Follow these instructions to set up, compile, and run the project on your machine (compatible with Windows and macOS).

### 1. Prerequisites

Make sure you have the following installed on your host system or use the provided **Devcontainer** environment:
* [Rust & Cargo](https://rustup.rs/) (edition 2021)
* [Python 3.12](https://www.python.org/downloads/)
* **For Windows**: C++ Build Tools (installed automatically with Visual Studio or Rustup installer).
* **For macOS**: Xcode Command Line Tools (`xcode-select --install`).

---

### 2. Compilation and Setup (Using `maturin`)

`maturin` is used to compile the Rust project into a Python extension module. Follow these exact steps:

#### Step A: Set up a Python Virtual Environment
Navigate to the `python_agent` directory and create/activate a virtual environment:

##### Option 1: Using `uv` (Recommended)
```bash
# Install uv if you don't have it
pip install uv

# Navigate to python_agent
cd python_agent

# Create virtual environment and install dependencies
uv venv
source .venv/bin/activate      # On macOS/Linux
.venv\Scripts\activate         # On Windows (PowerShell)

# Sync/install requirements
uv pip install -e .
```

##### Option 2: Using standard `venv`
```bash
# Navigate to python_agent
cd python_agent

# Create virtual environment
python -m venv .venv

# Activate virtual environment
source .venv/bin/activate      # On macOS/Linux
.venv\Scripts\activate         # On Windows (PowerShell)

# Install Python requirements
pip install -e .
```

#### Step B: Install `maturin` inside the Virtual Environment
Ensure `maturin` is installed in your active Python environment:
```bash
pip install maturin
```

#### Step C: Compile Rust into Python
While inside your active virtual environment, navigate to the `rust_core` directory to build the library:

```bash
# Navigate to rust_core
cd ../rust_core

# Compile and inject the Rust module directly into your Python site-packages
maturin develop
```

> [!NOTE]
> `maturin develop` compiles the Rust module in debug mode (faster compilation) and makes it immediately importable in your active virtual environment as `import rust_core`.
>
> To compile a release build optimized for performance, run:
> ```bash
> maturin develop --release
> ```

---

### 3. Running the Agent

With the Rust extension successfully compiled into the virtual environment, you can now run the Python LangGraph RPA Agent.

```bash
# Navigate back to python_agent
cd ../python_agent

# Run the agent
python agent.py
```

---

### 4. Production Packaging

To compile a production-ready package (a `.whl` Wheel file) to distribute to other developers or servers:

```bash
cd rust_core
maturin build --release
```
The compiled wheel file will be saved in the `rust_core/target/wheels/` directory, ready to be installed via `pip install <wheel_name>.whl`.

---

## OS-Specific Permissions

Since this project simulates inputs and captures the screen, you may need to grant permissions:
* **macOS**: When running `python agent.py` for the first time, you must grant **Accessibility** and **Screen Recording** permissions to the terminal or code editor executing the command (under *System Settings -> Privacy & Security*).
* **Windows**: Depending on permissions of target applications, you may need to run your terminal as Administrator for `enigo` to interact with elevated UI windows.
# RPA
