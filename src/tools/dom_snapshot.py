"""
Agent-OS DOM Snapshot — Token-Efficient Page Representation
============================================================
Instead of sending raw HTML (50,000+ chars) to the LLM, this module
produces an accessibility tree snapshot (2,000-5,000 chars) that
captures the SEMANTIC structure of the page.

This is the core token-saving mechanism: the LLM receives a compact,
structured representation of the page instead of noisy HTML.

Ported from agent-browser (Vercel Labs) Rust implementation.
See THIRD_PARTY_LICENSES.md for attribution.
"""

import logging
import json
from typing import Any, Dict, List, Optional, Set, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger("agent-os.dom-snapshot")

# ═══════════════════════════════════════════════════════════════
# ROLE CLASSIFICATIONS
# ═══════════════════════════════════════════════════════════════

INTERACTIVE_ROLES = frozenset([
    "button", "link", "textbox", "checkbox", "radio", "combobox",
    "listbox", "menuitem", "menuitemcheckbox", "menuitemradio",
    "option", "searchbox", "slider", "spinbutton", "switch",
    "tab", "treeitem", "Iframe",
])

CONTENT_ROLES = frozenset([
    "heading", "cell", "gridcell", "columnheader", "rowheader",
    "listitem", "article", "region", "main", "navigation",
])

STRUCTURAL_ROLES = frozenset([
    "generic", "group", "list", "table", "row", "rowgroup",
    "grid", "treegrid", "menu", "menubar", "toolbar", "tablist",
    "tree", "directory", "document", "application", "presentation",
    "none", "WebArea", "RootWebArea",
])

INVISIBLE_CHARS = frozenset([
    '\uFEFF', '\u200B', '\u200C', '\u200D', '\u2060', '\u00A0',
])

# ═══════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═══════════════════════════════════════════════════════════════

@dataclass
class SnapshotOptions:
    """Options for controlling snapshot output."""
    interactive: bool = False       # Only include interactive elements
    compact: bool = False           # Remove empty structural elements
    depth: Optional[int] = None     # Limit tree depth
    urls: bool = False              # Include href URLs for links
    selector: Optional[str] = None  # Scope to CSS selector


@dataclass
class CursorElementInfo:
    """Info about a cursor-interactive element (cursor:pointer, onclick, etc.)."""
    kind: str                       # "clickable", "focusable", "editable"
    hints: List[str] = field(default_factory=list)
    text: str = ""
    hidden_input_kind: Optional[str] = None     # "radio" or "checkbox"
    hidden_input_checked: Optional[str] = None  # "true", "false", "mixed"


@dataclass
class TreeNode:
    """A node in the accessibility tree."""
    role: str = ""
    name: str = ""
    level: Optional[int] = None
    checked: Optional[str] = None
    expanded: Optional[bool] = None
    selected: Optional[bool] = None
    disabled: Optional[bool] = None
    required: Optional[bool] = None
    value_text: Optional[str] = None
    backend_node_id: Optional[int] = None
    children: List[int] = field(default_factory=list)
    parent_idx: Optional[int] = None
    has_ref: bool = False
    ref_id: Optional[str] = None
    depth: int = 0
    cursor_info: Optional[CursorElementInfo] = None
    url: Optional[str] = None


@dataclass
class RefEntry:
    """A reference entry mapping ref_id to an element."""
    ref_id: str
    backend_node_id: Optional[int]
    role: str
    name: str
    nth: Optional[int] = None
    frame_id: Optional[str] = None


class RefMap:
    """Maps ref IDs (@e1, @e2...) to DOM elements for subsequent commands."""

    def __init__(self):
        self._entries: Dict[str, RefEntry] = {}
        self._next_ref: int = 1

    def add(self, ref_id: str, backend_node_id: Optional[int],
            role: str, name: str, nth: Optional[int] = None,
            frame_id: Optional[str] = None):
        self._entries[ref_id] = RefEntry(
            ref_id=ref_id,
            backend_node_id=backend_node_id,
            role=role,
            name=name,
            nth=nth,
            frame_id=frame_id,
        )

    def get(self, ref_id: str) -> Optional[RefEntry]:
        return self._entries.get(ref_id)

    def next_ref_num(self) -> int:
        return self._next_ref

    def set_next_ref_num(self, num: int):
        self._next_ref = num

    def entries_sorted(self) -> List[Tuple[str, RefEntry]]:
        return sorted(self._entries.items(), key=lambda x: x[0])

    def clear(self):
        self._entries.clear()
        self._next_ref = 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            ref_id: {
                "role": entry.role,
                "name": entry.name,
                "backend_node_id": entry.backend_node_id,
                "nth": entry.nth,
            }
            for ref_id, entry in self._entries.items()
        }


