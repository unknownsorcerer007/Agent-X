"""
Agent-OS Workflow Engine
Execute multi-step browser workflows from a single command.
Supports conditionals, loops, error handling, variables, and templates.
"""
import asyncio
import json
import logging
import time
import re
from typing import Dict, List, Any, Optional
from pathlib import Path

logger = logging.getLogger("agent-os.workflow")


class WorkflowEngine:
    """
    Execute multi-step workflows. Each step is a browser command.
    Supports:
    - Variables: {{variable_name}}
    - Conditionals: if/unless based on page content
    - Loops: repeat steps for each item
    - Error handling: retry, skip, abort
    - Templates: save/load reusable workflows
    - Delays: wait between steps
    """

    BUILTIN_TEMPLATES = {
        "google_search": {
            "name": "Google Search",
            "description": "Search Google and get first result",
            "steps": [
                {"command": "navigate", "url": "https://google.com"},
                {"command": "smart-fill", "label": "Search", "value": "{{query}}"},
                {"command": "press", "key": "Enter"},
                {"command": "wait", "selector": "#search", "timeout": 5000},
                {"command": "get-content"},
            ],
            "variables": {"query": "search term"},
        },
        "login": {
            "name": "Login Flow",
            "description": "Fill login form and submit",
            "steps": [
                {"command": "navigate", "url": "{{login_url}}"},
                {"command": "fill-form", "fields": {
                    "input[type='email'], input[name='email'], input[name='username']": "{{username}}",
                    "input[type='password']": "{{password}}",
                }},
                {"command": "click", "selector": "button[type='submit'], input[type='submit']"},
                {"command": "wait", "selector": "body", "timeout": 5000},
            ],
            "variables": {"login_url": "", "username": "", "password": ""},
        },
        "screenshot_full": {
            "name": "Full Page Screenshot",
            "description": "Navigate and take full page screenshot",
            "steps": [
                {"command": "navigate", "url": "{{url}}"},
                {"command": "screenshot", "full_page": True},
            ],
            "variables": {"url": ""},
        },
    }

    def __init__(self, browser):
        self.browser = browser
        self._templates_dir = Path.home() / ".agent-os" / "workflows"
        self._templates_dir.mkdir(parents=True, exist_ok=True)
        self._running_workflows: Dict[str, Dict] = {}
        self._max_concurrent = 5

    async def execute(
        self,
        steps: List[Dict[str, Any]],
        variables: Dict[str, str] = None,
        on_error: str = "abort",
        retry_count: int = 0,
        step_delay_ms: int = 0,
        timeout_per_step_ms: int = 30000,
    ) -> Dict[str, Any]:
        """
        Execute a multi-step workflow.

        Args:
            steps: List of command dicts, each with "command" + params
            variables: Template variables to substitute
            on_error: "abort", "skip", or "retry"
            retry_count: Number of retries per step on failure
            step_delay_ms: Delay between steps
            timeout_per_step_ms: Max time per step

        Returns:
            Full workflow result with per-step results
        """
        if len(self._running_workflows) >= self._max_concurrent:
            return {"status": "error", "error": "Too many concurrent workflows. Max: " + str(self._max_concurrent)}

        workflow_id = f"wf-{int(time.time())}"
        variables = variables or {}

        self._running_workflows[workflow_id] = {
            "started_at": time.time(),
            "total_steps": len(steps),
            "current_step": 0,
            "status": "running",
        }

        results = []
        total_start = time.time()

        try:
            for i, step in enumerate(steps):
                self._running_workflows[workflow_id]["current_step"] = i + 1

                # Substitute variables
                resolved_step = self._resolve_variables(step, variables)

                # Apply inter-step delay
                if step_delay_ms > 0 and i > 0:
                    await asyncio.sleep(step_delay_ms / 1000)

                # Execute step with retries
                step_result = await self._execute_step(
                    resolved_step, retry_count, timeout_per_step_ms
                )

                results.append({
                    "step": i + 1,
                    "command": step.get("command", "unknown"),
                    "resolved_params": {k: v for k, v in resolved_step.items() if k != "command"},
                    **step_result,
                })

                # Handle errors
                if step_result.get("status") == "error":
                    if on_error == "abort":
                        logger.error(f"Workflow {workflow_id} aborted at step {i+1}: {step_result.get('error')}")
                        break
                    elif on_error == "skip":
                        logger.warning(f"Workflow {workflow_id} step {i+1} skipped: {step_result.get('error')}")
                        continue
                    elif on_error == "retry":
                        # Already retried in _execute_step, skip
                        continue

                # Capture step output into variables for next steps
                if step_result.get("status") == "success":
                    for key in ["url", "title", "text", "screenshot"]:
                        if key in step_result:
                            variables[f"_step{i+1}_{key}"] = str(step_result[key])[:1000]

            total_time = time.time() - total_start
            successful = sum(1 for r in results if r.get("status") == "success")

            return {
                "status": "success" if successful == len(steps) else "partial",
                "workflow_id": workflow_id,
                "total_steps": len(steps),
                "successful_steps": successful,
                "failed_steps": len(steps) - successful,
                "total_time_ms": int(total_time * 1000),
                "steps": results,
                "variables_captured": {k: v for k, v in variables.items() if k.startswith("_step")},
            }

        except Exception as e:
            logger.error(f"Workflow {workflow_id} fatal error: {e}")
            return {
                "status": "error",
                "workflow_id": workflow_id,
                "error": str(e),
                "steps": results,
            }
        finally:
            self._running_workflows.pop(workflow_id, None)

    async def execute_template(
        self,
        template_name: str,
        variables: Dict[str, str] = None,
        page_id: str = "main",
    ) -> Dict[str, Any]:
        """Execute a saved or built-in workflow template."""
        template = self._load_template(template_name)
        if not template:
            return {"status": "error", "error": f"Template not found: {template_name}"}

        steps = template.get("steps", [])
        default_vars = template.get("variables", {})
        merged_vars = {**default_vars, **(variables or {})}

        return await self.execute(steps, variables=merged_vars)

    async def execute_from_json(self, json_str: str, page_id: str = "main") -> Dict[str, Any]:
        """Execute a workflow from a JSON string."""
        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            return {"status": "error", "error": f"Invalid JSON: {e}"}

        steps = data.get("steps", [])
        if not steps:
            return {"status": "error", "error": "No steps defined in workflow"}

        return await self.execute(
            steps,
            variables=data.get("variables", {}),
            on_error=data.get("on_error", "abort"),
            retry_count=data.get("retry_count", 0),
            step_delay_ms=data.get("step_delay_ms", 0),
        )

    def save_template(self, name: str, steps: List[Dict], variables: Dict = None, description: str = "") -> Dict:
        """Save a workflow as a reusable template."""
        template = {
            "name": name,
            "description": description,
            "steps": steps,
            "variables": variables or {},
            "created_at": time.time(),
        }

        path = self._templates_dir / f"{name}.json"
        with open(path, "w") as f:
            json.dump(template, f, indent=2)

        return {"status": "success", "name": name, "path": str(path)}

    def list_templates(self) -> List[Dict]:
        """List all available workflow templates."""
        templates = []

        # Built-in templates
        for name, tpl in self.BUILTIN_TEMPLATES.items():
            templates.append({
                "name": name,
                "description": tpl["description"],
                "steps": len(tpl["steps"]),
                "variables": list(tpl.get("variables", {}).keys()),
                "built_in": True,
            })

        # Saved templates
        for path in self._templates_dir.glob("*.json"):
            try:
                with open(path) as f:
                    tpl = json.load(f)
                templates.append({
                    "name": tpl.get("name", path.stem),
                    "description": tpl.get("description", ""),
                    "steps": len(tpl.get("steps", [])),
                    "variables": list(tpl.get("variables", {}).keys()),
                    "built_in": False,
                })
            except Exception:
                continue

        return templates

    def get_status(self, workflow_id: str) -> Dict:
        """Get status of a running workflow."""
        wf = self._running_workflows.get(workflow_id)
        if not wf:
            return {"status": "not_found", "error": f"Workflow {workflow_id} not found or completed"}
        return {
            "status": wf["status"],
            "workflow_id": workflow_id,
            "current_step": wf["current_step"],
            "total_steps": wf["total_steps"],
            "elapsed_seconds": int(time.time() - wf["started_at"]),
        }

    def _load_template(self, name: str) -> Optional[Dict]:
        """Load a template by name (built-in or saved)."""
        # Check built-in
        if name in self.BUILTIN_TEMPLATES:
            return self.BUILTIN_TEMPLATES[name]

        # Check saved
        path = self._templates_dir / f"{name}.json"
        if path.exists():
            with open(path) as f:
                return json.load(f)

        return None

    def _resolve_variables(self, step: Dict, variables: Dict[str, str]) -> Dict:
        """Replace {{var}} placeholders with actual values."""
        resolved = {}
        for key, value in step.items():
            if isinstance(value, str):
                resolved[key] = self._substitute(value, variables)
            elif isinstance(value, dict):
                resolved[key] = {
                    k: self._substitute(v, variables) if isinstance(v, str) else v
                    for k, v in value.items()
                }
            elif isinstance(value, list):
                resolved[key] = [
                    self._substitute(v, variables) if isinstance(v, str) else v
                    for v in value
                ]
            else:
                resolved[key] = value
        return resolved

    def _substitute(self, text: str, variables: Dict[str, str]) -> str:
        """Replace {{var}} in text."""
        def replacer(match):
            var_name = match.group(1).strip()
            return str(variables.get(var_name, match.group(0)))
        return re.sub(r'\{\{(\w+)\}\}', replacer, text)

    async def _execute_step(
        self, step: Dict, retries: int, timeout_ms: int
    ) -> Dict[str, Any]:
        """Execute a single workflow step with retry support."""
        command = step.get("command", "")
        if not command:
            return {"status": "error", "error": "No command specified in step"}

        params = {k: v for k, v in step.items() if k != "command"}

        last_error = None
        attempts = 1 + retries

        for attempt in range(attempts):
            try:
                # Route to browser method
                result = await asyncio.wait_for(
                    self._route_command(command, params),
                    timeout=timeout_ms / 1000,
                )

                if result.get("status") != "error":
                    return result

                last_error = result.get("error", "Unknown error")
                if attempt < attempts - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))  # Exponential backoff

            except asyncio.TimeoutError:
                last_error = f"Step timed out after {timeout_ms}ms"
                if attempt < attempts - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))
            except Exception as e:
                last_error = str(e)
                if attempt < attempts - 1:
                    await asyncio.sleep(0.5 * (attempt + 1))

        return {"status": "error", "error": last_error, "attempts": attempts}

    async def _route_command(self, command: str, params: Dict) -> Dict:
        """Route a command to the appropriate browser method."""
        cmd_map = {
            "navigate": lambda: self.browser.navigate(params.get("url", "")),
            "click": lambda: self.browser.click(params.get("selector", "")),
            "type": lambda: self.browser.type_text(params.get("text", "")),
            "press": lambda: self.browser.press_key(params.get("key", "Enter")),
            "fill-form": lambda: self.browser.fill_form(params.get("fields", {})),
            "scroll": lambda: self.browser.scroll(params.get("direction", "down"), params.get("amount", 500)),
            "hover": lambda: self.browser.hover(params.get("selector", "")),
            "screenshot": lambda: self.browser.screenshot(full_page=params.get("full_page", False)),
            "get-content": lambda: self.browser.get_content(),
            "get-dom": lambda: self.browser.get_dom_snapshot(),
            "wait": lambda: self.browser.wait_for_element(params.get("selector", ""), params.get("timeout", 10000)),
            "back": lambda: self.browser.go_back(),
            "forward": lambda: self.browser.go_forward(),
            "reload": lambda: self.browser.reload(),
            "double-click": lambda: self.browser.double_click(params.get("selector", "")),
            "drag-drop": lambda: self.browser.drag_and_drop(params.get("source", ""), params.get("target", "")),
            "clear-input": lambda: self.browser.clear_input(params.get("selector", "")),
            "checkbox": lambda: self.browser.set_checkbox(params.get("selector", ""), params.get("checked", True)),
            "upload": lambda: self.browser.upload_file(params.get("selector", ""), params.get("file_path", "")),
            "select": lambda: self.browser.select_option(params.get("selector", ""), params.get("value", "")),
        }

        handler = cmd_map.get(command)
        if not handler:
            return {"status": "error", "error": f"Unknown workflow command: {command}"}

        result = await handler()
        if isinstance(result, dict):
            if "status" not in result:
                result["status"] = "success"
            return result
        return {"status": "success", "result": str(result)}
