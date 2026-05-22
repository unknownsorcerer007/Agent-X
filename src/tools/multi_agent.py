"""
Agent-OS Multi-Agent Browsing Sharing Engine
Production-grade collaboration hub for multiple AI agents sharing browser sessions.

Architecture:
  AgentHub (singleton)
  ├── SharedWorkspace      — shared browser context with per-agent isolation
  ├── AgentRegistry        — tracks connected agents, roles, capabilities
  ├── LockManager          — optimistic/pessimistic locking on pages & elements
  ├── TaskBoard            — task delegation, assignment, status tracking
  ├── EventBus             — pub/sub for cross-agent event broadcasting
  ├── SharedMemory         — cross-agent key-value store with TTL
  ├── SessionHandoff       — transfer control between agents
  ├── ConflictResolver     — resolve simultaneous action conflicts
  └── AuditTrail           — per-agent action log with full attribution

Use cases:
  - Agent A navigates to login page, Agent B fills the form, Agent C clicks submit
  - Multiple agents work on different tabs simultaneously
  - One agent does research while another fills out forms
  - Agent delegates subtask to specialized agent (e.g., captcha solver)
  - Supervisor agent monitors and guides worker agents
"""
import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("agent-os.multi_agent")


# ─── Agent Roles & Permissions ──────────────────────────────

class AgentRole(str, Enum):
    OBSERVER = "observer"      # Read-only: can see page content, screenshots, DOM
    OPERATOR = "operator"      # Full browser control: click, fill, navigate
    SUPERVISOR = "supervisor"  # Operator + can manage other agents, assign tasks
    ADMIN = "admin"            # Full control including workspace config


ROLE_PERMISSIONS: Dict[AgentRole, Set[str]] = {
    AgentRole.OBSERVER: {
        "screenshot", "get-content", "get-dom", "get-links", "get-images",
        "get-text", "get-attr", "get-cookies", "console-logs",
        "page-summary", "page-tables", "page-emails", "page-phones",
        "page-seo", "page-accessibility", "smart-find", "smart-find-all",
        "tabs",  # can list tabs
        "record-status", "replay-position", "replay-events",
        "analyze", "analyze-search",
        "hub-status", "hub-agents", "hub-tasks", "hub-events",
        "hub-memory-get", "hub-audit",
    },
    AgentRole.OPERATOR: {
        "navigate", "click", "fill-form", "type", "press", "scroll",
        "hover", "select", "upload", "wait", "back", "forward", "reload",
        "double-click", "right-click", "context-action", "drag-drop",
        "drag-offset", "clear-input", "checkbox", "evaluate-js",
        "set-cookie", "set-proxy", "emulate-device", "viewport",
        "screenshot", "get-content", "get-dom", "get-links", "get-images",
        "get-text", "get-attr", "get-cookies", "console-logs",
        "tabs",  # full tab management
        "smart-wait", "smart-wait-network", "smart-wait-dom",
        "smart-wait-element", "smart-wait-page", "smart-wait-js",
        "smart-wait-compose", "smart-find", "smart-find-all",
        "smart-click", "smart-fill",
        "heal-click", "heal-fill", "heal-wait", "heal-hover",
        "heal-double-click", "heal-selector", "heal-fingerprint",
        "heal-fingerprint-page", "heal-stats",
        "retry-navigate", "retry-click", "retry-fill", "retry-api-call",
        "workflow", "workflow-template", "workflow-json",
        "network-start", "network-stop", "network-get", "network-apis",
        "network-detail", "network-stats", "network-export", "network-clear",
        "record-start", "record-stop", "record-pause", "record-resume",
        "record-annotate", "record-status",
        "page-summary", "page-tables", "page-emails", "page-phones",
        "page-seo", "page-accessibility",
        "hub-status", "hub-agents", "hub-tasks", "hub-events",
        "hub-memory-get", "hub-memory-set", "hub-audit",
        "hub-task-claim", "hub-task-complete", "hub-task-fail",
        "hub-broadcast", "hub-lock", "hub-unlock",
    },
    AgentRole.SUPERVISOR: None,  # Inherits OPERATOR + management commands
    AgentRole.ADMIN: None,       # All commands
}


# ─── Data Structures ────────────────────────────────────────

@dataclass
class AgentInfo:
    """Information about a connected agent."""
    agent_id: str
    name: str
    role: AgentRole
    capabilities: List[str] = field(default_factory=list)
    connected_at: float = field(default_factory=time.time)
    last_heartbeat: float = field(default_factory=time.time)
    active_tab: str = "main"
    current_task_id: Optional[str] = None
    commands_executed: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_alive(self, timeout_seconds: float = 60) -> bool:
        return (time.time() - self.last_heartbeat) < timeout_seconds

    def to_dict(self) -> Dict:
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "role": self.role.value,
            "capabilities": self.capabilities,
            "connected_seconds": round(time.time() - self.connected_at, 1),
            "last_heartbeat_seconds_ago": round(time.time() - self.last_heartbeat, 1),
            "alive": self.is_alive(),
            "active_tab": self.active_tab,
            "current_task_id": self.current_task_id,
            "commands_executed": self.commands_executed,
        }