# ═══════════════════════════════════════════════════════════════
# ACCESSIBILITY TREE EXTRACTION (via CDP)
# ═══════════════════════════════════════════════════════════════

async def get_ax_tree(page) -> List[Dict[str, Any]]:
    """Get the full accessibility tree from a Playwright page via CDP.

    Args:
        page: Playwright Page object

    Returns:
        List of AX node dicts from Chrome's Accessibility.getFullAXTree
    """
    try:
        cdp = await page.context.new_cdp_session(page)
        result = await cdp.send("Accessibility.getFullAXTree")
        await cdp.detach()
        return result.get("nodes", [])
    except Exception as e:
        logger.warning(f"CDP AX tree failed, falling back to JS: {e}")
        return await _get_ax_tree_js(page)


async def _get_ax_tree_js(page) -> List[Dict[str, Any]]:
    """Fallback: Build a simplified accessibility tree using JavaScript.

    When CDP is not available (e.g., in some browser modes), we build
    a tree using DOM APIs and ARIA attributes.
    """
    try:
        tree = await page.evaluate("""() => {
            function getRole(el) {
                const role = el.getAttribute('role');
                if (role) return role;
                const tag = el.tagName.toLowerCase();
                const type = el.getAttribute('type');
                const map = {
                    'a': 'link', 'button': 'button', 'input': 'textbox',
                    'select': 'combobox', 'textarea': 'textbox',
                    'h1': 'heading', 'h2': 'heading', 'h3': 'heading',
                    'h4': 'heading', 'h5': 'heading', 'h6': 'heading',
                    'img': 'img', 'nav': 'navigation', 'main': 'main',
                    'header': 'banner', 'footer': 'contentinfo',
                    'form': 'form', 'table': 'table', 'ul': 'list',
                    'ol': 'list', 'li': 'listitem', 'dialog': 'dialog',
                };
                if (tag === 'input') {
                    const typeMap = {
                        'checkbox': 'checkbox', 'radio': 'radio',
                        'range': 'slider', 'search': 'searchbox',
                        'email': 'textbox', 'password': 'textbox',
                        'tel': 'textbox', 'url': 'textbox',
                        'number': 'spinbutton',
                    };
                    return typeMap[type] || 'textbox';
                }
                return map[tag] || 'generic';
            }

            function getName(el) {
                const ariaLabel = el.getAttribute('aria-label');
                if (ariaLabel) return ariaLabel;
                const ariaLabelledBy = el.getAttribute('aria-labelledby');
                if (ariaLabelledBy) {
                    const labelEl = document.getElementById(ariaLabelledBy);
                    if (labelEl) return labelEl.textContent.trim().slice(0, 100);
                }
                const title = el.getAttribute('title');
                if (title) return title;
                const alt = el.getAttribute('alt');
                if (alt) return alt;
                const placeholder = el.getAttribute('placeholder');
                if (placeholder) return placeholder;
                if (el.childNodes.length === 1 && el.childNodes[0].nodeType === 3) {
                    const text = el.childNodes[0].textContent.trim();
                    if (text.length <= 100) return text;
                }
                return '';
            }

            function isInteractive(el) {
                const tag = el.tagName.toLowerCase();
                const interactiveTags = ['a', 'button', 'input', 'select', 'textarea', 'details', 'summary'];
                if (interactiveTags.includes(tag)) return true;
                const role = el.getAttribute('role');
                const interactiveRoles = ['button', 'link', 'textbox', 'checkbox', 'radio', 'combobox', 'listbox', 'menuitem', 'switch', 'tab', 'slider'];
                if (role && interactiveRoles.includes(role.toLowerCase())) return true;
                if (el.hasAttribute('onclick') || el.hasAttribute('tabindex')) return true;
                const style = getComputedStyle(el);
                if (style.cursor === 'pointer') return true;
                return false;
            }

            function buildNode(el, depth) {
                if (depth > 15) return null;
                if (el.nodeType !== 1) return null;
                if (['SCRIPT', 'STYLE', 'NOSCRIPT', 'META', 'LINK'].includes(el.tagName)) return null;

                const role = getRole(el);
                const name = getName(el);
                const isInput = ['checkbox', 'radio'].includes(role);

                const node = {
                    role: role,
                    name: name,
                    depth: depth,
                    interactive: isInteractive(el),
                    children: []
                };

                if (isInput) {
                    node.checked = el.checked ? 'true' : 'false';
                }
                if (el.disabled) node.disabled = true;
                if (el.getAttribute('aria-expanded') !== null) {
                    node.expanded = el.getAttribute('aria-expanded') === 'true';
                }
                if (el.getAttribute('aria-selected') === 'true') node.selected = true;
                if (el.hasAttribute('aria-required') || el.required) node.required = true;

                // Level for headings
                const tag = el.tagName.toLowerCase();
                if (tag.match(/^h[1-6]$/)) {
                    node.level = parseInt(tag[1]);
                }

                const href = el.getAttribute('href');
                if (href && role === 'link') node.url = href;

                for (const child of el.children) {
                    const childNode = buildNode(child, depth + 1);
                    if (childNode) node.children.push(childNode);
                }

                // Aggregate adjacent text for leaf nodes
                if (node.children.length === 0 && !name) {
                    const text = el.textContent.trim().slice(0, 100);
                    if (text) {
                        node.role = 'StaticText';
                        node.name = text;
                    }
                }

                return node;
            }

            const body = document.body;
            if (!body) return [];
            const root = buildNode(body, 0);
            return root ? [root] : [];
        }""")
        return tree or []
    except Exception as e:
        logger.error(f"JS AX tree fallback failed: {e}")
        return []


