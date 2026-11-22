# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Async helper functions for web UI
"""

import asyncio
import tomllib
from pathlib import Path

from loguru import logger


def run_async(coro):
    """
    Run async coroutine in sync context
    
    Handles event loop properly for Streamlit environment:
    - If there's already a running event loop, use it
    - Otherwise, create a new one
    """
    try:
        # Try to get the current event loop
        loop = asyncio.get_running_loop()
        # If we're here, there's a running loop - we need to handle it differently
        # Use nest_asyncio if available, otherwise create a task
        try:
            import nest_asyncio
            nest_asyncio.apply()
            return asyncio.run(coro)
        except ImportError:
            # Fallback: create a new thread with a new event loop
            import concurrent.futures
            import threading
            
            def run_in_thread():
                new_loop = asyncio.new_event_loop()
                asyncio.set_event_loop(new_loop)
                try:
                    return new_loop.run_until_complete(coro)
                finally:
                    new_loop.close()
            
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(run_in_thread)
                return future.result()
    except RuntimeError:
        # No running event loop, safe to use asyncio.run()
        return asyncio.run(coro)


def get_project_version():
    """Get project version from pyproject.toml"""
    try:
        # Get project root (web parent directory)
        web_dir = Path(__file__).resolve().parent.parent
        project_root = web_dir.parent
        pyproject_path = project_root / "pyproject.toml"
        
        if pyproject_path.exists():
            with open(pyproject_path, "rb") as f:
                pyproject_data = tomllib.load(f)
                return pyproject_data.get("project", {}).get("version", "Unknown")
    except Exception as e:
        logger.warning(f"Failed to read version from pyproject.toml: {e}")
    return "Unknown"