class TaskStatus(str, Enum):
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Task:
    """A task that can be assigned to agents."""
    task_id: str
    title: str
    description: str
    status: TaskStatus = TaskStatus.PENDING
    assigned_to: Optional[str] = None
    assigned_by: Optional[str] = None
    created_at: float = field(default_factory=time.time)
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    result: Optional[Dict] = None
    priority: int = 0  # Higher = more urgent
    tags: List[str] = field(default_factory=list)
    dependencies: List[str] = field(default_factory=list)  # task_ids
    metadata: Dict[str, Any] = field(default_factory=dict)
    max_retries: int = 0
    retries: int = 0

    def to_dict(self) -> Dict:
        return {
            "task_id": self.task_id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "assigned_to": self.assigned_to,
            "assigned_by": self.assigned_by,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "result": self.result,
            "priority": self.priority,
            "tags": self.tags,
            "dependencies": self.dependencies,
            "retries": self.retries,
            "max_retries": self.max_retries,
        }


class LockType(str, Enum):
    SHARED = "shared"       # Multiple readers
    EXCLUSIVE = "exclusive"  # Single writer


@dataclass
class Lock:
    """A lock on a page or element."""
    lock_id: str
    resource: str          # e.g., "page:main", "element:#login-btn"
    lock_type: LockType
    owner_agent_id: str
    acquired_at: float = field(default_factory=time.time)
    expires_at: float = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_expired(self) -> bool:
        return self.expires_at > 0 and time.time() > self.expires_at


@dataclass
class AuditEntry:
    """An audit trail entry."""
    entry_id: str
    agent_id: str
    agent_name: str
    action: str
    resource: str
    timestamp: float = field(default_factory=time.time)
    details: Dict[str, Any] = field(default_factory=dict)
    success: bool = True
    duration_ms: float = 0


@dataclass
class EventMessage:
    """A pub/sub event message."""
    event_id: str
    topic: str
    sender_id: str
    payload: Dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    ttl_seconds: float = 300  # 5 min default

    def is_expired(self) -> bool:
        return self.ttl_seconds > 0 and time.time() > (self.timestamp + self.ttl_seconds)


# ─── Shared Memory ──────────────────────────────────────────

@dataclass
class MemoryEntry:
    key: str
    value: Any
    owner_agent_id: str
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    expires_at: float = 0  # 0 = no expiry
    access: str = "shared"  # "shared", "private", "readonly"

    def is_expired(self) -> bool:
        return self.expires_at > 0 and time.time() > self.expires_at


# ─── Agent Hub (Central Coordinator) ─────────────────────────