# ═══════════════════════════════════════════════════════════════
# TREE BUILDING
# ═══════════════════════════════════════════════════════════════

def _build_tree_from_ax(ax_nodes: List[Dict]) -> Tuple[List[TreeNode], List[int]]:
    """Build a flat tree of TreeNodes from AX tree data.

    Returns:
        (tree_nodes, root_indices)
    """
    tree_nodes: List[TreeNode] = []
    id_to_idx: Dict[str, int] = {}

    for i, node in enumerate(ax_nodes):
        role = node.get("role", "")
        if isinstance(role, dict):
            role = role.get("value", "")

        name = node.get("name", "")
        if isinstance(name, dict):
            name = name.get("value", "")

        # Skip ignored nodes and InlineTextBox
        if node.get("ignored", False) and role != "RootWebArea":
            tree_nodes.append(TreeNode())
            id_to_idx[node.get("nodeId", str(i))] = i
            continue
        if role == "InlineTextBox":
            tree_nodes.append(TreeNode())
            id_to_idx[node.get("nodeId", str(i))] = i
            continue

        # Extract properties
        props = node.get("properties", [])
        level = None
        checked = None
        expanded = None
        selected = None
        disabled = None
        required = None
        value_text = None

        for prop in props:
            pname = prop.get("name", "")
            pvalue = prop.get("value", {})
            if isinstance(pvalue, dict):
                pvalue = pvalue.get("value")

            if pname == "level":
                level = int(pvalue) if pvalue is not None else None
            elif pname == "checked":
                checked = str(pvalue).lower() if pvalue is not None else None
            elif pname == "expanded":
                expanded = bool(pvalue) if pvalue is not None else None
            elif pname == "selected":
                selected = bool(pvalue) if pvalue is not None else None
            elif pname == "disabled":
                disabled = bool(pvalue) if pvalue is not None else None
            elif pname == "required":
                required = bool(pvalue) if pvalue is not None else None
            elif pname == "value":
                if pvalue and str(pvalue).strip():
                    value_text = str(pvalue).strip()

        backend_node_id = node.get("backendDOMNodeId")

        tree_nodes.append(TreeNode(
            role=role,
            name=name,
            level=level,
            checked=checked,
            expanded=expanded,
            selected=selected,
            disabled=disabled,
            required=required,
            value_text=value_text,
            backend_node_id=backend_node_id,
            children=[],
            parent_idx=None,
        ))
        id_to_idx[node.get("nodeId", str(i))] = i

    # Build parent-child relationships
    for i, node in enumerate(ax_nodes):
        child_ids = node.get("childIds", [])
        for cid in child_ids:
            child_idx = id_to_idx.get(cid)
            if child_idx is not None:
                tree_nodes[i].children.append(child_idx)
                tree_nodes[child_idx].parent_idx = i

    # Aggregate adjacent StaticText nodes
    for i, node in enumerate(tree_nodes):
        if not node.role or not node.children:
            continue

        children_indices = list(node.children)
        start = 0
        while start < len(children_indices):
            if tree_nodes[children_indices[start]].role != "StaticText":
                start += 1
                continue

            end = start + 1
            while end < len(children_indices) and tree_nodes[children_indices[end]].role == "StaticText":
                end += 1

            if end > start + 1:
                aggregated = "".join(
                    tree_nodes[children_indices[j]].name for j in range(start, end)
                )
                tree_nodes[children_indices[start]].name = aggregated
                for j in range(start + 1, end):
                    tree_nodes[children_indices[j]].role = ""
                    tree_nodes[children_indices[j]].name = ""

            start = end

        # Deduplicate redundant StaticText
        if (len(children_indices) == 1
            and tree_nodes[children_indices[0]].role == "StaticText"
            and node.name == tree_nodes[children_indices[0]].name):
            tree_nodes[children_indices[0]].role = ""

    # Find root indices
    is_child = [False] * len(tree_nodes)
    for node in tree_nodes:
        for child_idx in node.children:
            is_child[child_idx] = True

    root_indices = [i for i, is_c in enumerate(is_child) if not is_c]

    # Set depths
    def set_depth(idx: int, depth: int):
        tree_nodes[idx].depth = depth
        for child_idx in tree_nodes[idx].children:
            set_depth(child_idx, depth + 1)

    for root in root_indices:
        set_depth(root, 0)

    return tree_nodes, root_indices


