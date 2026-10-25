"""
OpsIQ Model Context Protocol (MCP) Auto-Installer & Health Check
Automatically configures Claude Desktop and Cursor IDE to connect to OpsIQ.
Preserves existing MCP servers in your Claude Desktop configuration.
"""

import json
import os
import platform
import subprocess
import sys
from pathlib import Path


def get_claude_desktop_config_path() -> Path:
    system = platform.system()
    if system == "Windows":
        appdata = os.environ.get("APPDATA", "")
        if not appdata:
            appdata = str(Path.home() / "AppData" / "Roaming")
        return Path(appdata) / "Claude" / "claude_desktop_config.json"
    elif system == "Darwin":  # macOS
        return Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    else:  # Linux
        return Path.home() / ".config" / "Claude" / "claude_desktop_config.json"


def get_project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def get_python_executable(project_root: Path) -> str:
    # Check project-local virtual environment first
    if platform.system() == "Windows":
        venv_py = project_root / ".venv" / "Scripts" / "python.exe"
    else:
        venv_py = project_root / ".venv" / "bin" / "python"

    if venv_py.exists():
        return str(venv_py)
    return sys.executable


def build_opsiq_mcp_entry(project_root: Path, python_exe: str) -> dict:
    return {
        "command": python_exe,
        "args": ["-m", "ecommerce_ops.mcp.cli"],
        "env": {
            "PYTHONPATH": str(project_root),
            "API_KEY": "opsiq-dev-key-2024",
            "ENV": "development",
            "DATABASE_URL": f"sqlite+aiosqlite:///{project_root.as_posix()}/opsiq_dev.db",
        },
    }


def update_json_config(file_path: Path, server_entry: dict) -> None:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    config = {}
    if file_path.exists():
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                config = json.load(f)
        except Exception as e:
            print(f"[!] Warning: Could not read existing {file_path}: {e}. Creating fresh config.")

    if "mcpServers" not in config:
        config["mcpServers"] = {}

    config["mcpServers"]["opsiq"] = server_entry

    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


def test_mcp_health(python_exe: str, project_root: Path) -> bool:
    print("[*] Running pre-flight MCP protocol diagnostic test...")
    init_req = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    tools_req = json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    input_payload = f"{init_req}\n{tools_req}\n"

    env = os.environ.copy()
    env["PYTHONPATH"] = str(project_root)

    try:
        proc = subprocess.run(
            [python_exe, "-m", "ecommerce_ops.mcp.cli"],
            input=input_payload,
            capture_output=True,
            text=True,
            timeout=25,
            cwd=str(project_root),
            env=env,
        )
        if proc.returncode == 0 or '{"jsonrpc": "2.0", "id": 1' in proc.stdout:
            for line in proc.stdout.splitlines():
                if '"tools":' in line:
                    print("    -> tools/list call successfully returned registered tools.")
                    return True
            print("    -> Handshake succeeded.")
            return True
        else:
            print(f"[!] Diagnostic failed with code {proc.returncode}:\n{proc.stderr}")
            return False
    except Exception as e:
        print(f"[!] Diagnostic check error: {e}")
        return False


def main():
    print("=" * 65)
    print("  OpsIQ Model Context Protocol (MCP) Installer for Claude & Cursor")
    print("=" * 65)

    project_root = get_project_root()
    python_exe = get_python_executable(project_root)
    mcp_entry = build_opsiq_mcp_entry(project_root, python_exe)

    # 1. Configure Claude Desktop
    claude_path = get_claude_desktop_config_path()
    print(f"\n[1/3] Configuring Claude Desktop...")
    print(f"      Path: {claude_path}")
    update_json_config(claude_path, mcp_entry)
    print("      Done. 'opsiq' added to Claude Desktop configuration.")

    # 2. Configure Cursor IDE (.cursor/mcp.json)
    cursor_path = project_root / ".cursor" / "mcp.json"
    print(f"\n[2/3] Configuring Cursor IDE...")
    print(f"      Path: {cursor_path}")
    update_json_config(cursor_path, mcp_entry)
    print("      Done. 'opsiq' added to Cursor project configuration.")

    # 3. Test MCP Server
    print(f"\n[3/3] Testing stdio pipe connection...")
    success = test_mcp_health(python_exe, project_root)

    print("\n" + "=" * 65)
    if success:
        print("  SUCCESS! OpsIQ MCP Server is live and fully configured.")
        print("  - Restart Claude Desktop or open Cursor Composer.")
        print("  - You can now prompt Claude with:")
        print("    * 'Assess order #1089 for fraud risk and hold warehouse fulfillment.'")
        print("    * 'Audit our Meta ad spend against out-of-stock Shopify inventory.'")
        print("    * 'Analyze customer return for sizing fit and propose up-exchange.'")
    else:
        print("  Setup completed, but self-test encountered an issue. See logs above.")
    print("=" * 65 + "\n")


if __name__ == "__main__":
    main()