class AgentHub:
    """
    Central coordination hub for multi-agent browsing.

    Manages:
    - Agent registration and lifecycle
    - Permission checking and role enforcement
    - Element/page locking for conflict prevention
    - Task delegation and tracking
    - Cross-agent event broadcasting
    - Shared key-value memory
    - Session handoff between agents
    - Full audit trail

    Usage:
        hub = AgentHub(browser, session_manager)

        # Agent A joins
        await hub.register_agent("agent-a", "Researcher", role="observer")

        # Agent B joins
        await hub.register_agent("agent-b", "Form Filler", role="operator")

        # Agent A assigns task to Agent B
        task = await hub.create_task("Fill login form", assigned_to="agent-b")

        # Agent B locks the form, fills it, unlocks
        await hub.acquire_lock("agent-b", "page:main", "exclusive")
        # ... fill form ...
        await hub.release_lock("agent-b", "lock-id")

        # Agent B broadcasts result
        await hub.broadcast("agent-b", "task_update", {"task_id": "...", "status": "done"})

        # Agent A subscribes to updates
        events = await hub.get_events("agent-a", topic="task_update")
    """

    # Default TTLs
    LOCK_TTL_SECONDS = 30       # Auto-release locks after 30s
    HEARTBEAT_INTERVAL = 15     # Agents heartbeat every 15s
    AGENT_TIMEOUT = 60          # Consider agent dead after 60s no heartbeat
    EVENT_TTL = 300             # Events expire after 5 min
    MEMORY_CLEANUP_INTERVAL = 60

    def __init__(self, browser, session_manager=None):
        self.browser = browser
        self.session_manager = session_manager

        # Core state
        self._agents: Dict[str, AgentInfo] = {}
        self._tasks: Dict[str, Task] = {}
        self._locks: Dict[str, Lock] = {}
        self._events: List[EventMessage] = []
        self._memory: Dict[str, MemoryEntry] = {}
        self._audit: List[AuditEntry] = []

        # Per-agent event subscription tracking
        self._agent_last_event_check: Dict[str, float] = {}

        # Background tasks
        self._cleanup_task: Optional[asyncio.Task] = None
        self._lock_cleanup_task: Optional[asyncio.Task] = None

        # Stats
        self._stats = {
            "total_agents_joined": 0,
            "total_tasks_created": 0,
            "total_locks_acquired": 0,
            "total_events_broadcast": 0,
            "total_commands_authorized": 0,
            "total_commands_denied": 0,
        }

    async def start(self):
        """Start background maintenance tasks."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self._lock_cleanup_task = asyncio.create_task(self._lock_cleanup_loop())
        logger.info("AgentHub started")

    async def stop(self):
        """Shutdown the hub."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
        if self._lock_cleanup_task:
            self._lock_cleanup_task.cancel()
        # Notify all agents
        for agent_id in list(self._agents.keys()):
            await self.unregister_agent(agent_id)
        logger.info("AgentHub stopped")

    # ─── Agent Management ───────────────────────────────────

    async def register_agent(
        self,
        agent_id: str = None,
        name: str = None,
        role: str = "operator",
        capabilities: List[str] = None,
        metadata: Dict = None,
    ) -> Dict[str, Any]:
        """
        Register an agent with the hub.

        Args:
            agent_id: Unique ID (auto-generated if not provided).
            name: Human-readable name.
            role: "observer" | "operator" | "supervisor" | "admin"
            capabilities: List of what this agent can do (e.g., ["form-filling", "research"])
            metadata: Arbitrary metadata.
        """
        agent_id = agent_id or f"agent-{str(uuid.uuid4())[:8]}"
        name = name or agent_id

        if agent_id in self._agents:
            # Re-registration (heartbeat/update)
            agent = self._agents[agent_id]
            agent.last_heartbeat = time.time()
            agent.name = name
            if metadata:
                agent.metadata.update(metadata)
            return {"status": "success", "agent_id": agent_id, "action": "updated"}

        # Validate role
        try:
            agent_role = AgentRole(role)
        except ValueError:
            return {"status": "error", "error": f"Invalid role: {role}. Valid: {[r.value for r in AgentRole]}"}

        agent = AgentInfo(
            agent_id=agent_id,
            name=name,
            role=agent_role,
            capabilities=capabilities or [],
            metadata=metadata or {},
        )
        self._agents[agent_id] = agent
        self._stats["total_agents_joined"] += 1

        # Broadcast join event
        await self._emit_event("system", "agent_joined", {
            "agent_id": agent_id,
            "name": name,
            "role": role,
        })

        # Audit
        self._add_audit(agent_id, name, "register", "hub", success=True)

        logger.info(f"Agent registered: {name} ({agent_id}) as {role}")

        return {
            "status": "success",
            "agent_id": agent_id,
            "name": name,
            "role": role,
            "permissions": list(self._get_permissions(agent_role)),
            "active_agents": len([a for a in self._agents.values() if a.is_alive()]),
        }

    async def unregister_agent(self, agent_id: str) -> Dict[str, Any]:
        """Unregister an agent and release all its resources."""
        agent = self._agents.pop(agent_id, None)
        if not agent:
            return {"status": "error", "error": f"Agent not found: {agent_id}"}

        # Release all locks held by this agent
        released_locks = []
        for lock_id, lock in list(self._locks.items()):
            if lock.owner_agent_id == agent_id:
                del self._locks[lock_id]
                released_locks.append(lock_id)

        # Reassign pending tasks
        reassigned = 0
        for task in self._tasks.values():
            if task.assigned_to == agent_id and task.status in (TaskStatus.ASSIGNED, TaskStatus.IN_PROGRESS):
                task.status = TaskStatus.PENDING
                task.assigned_to = None
                reassigned += 1

        # Audit
        self._add_audit(agent_id, agent.name, "unregister", "hub", success=True)

        # Broadcast leave
        await self._emit_event("system", "agent_left", {
            "agent_id": agent_id,
            "name": agent.name,
            "released_locks": len(released_locks),
            "reassigned_tasks": reassigned,
        })

        logger.info(f"Agent unregistered: {agent.name} ({agent_id})")

        return {
            "status": "success",
            "agent_id": agent_id,
            "released_locks": released_locks,
            "reassigned_tasks": reassigned,
        }

    async def heartbeat(self, agent_id: str) -> Dict[str, Any]:
        """Agent heartbeat — must call periodically or get reaped."""
        agent = self._agents.get(agent_id)
        if not agent:
            return {"status": "error", "error": f"Agent not found: {agent_id}. Re-register."}
        agent.last_heartbeat = time.time()
        return {"status": "alive", "agent_id": agent_id}

    def get_agents(self, alive_only: bool = True) -> Dict[str, Any]:
        """List all registered agents."""
        agents = []
        for a in self._agents.values():
            if alive_only and not a.is_alive(self.AGENT_TIMEOUT):
                continue
            agents.append(a.to_dict())

        return {
            "status": "success",
            "agents": agents,
            "count": len(agents),
            "by_role": {
                role.value: len([a for a in agents if a["role"] == role.value])
                for role in AgentRole
            },
        }

    # ─── Permission Enforcement ─────────────────────────────

    def check_permission(self, agent_id: str, command: str) -> Tuple[bool, str]:
        """
        Check if an agent is authorized to execute a command.

        Returns (allowed: bool, reason: str)
        """
        agent = self._agents.get(agent_id)
        if not agent:
            return False, f"Agent not registered: {agent_id}"

        if not agent.is_alive(self.AGENT_TIMEOUT):
            return False, f"Agent timed out (no heartbeat for {self.AGENT_TIMEOUT}s)"

        permissions = self._get_permissions(agent.role)

        if command in permissions:
            self._stats["total_commands_authorized"] += 1
            return True, "authorized"

        self._stats["total_commands_denied"] += 1
        return False, f"Role '{agent.role.value}' cannot execute '{command}'"

    def _get_permissions(self, role: AgentRole) -> Set[str]:
        """Get the full set of permissions for a role."""
        if role == AgentRole.ADMIN:
            # Admin gets everything
            return set().union(*ROLE_PERMISSIONS.values()) | {
                "hub-admin-config", "hub-admin-kill-agent", "hub-admin-evict",
            }

        if role == AgentRole.SUPERVISOR:
            # Supervisor = operator + management
            return ROLE_PERMISSIONS[AgentRole.OPERATOR] | {
                "hub-assign-task", "hub-cancel-task", "hub-set-role",
                "hub-admin-kill-agent",
            }

        return ROLE_PERMISSIONS.get(role, set())

    # ─── Lock Management ────────────────────────────────────

    async def acquire_lock(
        self,
        agent_id: str,
        resource: str,
        lock_type: str = "exclusive",
        ttl_seconds: float = None,
        timeout_ms: float = 5000,
    ) -> Dict[str, Any]:
        """
        Acquire a lock on a resource (page, element, tab).

        Args:
            agent_id: Agent requesting the lock.
            resource: Resource identifier (e.g., "page:main", "element:#login-btn", "tab:tab-1").
            lock_type: "shared" (multiple readers) or "exclusive" (single writer).
            ttl_seconds: Auto-release after this time (default 30s).
            timeout_ms: How long to wait for lock acquisition.
        """
        agent = self._agents.get(agent_id)
        if not agent:
            return {"status": "error", "error": f"Agent not registered: {agent_id}"}

        allowed, reason = self.check_permission(agent_id, "hub-lock")
        if not allowed:
            return {"status": "error", "error": reason}

        lt = LockType(lock_type)
        ttl = ttl_seconds or self.LOCK_TTL_SECONDS
        start = time.time()

        while True:
            # Check for conflicts
            conflict = self._find_lock_conflict(resource, lt, agent_id)

            if not conflict:
                # No conflict — acquire
                lock_id = str(uuid.uuid4())[:8]
                lock = Lock(
                    lock_id=lock_id,
                    resource=resource,
                    lock_type=lt,
                    owner_agent_id=agent_id,
                    expires_at=time.time() + ttl,
                )
                self._locks[lock_id] = lock
                self._stats["total_locks_acquired"] += 1

                self._add_audit(agent_id, agent.name, "lock_acquire", resource, details={
                    "lock_id": lock_id, "lock_type": lock_type, "ttl": ttl,
                })

                return {
                    "status": "success",
                    "lock_id": lock_id,
                    "resource": resource,
                    "lock_type": lock_type,
                    "expires_in_seconds": ttl,
                }

            # Conflict exists — wait or fail
            elapsed_ms = (time.time() - start) * 1000
            if elapsed_ms >= timeout_ms:
                return {
                    "status": "error",
                    "error": f"Lock acquisition timed out — resource '{resource}' held by '{conflict.owner_agent_id}'",
                    "held_by": conflict.owner_agent_id,
                    "lock_type": conflict.lock_type.value,
                    "held_since_seconds": round(time.time() - conflict.acquired_at, 1),
                }

            await asyncio.sleep(0.1)  # Poll every 100ms

    async def release_lock(self, agent_id: str, lock_id: str) -> Dict[str, Any]:
        """Release a lock."""
        lock = self._locks.get(lock_id)
        if not lock:
            return {"status": "error", "error": f"Lock not found: {lock_id}"}

        if lock.owner_agent_id != agent_id:
            agent = self._agents.get(agent_id)
            if not agent or agent.role not in (AgentRole.SUPERVISOR, AgentRole.ADMIN):
                return {"status": "error", "error": f"Lock owned by '{lock.owner_agent_id}', not '{agent_id}'"}

        del self._locks[lock_id]

        agent = self._agents.get(agent_id)
        self._add_audit(agent_id, agent.name if agent else agent_id, "lock_release", lock.resource, details={"lock_id": lock_id})

        return {"status": "success", "lock_id": lock_id, "resource": lock.resource}

    def get_locks(self, resource: str = None, agent_id: str = None) -> Dict[str, Any]:
        """Get active locks, optionally filtered."""
        locks = []
        for lock in self._locks.values():
            if lock.is_expired():
                continue
            if resource and lock.resource != resource:
                continue
            if agent_id and lock.owner_agent_id != agent_id:
                continue
            locks.append({
                "lock_id": lock.lock_id,
                "resource": lock.resource,
                "lock_type": lock.lock_type.value,
                "owner_agent_id": lock.owner_agent_id,
                "held_seconds": round(time.time() - lock.acquired_at, 1),
                "expires_in_seconds": round(lock.expires_at - time.time(), 1) if lock.expires_at > 0 else None,
            })

        return {"status": "success", "locks": locks, "count": len(locks)}

    def _find_lock_conflict(self, resource: str, requested_type: LockType, agent_id: str) -> Optional[Lock]:
        """Check if a lock conflicts with existing locks."""
        for lock in self._locks.values():
            if lock.resource != resource:
                continue
            if lock.is_expired():
                continue
            if lock.owner_agent_id == agent_id:
                continue  # Same agent can re-acquire

            # Exclusive lock blocks everything
            if lock.lock_type == LockType.EXCLUSIVE:
                return lock
            # Requesting exclusive blocks on any existing lock
            if requested_type == LockType.EXCLUSIVE:
                return lock

        return None

    # ─── Task Management ────────────────────────────────────

    async def create_task(
        self,
        title: str,
        description: str = "",
        assigned_to: str = None,
        assigned_by: str = None,
        priority: int = 0,
        tags: List[str] = None,
        dependencies: List[str] = None,
        max_retries: int = 0,
        metadata: Dict = None,
    ) -> Dict[str, Any]:
        """
        Create a task on the shared task board.

        Args:
            title: Short task title.
            description: Detailed description.
            assigned_to: Agent ID to assign to (None = unassigned).
            assigned_by: Agent ID that created the task.
            priority: Higher = more urgent (0-10).
            tags: Tags for filtering (e.g., ["form-filling", "urgent"]).
            dependencies: Task IDs that must complete first.
            max_retries: Auto-retry on failure.
            metadata: Arbitrary task data.
        """
        task_id = str(uuid.uuid4())[:8]

        # Validate assignee
        if assigned_to and assigned_to not in self._agents:
            return {"status": "error", "error": f"Agent not found: {assigned_to}"}

        task = Task(
            task_id=task_id,
            title=title,
            description=description,
            status=TaskStatus.ASSIGNED if assigned_to else TaskStatus.PENDING,
            assigned_to=assigned_to,
            assigned_by=assigned_by,
            priority=priority,
            tags=tags or [],
            dependencies=dependencies or [],
            max_retries=max_retries,
            metadata=metadata or {},
        )
        self._tasks[task_id] = task
        self._stats["total_tasks_created"] += 1

        # Audit
        creator = self._agents.get(assigned_by)
        self._add_audit(
            assigned_by or "system",
            creator.name if creator else "system",
            "task_create", f"task:{task_id}",
            details={"title": title, "assigned_to": assigned_to},
        )

        # Broadcast
        await self._emit_event("tasks", "task_created", task.to_dict())

        return {"status": "success", **task.to_dict()}

    async def claim_task(self, agent_id: str, task_id: str = None, tags: List[str] = None) -> Dict[str, Any]:
        """
        Claim an unassigned task. Optionally filter by tags.
        Returns the claimed task or error.
        """
        agent = self._agents.get(agent_id)
        if not agent:
            return {"status": "error", "error": f"Agent not registered: {agent_id}"}

        if task_id:
            task = self._tasks.get(task_id)
            if not task:
                return {"status": "error", "error": f"Task not found: {task_id}"}
            if task.status != TaskStatus.PENDING:
                return {"status": "error", "error": f"Task not available: status={task.status.value}"}
        else:
            # Find highest-priority pending task matching tags
            available = [
                t for t in self._tasks.values()
                if t.status == TaskStatus.PENDING
                and (not tags or any(tag in t.tags for tag in tags))
            ]
            if not available:
                return {"status": "error", "error": "No pending tasks available"}
            task = max(available, key=lambda t: t.priority)

        # Check dependencies
        for dep_id in task.dependencies:
            dep = self._tasks.get(dep_id)
            if dep and dep.status != TaskStatus.COMPLETED:
                return {"status": "error", "error": f"Dependency not met: {dep_id} (status: {dep.status.value})"}

        # Assign
        task.assigned_to = agent_id
        task.status = TaskStatus.ASSIGNED
        agent.current_task_id = task.task_id

        self._add_audit(agent_id, agent.name, "task_claim", f"task:{task.task_id}", details={"title": task.title})
        await self._emit_event("tasks", "task_claimed", {**task.to_dict(), "claimed_by": agent_id})

        return {"status": "success", **task.to_dict()}

    async def start_task(self, agent_id: str, task_id: str) -> Dict[str, Any]:
        """Mark a task as in-progress."""
        task = self._tasks.get(task_id)
        if not task:
            return {"status": "error", "error": f"Task not found: {task_id}"}
        if task.assigned_to != agent_id:
            return {"status": "error", "error": f"Task assigned to '{task.assigned_to}', not '{agent_id}'"}

        task.status = TaskStatus.IN_PROGRESS
        task.started_at = time.time()

        await self._emit_event("tasks", "task_started", task.to_dict())
        return {"status": "success", **task.to_dict()}

    async def complete_task(self, agent_id: str, task_id: str, result: Dict = None) -> Dict[str, Any]:
        """Mark a task as completed with optional result data."""
        task = self._tasks.get(task_id)
        if not task:
            return {"status": "error", "error": f"Task not found: {task_id}"}
        if task.assigned_to != agent_id:
            return {"status": "error", "error": f"Task assigned to '{task.assigned_to}', not '{agent_id}'"}

        task.status = TaskStatus.COMPLETED
        task.completed_at = time.time()
        task.result = result

        agent = self._agents.get(agent_id)
        if agent:
            agent.current_task_id = None

        self._add_audit(agent_id, agent.name if agent else agent_id, "task_complete", f"task:{task_id}")
        await self._emit_event("tasks", "task_completed", task.to_dict())

        return {"status": "success", **task.to_dict()}

    async def fail_task(self, agent_id: str, task_id: str, error: str = "") -> Dict[str, Any]:
        """Mark a task as failed. Auto-retry if retries remain."""
        task = self._tasks.get(task_id)
        if not task:
            return {"status": "error", "error": f"Task not found: {task_id}"}

        if task.retries < task.max_retries:
            task.retries += 1
            task.status = TaskStatus.PENDING
            task.assigned_to = None
            logger.info(f"Task {task_id} failed, retrying ({task.retries}/{task.max_retries})")
        else:
            task.status = TaskStatus.FAILED
            task.completed_at = time.time()
            task.result = {"error": error}

        agent = self._agents.get(agent_id)
        if agent:
            agent.current_task_id = None

        await self._emit_event("tasks", "task_failed", {**task.to_dict(), "error": error})
        return {"status": "success", **task.to_dict()}

    async def cancel_task(self, task_id: str, cancelled_by: str = None) -> Dict[str, Any]:
        """Cancel a task."""
        task = self._tasks.get(task_id)
        if not task:
            return {"status": "error", "error": f"Task not found: {task_id}"}

        task.status = TaskStatus.CANCELLED
        task.completed_at = time.time()

        if task.assigned_to:
            agent = self._agents.get(task.assigned_to)
            if agent:
                agent.current_task_id = None

        await self._emit_event("tasks", "task_cancelled", task.to_dict())
        return {"status": "success", **task.to_dict()}

    def get_tasks(
        self,
        status: str = None,
        assigned_to: str = None,
        tags: List[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """Get tasks with optional filters."""
        tasks = list(self._tasks.values())

        if status:
            tasks = [t for t in tasks if t.status.value == status]
        if assigned_to:
            tasks = [t for t in tasks if t.assigned_to == assigned_to]
        if tags:
            tasks = [t for t in tasks if any(tag in t.tags for tag in tags)]

        # Sort: priority desc, created_at desc
        tasks.sort(key=lambda t: (t.priority, t.created_at), reverse=True)

        return {
            "status": "success",
            "tasks": [t.to_dict() for t in tasks[:limit]],
            "total": len(tasks),
            "by_status": {
                s.value: len([t for t in self._tasks.values() if t.status == s])
                for s in TaskStatus
            },
        }

    # ─── Event Bus (Pub/Sub) ────────────────────────────────

    async def broadcast(
        self,
        sender_id: str,
        topic: str,
        payload: Dict[str, Any],
        ttl_seconds: float = None,
    ) -> Dict[str, Any]:
        """
        Broadcast an event to all subscribed agents.

        Topics: "task_update", "page_change", "alert", "data", "coordination", or custom.
        """
        agent = self._agents.get(sender_id)
        if not agent:
            return {"status": "error", "error": f"Agent not registered: {sender_id}"}

        event = EventMessage(
            event_id=str(uuid.uuid4())[:8],
            topic=topic,
            sender_id=sender_id,
            payload=payload,
            ttl_seconds=ttl_seconds or self.EVENT_TTL,
        )
        self._events.append(event)
        self._stats["total_events_broadcast"] += 1

        # Trim old events
        self._trim_events()

        return {
            "status": "success",
            "event_id": event.event_id,
            "topic": topic,
            "broadcast_to": len([a for a in self._agents.values() if a.is_alive() and a.agent_id != sender_id]),
        }

    def get_events(
        self,
        agent_id: str,
        topic: str = None,
        since_seconds: float = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """
        Get events for an agent. Returns events since last check by default.
        """
        since = self._agent_last_event_check.get(agent_id, 0)
        if since_seconds is not None:
            since = time.time() - since_seconds

        cutoff = time.time()
        events = []
        for e in self._events:
            if e.timestamp <= since:
                continue
            if e.sender_id == agent_id:
                continue  # Don't return own events
            if e.is_expired():
                continue
            if topic and e.topic != topic:
                continue
            events.append({
                "event_id": e.event_id,
                "topic": e.topic,
                "sender_id": e.sender_id,
                "payload": e.payload,
                "timestamp": e.timestamp,
                "age_seconds": round(time.time() - e.timestamp, 1),
            })

        self._agent_last_event_check[agent_id] = cutoff

        return {
            "status": "success",
            "events": events[-limit:],
            "count": len(events),
        }

    async def _emit_event(self, topic: str, event_name: str, data: Dict):
        """Internal event emission."""
        event = EventMessage(
            event_id=str(uuid.uuid4())[:8],
            topic=topic,
            sender_id="system",
            payload={"event": event_name, **data},
            ttl_seconds=self.EVENT_TTL,
        )
        self._events.append(event)

    def _trim_events(self):
        """Remove expired and excess events."""
        max_events = 5000
        cutoff = time.time() - self.EVENT_TTL
        self._events = [e for e in self._events if e.timestamp > cutoff and not e.is_expired()]
        if len(self._events) > max_events:
            self._events = self._events[-max_events:]

    # ─── Shared Memory ──────────────────────────────────────

    async def memory_set(
        self,
        agent_id: str,
        key: str,
        value: Any,
        ttl_seconds: float = 0,
        access: str = "shared",
    ) -> Dict[str, Any]:
        """
        Set a shared memory entry.

        Args:
            key: Memory key.
            value: Value (any JSON-serializable type).
            ttl_seconds: Auto-expire after this time (0 = no expiry).
            access: "shared" (all can read/write), "private" (only owner), "readonly" (all read, owner writes).
        """
        agent = self._agents.get(agent_id)
        if not agent:
            return {"status": "error", "error": f"Agent not registered: {agent_id}"}

        existing = self._memory.get(key)
        if existing and existing.access == "readonly" and existing.owner_agent_id != agent_id:
            return {"status": "error", "error": f"Key '{key}' is readonly, owned by '{existing.owner_agent_id}'"}

        entry = MemoryEntry(
            key=key,
            value=value,
            owner_agent_id=agent_id,
            updated_at=time.time(),
            expires_at=time.time() + ttl_seconds if ttl_seconds > 0 else 0,
            access=access,
        )
        self._memory[key] = entry

        return {"status": "success", "key": key, "access": access}

    async def memory_get(self, agent_id: str, key: str) -> Dict[str, Any]:
        """Get a shared memory entry."""
        entry = self._memory.get(key)
        if not entry:
            return {"status": "error", "error": f"Key not found: {key}"}
        if entry.is_expired():
            del self._memory[key]
            return {"status": "error", "error": f"Key expired: {key}"}
        if entry.access == "private" and entry.owner_agent_id != agent_id:
            return {"status": "error", "error": f"Key '{key}' is private, owned by '{entry.owner_agent_id}'"}

        return {
            "status": "success",
            "key": key,
            "value": entry.value,
            "owner": entry.owner_agent_id,
            "access": entry.access,
            "age_seconds": round(time.time() - entry.created_at, 1),
        }

    async def memory_delete(self, agent_id: str, key: str) -> Dict[str, Any]:
        """Delete a shared memory entry."""
        entry = self._memory.get(key)
        if not entry:
            return {"status": "error", "error": f"Key not found: {key}"}
        if entry.owner_agent_id != agent_id:
            agent = self._agents.get(agent_id)
            if not agent or agent.role not in (AgentRole.SUPERVISOR, AgentRole.ADMIN):
                return {"status": "error", "error": "Only owner or supervisor can delete"}

        del self._memory[key]
        return {"status": "success", "deleted": key}

    def memory_list(self, prefix: str = None, agent_id: str = None) -> Dict[str, Any]:
        """List memory keys (values not included for security)."""
        entries = []
        for key, entry in self._memory.items():
            if entry.is_expired():
                continue
            if prefix and not key.startswith(prefix):
                continue
            if entry.access == "private" and agent_id and entry.owner_agent_id != agent_id:
                continue
            entries.append({
                "key": key,
                "owner": entry.owner_agent_id,
                "access": entry.access,
                "age_seconds": round(time.time() - entry.created_at, 1),
                "expires_in": round(entry.expires_at - time.time(), 1) if entry.expires_at > 0 else None,
            })

        return {"status": "success", "entries": entries, "count": len(entries)}

    # ─── Session Handoff ────────────────────────────────────

    async def handoff(
        self,
        from_agent_id: str,
        to_agent_id: str,
        resource: str = "page:main",
        context: Dict = None,
    ) -> Dict[str, Any]:
        """
        Hand off control from one agent to another.
        Transfers locks, updates active tab, notifies both agents.

        Args:
            from_agent_id: Current controller.
            to_agent_id: New controller.
            resource: What to hand off ("page:main", "tab:tab-1", etc.).
            context: Optional context data to pass (URL, current state, notes).
        """
        from_agent = self._agents.get(from_agent_id)
        to_agent = self._agents.get(to_agent_id)

        if not from_agent:
            return {"status": "error", "error": f"Agent not found: {from_agent_id}"}
        if not to_agent:
            return {"status": "error", "error": f"Agent not found: {to_agent_id}"}

        # Transfer locks
        transferred_locks = []
        for lock_id, lock in list(self._locks.items()):
            if lock.owner_agent_id == from_agent_id and lock.resource.startswith(resource.split(":")[0]):
                lock.owner_agent_id = to_agent_id
                lock.acquired_at = time.time()
                transferred_locks.append(lock_id)

        # Update active tab
        if resource.startswith("tab:"):
            tab_id = resource.split(":", 1)[1]
            to_agent.active_tab = tab_id

        # Audit
        self._add_audit(
            from_agent_id, from_agent.name, "handoff", resource,
            details={"to": to_agent_id, "context": context, "locks_transferred": len(transferred_locks)},
        )

        # Broadcast
        await self._emit_event("coordination", "session_handoff", {
            "from": from_agent_id,
            "to": to_agent_id,
            "resource": resource,
            "context": context,
            "locks_transferred": transferred_locks,
        })

        return {
            "status": "success",
            "from": from_agent_id,
            "to": to_agent_id,
            "resource": resource,
            "locks_transferred": transferred_locks,
            "context": context,
        }

    # ─── Audit Trail ────────────────────────────────────────

    def get_audit(
        self,
        agent_id: str = None,
        action: str = None,
        since_seconds: float = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """Get audit trail with optional filters."""
        entries = self._audit

        if agent_id:
            entries = [e for e in entries if e.agent_id == agent_id]
        if action:
            entries = [e for e in entries if e.action == action]
        if since_seconds:
            cutoff = time.time() - since_seconds
            entries = [e for e in entries if e.timestamp >= cutoff]

        return {
            "status": "success",
            "entries": [
                {
                    "id": e.entry_id,
                    "agent_id": e.agent_id,
                    "agent_name": e.agent_name,
                    "action": e.action,
                    "resource": e.resource,
                    "timestamp": e.timestamp,
                    "age_seconds": round(time.time() - e.timestamp, 1),
                    "success": e.success,
                    "details": e.details,
                }
                for e in entries[-limit:]
            ],
            "total": len(entries),
        }

    def _add_audit(self, agent_id: str, agent_name: str, action: str, resource: str, details: Dict = None, success: bool = True):
        """Add audit entry."""
        entry = AuditEntry(
            entry_id=str(uuid.uuid4())[:8],
            agent_id=agent_id,
            agent_name=agent_name,
            action=action,
            resource=resource,
            details=details or {},
            success=success,
        )
        self._audit.append(entry)
        # Cap audit at 10k entries
        if len(self._audit) > 10000:
            self._audit = self._audit[-5000:]

    # ─── Status & Health ────────────────────────────────────

    def get_status(self) -> Dict[str, Any]:
        """Get hub status and statistics."""
        alive_agents = [a for a in self._agents.values() if a.is_alive(self.AGENT_TIMEOUT)]
        active_locks = [lk for lk in self._locks.values() if not lk.is_expired()]
        pending_tasks = [t for t in self._tasks.values() if t.status in (TaskStatus.PENDING, TaskStatus.ASSIGNED)]  # noqa: F841

        return {
            "status": "success",
            "hub": {
                "agents": {
                    "total": len(self._agents),
                    "alive": len(alive_agents),
                    "by_role": {
                        role.value: len([a for a in alive_agents if a.role == role])
                        for role in AgentRole
                    },
                },
                "tasks": {
                    "total": len(self._tasks),
                    "pending": len([t for t in self._tasks.values() if t.status == TaskStatus.PENDING]),
                    "in_progress": len([t for t in self._tasks.values() if t.status == TaskStatus.IN_PROGRESS]),
                    "completed": len([t for t in self._tasks.values() if t.status == TaskStatus.COMPLETED]),
                    "failed": len([t for t in self._tasks.values() if t.status == TaskStatus.FAILED]),
                },
                "locks": {
                    "active": len(active_locks),
                    "by_type": {
                        lt.value: len([lk for lk in active_locks if lk.lock_type == lt])
                        for lt in LockType
                    },
                },
                "memory": {
                    "keys": len(self._memory),
                    "expired": len([e for e in self._memory.values() if e.is_expired()]),
                },
                "events": {
                    "buffered": len(self._events),
                },
                "audit": {
                    "entries": len(self._audit),
                },
            },
            "stats": self._stats,
        }

    # ─── Background Maintenance ─────────────────────────────

    async def _cleanup_loop(self):
        """Periodic cleanup of stale agents, expired memory, old events."""
        while True:
            try:
                await asyncio.sleep(self.MEMORY_CLEANUP_INTERVAL)

                # Reap dead agents
                dead = [aid for aid, a in self._agents.items() if not a.is_alive(self.AGENT_TIMEOUT * 2)]
                for aid in dead:
                    await self.unregister_agent(aid)

                # Clean expired memory
                expired_keys = [k for k, v in self._memory.items() if v.is_expired()]
                for k in expired_keys:
                    del self._memory[k]

                # Trim events
                self._trim_events()

                if dead or expired_keys:
                    logger.info(f"Cleanup: removed {len(dead)} dead agents, {len(expired_keys)} expired memory keys")

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup error: {e}")

    async def _lock_cleanup_loop(self):
        """Auto-release expired locks."""
        while True:
            try:
                await asyncio.sleep(5)
                expired = [lid for lid, lock in self._locks.items() if lock.is_expired()]
                for lid in expired:
                    lock = self._locks.pop(lid)
                    logger.info(f"Auto-released expired lock: {lock.resource} (was held by {lock.owner_agent_id})")
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(5)