# ═══════════════════════════════════════════════════════════════
# CURSOR-INTERACTIVE ELEMENT DETECTION
# ═══════════════════════════════════════════════════════════════

async def find_cursor_interactive_elements(page) -> Dict[int, CursorElementInfo]:
    """Find elements with cursor:pointer, onclick, tabindex, or contenteditable
    that aren't standard interactive elements.

    These are "secretly interactive" — the ARIA tree doesn't mark them as
    interactive, but users can click/focus them.
    """
    try:
        elements = await page.evaluate("""() => {
            const results = [];
            if (!document.body) return results;

            const interactiveRoles = new Set([
                'button', 'link', 'textbox', 'checkbox', 'radio', 'combobox',
                'listbox', 'menuitem', 'menuitemcheckbox', 'menuitemradio',
                'option', 'searchbox', 'slider', 'spinbutton', 'switch',
                'tab', 'treeitem'
            ]);
            const interactiveTags = new Set([
                'a', 'button', 'input', 'select', 'textarea', 'details', 'summary'
            ]);

            const allElements = document.body.querySelectorAll('*');
            for (const el of allElements) {
                if (el.closest && el.closest('[hidden], [aria-hidden="true"]')) continue;

                const tagName = el.tagName.toLowerCase();
                if (interactiveTags.has(tagName)) continue;

                const role = el.getAttribute('role');
                if (role && interactiveRoles.has(role.toLowerCase())) continue;

                const style = getComputedStyle(el);
                const hasCursorPointer = style.cursor === 'pointer';
                const hasOnClick = el.hasAttribute('onclick') || el.onclick !== null;
                const tabIndex = el.getAttribute('tabindex');
                const hasTabIndex = tabIndex !== null && tabIndex !== '-1';
                const ce = el.getAttribute('contenteditable');
                const isEditable = ce === '' || ce === 'true';

                if (!hasCursorPointer && !hasOnClick && !hasTabIndex && !isEditable) continue;

                // Skip inherited cursor:pointer from parent
                if (hasCursorPointer && !hasOnClick && !hasTabIndex && !isEditable) {
                    const parent = el.parentElement;
                    if (parent && getComputedStyle(parent).cursor === 'pointer') continue;
                }

                const text = (el.textContent || '').trim().slice(0, 100);
                const rect = el.getBoundingClientRect();
                if (rect.width === 0 || rect.height === 0) continue;

                // Detect hidden radio/checkbox inputs
                let hiddenInputType = null;
                let hiddenInputChecked = null;
                const hiddenInput = el.querySelector('input[type="radio"], input[type="checkbox"]');
                if (hiddenInput) {
                    const inputStyle = getComputedStyle(hiddenInput);
                    const isHidden = inputStyle.display === 'none' || inputStyle.visibility === 'hidden' || hiddenInput.hidden;
                    if (isHidden) {
                        hiddenInputType = hiddenInput.type;
                        hiddenInputChecked = hiddenInput.indeterminate ? 'mixed' : String(hiddenInput.checked);
                    }
                }

                el.setAttribute('data-__ab-ci', String(results.length));
                results.push({
                    text, tagName,
                    hasOnClick, hasCursorPointer, hasTabIndex, isEditable,
                    hiddenInputType, hiddenInputChecked
                });
            }
            return results;
        }""")

        if not elements:
            return {}

        # Clean up data attributes
        await page.evaluate("""() => {
            const els = document.querySelectorAll('[data-__ab-ci]');
            for (const el of els) el.removeAttribute('data-__ab-ci');
        }""")

        # Build map (using index as key since we can't get backendNodeId from JS)
        result: Dict[int, CursorElementInfo] = {}
        for i, elem in enumerate(elements):
            has_cursor = elem.get("hasCursorPointer", False)
            has_click = elem.get("hasOnClick", False)
            has_tab = elem.get("hasTabIndex", False)
            is_editable = elem.get("isEditable", False)

            if has_cursor or has_click:
                kind = "clickable"
            elif is_editable:
                kind = "editable"
            else:
                kind = "focusable"

            hints = []
            if has_cursor: hints.append("cursor:pointer")
            if has_click: hints.append("onclick")
            if has_tab: hints.append("tabindex")
            if is_editable: hints.append("contenteditable")

            hidden_kind = elem.get("hiddenInputType")
            hidden_checked = elem.get("hiddenInputChecked")

            result[i] = CursorElementInfo(
                kind=kind,
                hints=hints,
                text=elem.get("text", ""),
                hidden_input_kind=hidden_kind,
                hidden_input_checked=hidden_checked,
            )

        return result

    except Exception as e:
        logger.debug(f"Cursor-interactive detection failed: {e}")
        return {}


