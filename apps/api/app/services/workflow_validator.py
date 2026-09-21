"""Workflow graph JSON validator."""

from typing import Any

ALLOWED_NODE_TYPES = {
    "input", "retrieve", "compose_prompt", "llm_generate", "output",
    "parameter_extract", "http_request", "if_else", "answer", "code_execute",
    # report / form nodes (0024): call a registered tool, render a document
    "tool_call", "render_document",
}


class ValidationError(Exception):
    """Raised when graph_json fails validation."""
    pass


def validate_graph(graph_json: dict[str, Any]) -> None:
    """Validate a workflow graph JSON.

    Rules:
      1. Must have 'nodes' and 'edges' arrays
      2. Exactly 1 input node, exactly 1 output node
      3. Only supported node types
      4. Graph must be a DAG (no cycles)
      5. Must have a path from input → output
      6. MVP: linear chain (each node max 1 outgoing edge)
    """
    nodes = graph_json.get("nodes", [])
    edges = graph_json.get("edges", [])

    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise ValidationError("graph_json must contain 'nodes' and 'edges' arrays")

    if len(nodes) == 0:
        raise ValidationError("Workflow must have at least one node")

    # Check node types
    node_ids = set()
    node_types: dict[str, str] = {}  # id -> type
    for node in nodes:
        nid = node.get("id")
        ntype = node.get("type")
        if not nid or not ntype:
            raise ValidationError("Each node must have 'id' and 'type'")
        if ntype not in ALLOWED_NODE_TYPES:
            raise ValidationError(f"Unknown node type '{ntype}'. Allowed: {ALLOWED_NODE_TYPES}")
        node_ids.add(nid)
        node_types[nid] = ntype

    # Exactly 1 input and 1 output
    input_nodes = [n for n in nodes if n["type"] == "input"]
    output_nodes = [n for n in nodes if n["type"] == "output"]

    if len(input_nodes) != 1:
        raise ValidationError(f"Must have exactly 1 input node, found {len(input_nodes)}")
    if len(output_nodes) != 1:
        raise ValidationError(f"Must have exactly 1 output node, found {len(output_nodes)}")

    # Build adjacency list
    adj: dict[str, list[str]] = {nid: [] for nid in node_ids}
    for edge in edges:
        src = edge.get("source")
        tgt = edge.get("target")
        if src not in node_ids or tgt not in node_ids:
            raise ValidationError(f"Edge references unknown node: {src} -> {tgt}")
        adj[src].append(tgt)

    # Linear chain — max 1 outgoing edge, except if_else (max 2)
    for nid, targets in adj.items():
        max_out = 2 if node_types.get(nid) == "if_else" else 1
        if len(targets) > max_out:
            raise ValidationError(f"Node '{nid}' has {len(targets)} outgoing edges (max {max_out})")

    # DAG check (cycle detection via DFS)
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {nid: WHITE for nid in node_ids}

    def has_cycle(u: str) -> bool:
        color[u] = GRAY
        for v in adj[u]:
            if color[v] == GRAY:
                return True
            if color[v] == WHITE and has_cycle(v):
                return True
        color[u] = BLACK
        return False

    for nid in node_ids:
        if color[nid] == WHITE:
            if has_cycle(nid):
                raise ValidationError("Graph contains a cycle — must be a DAG")

    # Path from input → output (BFS)
    input_id = input_nodes[0]["id"]
    output_id = output_nodes[0]["id"]

    visited = set()
    queue = [input_id]
    visited.add(input_id)
    while queue:
        current = queue.pop(0)
        for neighbor in adj[current]:
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)

    if output_id not in visited:
        raise ValidationError("No path from input node to output node")