# ═══════════════════════════════════════════════════════════════
# TREE RENDERING
# ═══════════════════════════════════════════════════════════════

def _render_tree(
    nodes: List[TreeNode],
    idx: int,
    indent: int,
    output: List[str],
    options: SnapshotOptions,
    ref_map: RefMap,
    tracker: Dict[str, int],
    nodes_with_refs: List[Tuple[int, int]],
):
    """Render a tree node to text output."""
    node = nodes[idx]

    # Skip empty/generic nodes
    if not node.role:
        for child in node.children:
            _render_tree(nodes, child, indent, output, options, ref_map, tracker, nodes_with_refs)
        return

    if node.role == "generic" and not node.has_ref and len(node.children) <= 1:
        for child in node.children:
            _render_tree(nodes, child, indent, output, options, ref_map, tracker, nodes_with_refs)
        return

    if node.role == "StaticText":
        cleaned = node.name
        for ch in INVISIBLE_CHARS:
            cleaned = cleaned.replace(ch, "")
        if not cleaned.strip():
            for child in node.children:
                _render_tree(nodes, child, indent, output, options, ref_map, tracker, nodes_with_refs)
            return

    if options.depth is not None and indent > options.depth:
        return

    # Skip RootWebArea/WebArea wrapper
    if node.role in ("RootWebArea", "WebArea"):
        for child in node.children:
            _render_tree(nodes, child, indent, output, options, ref_map, tracker, nodes_with_refs)
        return

    # Interactive mode: skip non-interactive elements
    if options.interactive and not node.has_ref:
        for child in node.children:
            _render_tree(nodes, child, indent, output, options, ref_map, tracker, nodes_with_refs)
        return

    # Build the output line
    prefix = "  " * indent
    line = f"{prefix}- {node.role}"

    # Name
    display_name = node.name
    if not display_name and options.interactive and node.cursor_info:
        display_name = node.cursor_info.text

    if display_name:
        # Clean invisible chars
        for ch in INVISIBLE_CHARS:
            display_name = display_name.replace(ch, "")
        if display_name:
            line += f" {json.dumps(display_name)}"

    # Properties
    attrs = []
    if node.level is not None:
        attrs.append(f"level={node.level}")
    if node.checked is not None:
        attrs.append(f"checked={node.checked}")
    if node.expanded is not None:
        attrs.append(f"expanded={str(node.expanded).lower()}")
    if node.selected:
        attrs.append("selected")
    if node.disabled:
        attrs.append("disabled")
    if node.required:
        attrs.append("required")
    if node.ref_id:
        attrs.append(f"ref={node.ref_id}")
    if node.url:
        attrs.append(f"url={node.url}")

    if attrs:
        line += f" [{', '.join(attrs)}]"

    # Cursor info
    if node.cursor_info:
        line += f" {node.cursor_info.kind} [{', '.join(node.cursor_info.hints)}]"

    # Value
    if node.value_text and node.value_text != node.name:
        line += f": {node.value_text}"

    output.append(line)

    for child in node.children:
        _render_tree(nodes, child, indent + 1, output, options, ref_map, tracker, nodes_with_refs)


def _compact_tree(text: str, interactive: bool) -> str:
    """Remove empty structural elements, keeping only nodes with refs or content."""
    lines = text.split("\n")
    if not lines:
        return ""

    keep = [False] * len(lines)

    for i, line in enumerate(lines):
        if "ref=" in line or ": " in line:
            keep[i] = True
            # Mark ancestors
            my_indent = _count_indent(line)
            for j in range(i - 1, -1, -1):
                ancestor_indent = _count_indent(lines[j])
                if ancestor_indent < my_indent:
                    keep[j] = True
                    if ancestor_indent == 0:
                        break

    result = [line for i, line in enumerate(lines) if keep[i]]
    output = "\n".join(result)

    if not output.strip() and interactive:
        return "(no interactive elements)"
    return output


def _count_indent(line: str) -> int:
    """Count indentation level (2 spaces per level)."""
    trimmed = line.lstrip()
    return (len(line) - len(trimmed)) // 2


# ═══════════════════════════════════════════════════════════════
# MAIN SNAPSHOT FUNCTION
# ═══════════════════════════════════════════════════════════════

async def take_snapshot(
    page,
    options: Optional[SnapshotOptions] = None,
    ref_map: Optional[RefMap] = None,
) -> str:
    """Take an accessibility tree snapshot of the page.

    This is the CORE token-saving function. Instead of sending raw HTML
    (50,000+ chars) to the LLM, this produces a compact semantic tree
    (2,000-5,000 chars) that captures the page structure.

    Args:
        page: Playwright Page object
        options: Snapshot options (interactive, compact, depth, urls)
        ref_map: Optional RefMap to populate with element references

    Returns:
        Compact text representation of the page's accessibility tree.
    """
    if options is None:
        options = SnapshotOptions()
    if ref_map is None:
        ref_map = RefMap()

    # Get the accessibility tree
    ax_nodes = await get_ax_tree(page)

    if not ax_nodes:
        return "(empty page)" if not options.interactive else "(no interactive elements)"

    # Build tree
    tree_nodes, root_indices = _build_tree_from_ax(ax_nodes)

    # Assign refs to interactive/content elements
    tracker: Dict[str, int] = {}  # "role:name" -> count
    nodes_with_refs: List[Tuple[int, int]] = []

    # Find cursor-interactive elements
    cursor_elements = await find_cursor_interactive_elements(page)

    # Promote hidden inputs
    for node in tree_nodes:
        if node.role not in ("LabelText", "generic"):
            continue
        if node.backend_node_id and node.backend_node_id in cursor_elements:
            ci = cursor_elements[node.backend_node_id]
            if ci.hidden_input_kind:
                node.role = ci.hidden_input_kind
                if not node.name and ci.text:
                    node.name = ci.text
                if ci.hidden_input_checked:
                    node.checked = ci.hidden_input_checked

    # Determine which nodes get refs
    for idx, node in enumerate(tree_nodes):
        should_ref = False
        if node.role in INTERACTIVE_ROLES:
            should_ref = True
        elif node.role in CONTENT_ROLES and node.name:
            should_ref = True
        elif node.backend_node_id and node.backend_node_id in cursor_elements:
            should_ref = True

        if should_ref:
            key = f"{node.role}:{node.name}"
            nth = tracker.get(key, 0)
            tracker[key] = nth + 1
            nodes_with_refs.append((idx, nth))

    # Find duplicates for nth disambiguation
    duplicates = {k for k, v in tracker.items() if v > 1}

    # Assign ref IDs
    next_ref = ref_map.next_ref_num()
    for idx, nth in nodes_with_refs:
        node = tree_nodes[idx]
        key = f"{node.role}:{node.name}"
        actual_nth = nth if key in duplicates else None

        ref_id = f"e{next_ref}"
        next_ref += 1

        ref_map.add(
            ref_id=ref_id,
            backend_node_id=node.backend_node_id,
            role=node.role,
            name=node.name,
            nth=actual_nth,
        )

        node.has_ref = True
        node.ref_id = ref_id

        # Attach cursor info
        if node.backend_node_id and node.backend_node_id in cursor_elements:
            node.cursor_info = cursor_elements[node.backend_node_id]

    ref_map.set_next_ref_num(next_ref)

    # Render tree
    output_lines: List[str] = []
    for root_idx in root_indices:
        _render_tree(tree_nodes, root_idx, 0, output_lines, options, ref_map, tracker, nodes_with_refs)

    output = "\n".join(output_lines)

    # Compact mode
    if options.compact:
        output = _compact_tree(output, options.interactive)

    trimmed = output.strip()
    if not trimmed:
        return "(empty page)" if not options.interactive else "(no interactive elements)"

    return trimmed


# ═══════════════════════════════════════════════════════════════
# CONVENIENCE FUNCTIONS
# ═══════════════════════════════════════════════════════════════

async def snapshot_interactive(page, compact: bool = True, depth: Optional[int] = None) -> Tuple[str, RefMap]:
    """Quick snapshot: interactive elements only, compact mode.

    Best for LLM consumption — minimal tokens, all clickable things.

    Returns:
        (snapshot_text, ref_map)
    """
    ref_map = RefMap()
    options = SnapshotOptions(interactive=True, compact=compact, depth=depth)
    text = await take_snapshot(page, options, ref_map)
    return text, ref_map


async def snapshot_full(page, compact: bool = True, depth: Optional[int] = None) -> Tuple[str, RefMap]:
    """Full page snapshot with all content.

    Returns:
        (snapshot_text, ref_map)
    """
    ref_map = RefMap()
    options = SnapshotOptions(compact=compact, depth=depth)
    text = await take_snapshot(page, options, ref_map)
    return text, ref_map


async def snapshot_selector(page, selector: str, compact: bool = True) -> Tuple[str, RefMap]:
    """Snapshot scoped to a CSS selector.

    Returns:
        (snapshot_text, ref_map)
    """
    ref_map = RefMap()
    options = SnapshotOptions(selector=selector, compact=compact)
    text = await take_snapshot(page, options, ref_map)
    return text, ref_map


def format_snapshot_for_llm(snapshot: str, ref_map: RefMap) -> str:
    """Format a snapshot with ref instructions for LLM consumption.

    Adds a header explaining how to use refs (@e1, @e2...) in commands.
    """
    header = """Page snapshot (use @eN refs to interact with elements):
- click @e1 — click element e1
- fill @e2 "text" — fill input e2
- type @e3 "text" — type into e3
- hover @e4 — hover over e4
- get text @e5 — get text from e5

"""
    return header + snapshot


def estimate_token_savings(html_length: int, snapshot_length: int) -> Dict[str, Any]:
    """Estimate token savings from using snapshot vs raw HTML.

    Returns:
        Dict with savings statistics.
    """
    # Rough estimate: 1 token ≈ 4 chars
    html_tokens = html_length // 4
    snapshot_tokens = snapshot_length // 4
    saved = html_tokens - snapshot_tokens
    pct = (saved / html_tokens * 100) if html_tokens > 0 else 0

    return {
        "html_chars": html_length,
        "snapshot_chars": snapshot_length,
        "html_tokens_est": html_tokens,
        "snapshot_tokens_est": snapshot_tokens,
        "tokens_saved_est": saved,
        "savings_pct": round(pct, 1),
    }
