"""Generate professional TikZ diagrams from nodes and edges."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Iterable


DEFAULT_SCALE = 0.035
DEFAULT_NODE_WIDTH = 2.8
DEFAULT_NODE_HEIGHT = 1.1
DEFAULT_COLOR = "ibmblue"

COLOR_PALETTE = {
    "ibmblue": "0F62FE",
    "blue": "0F62FE",
    "cyan": "1192E8",
    "teal": "009D9A",
    "green": "24A148",
    "purple": "8A3FFC",
    "magenta": "D02670",
    "red": "DA1E28",
    "orange": "FF832B",
    "gray": "6F6F6F",
    "black": "161616",
}

NODE_STYLE_BY_TYPE = {
    "rectangle": "processNode",
    "square": "processNode",
    "process": "processNode",
    "block": "processNode",
    "circle": "circleNode",
    "decision": "decisionNode",
    "diamond": "decisionNode",
    "database": "databaseNode",
    "entity": "entityNode",
    "uml_class": "classNode",
    "input": "inputNode",
    "output": "inputNode",
}


@dataclass(frozen=True)
class TikzNode:
    """Normalized node model used by the deterministic TikZ renderer."""

    id: str
    label: str
    type: str
    x: float
    y: float
    width: float
    height: float
    color: str


@dataclass(frozen=True)
class TikzEdge:
    """Normalized edge model used by the deterministic TikZ renderer."""

    id: str
    source: str | None
    target: str | None
    label: str
    type: str
    color: str
    points: tuple[tuple[float, float], ...]


def generate_tikz(nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> str:
    """Generate self-contained TikZ code from diagram nodes and edges."""
    normalized_nodes = normalize_nodes(nodes)
    normalized_edges = normalize_edges(edges)

    lines = [
        "\\begin{tikzpicture}[",
        "  >=Stealth,",
        "  node distance=1.8cm and 2.4cm,",
        "  every node/.style={font=\\sffamily\\small},",
        "]",
        *render_color_definitions(normalized_nodes, normalized_edges),
        *render_style_definitions(),
        "",
        *render_nodes(normalized_nodes),
        "",
        *render_edges(normalized_edges, normalized_nodes),
        "\\end{tikzpicture}",
    ]

    return "\n".join(line for line in lines if line is not None).strip() + "\n"


def normalize_nodes(nodes: Iterable[dict[str, Any]]) -> list[TikzNode]:
    """Normalize arbitrary node dictionaries into TikzNode objects."""
    normalized: list[TikzNode] = []

    for index, node in enumerate(nodes, start=1):
        node_id = sanitize_identifier(str(node.get("id") or f"node_{index}"))
        node_type = str(node.get("type") or "rectangle").strip().lower()
        label = str(node.get("label") or node.get("name") or node_id.replace("_", " ").title())
        color = normalize_color(str(node.get("color") or DEFAULT_COLOR))

        x, y = extract_position(node, index)
        width, height = extract_size(node)

        normalized.append(
            TikzNode(
                id=node_id,
                label=label,
                type=node_type,
                x=x,
                y=y,
                width=width,
                height=height,
                color=color,
            )
        )

    return normalized


def normalize_edges(edges: Iterable[dict[str, Any]]) -> list[TikzEdge]:
    """Normalize arbitrary edge dictionaries into TikzEdge objects."""
    normalized: list[TikzEdge] = []

    for index, edge in enumerate(edges, start=1):
        edge_id = sanitize_identifier(str(edge.get("id") or f"edge_{index}"))
        source = edge.get("source") or edge.get("from")
        target = edge.get("target") or edge.get("to")
        label = str(edge.get("label") or "")
        edge_type = str(edge.get("type") or "arrow").strip().lower()
        color = normalize_color(str(edge.get("color") or "black"))
        points = extract_edge_points(edge)

        normalized.append(
            TikzEdge(
                id=edge_id,
                source=sanitize_identifier(str(source)) if source else None,
                target=sanitize_identifier(str(target)) if target else None,
                label=label,
                type=edge_type,
                color=color,
                points=points,
            )
        )

    return normalized


def render_color_definitions(nodes: list[TikzNode], edges: list[TikzEdge]) -> list[str]:
    """Render xcolor definitions for colors used by the diagram."""
    colors = {node.color for node in nodes} | {edge.color for edge in edges}
    lines = []

    for color in sorted(colors):
        hex_value = COLOR_PALETTE.get(color)
        if hex_value:
            lines.append(f"\\definecolor{{{color}}}{{HTML}}{{{hex_value}}}")

    return lines


def render_style_definitions() -> list[str]:
    """Render reusable TikZ styles."""
    return [
        "\\tikzset{",
        "  processNode/.style={draw=#1, rounded corners=2pt, very thick, fill=#1!8, minimum width=2.8cm, minimum height=1.1cm, align=center, inner sep=6pt},",
        "  processNode/.default=ibmblue,",
        "  circleNode/.style={draw=#1, circle, very thick, fill=#1!8, minimum size=1.2cm, align=center, inner sep=5pt},",
        "  circleNode/.default=ibmblue,",
        "  decisionNode/.style={draw=#1, diamond, aspect=2.2, very thick, fill=#1!8, minimum width=2.6cm, minimum height=1.25cm, align=center, inner sep=3pt},",
        "  decisionNode/.default=ibmblue,",
        "  databaseNode/.style={draw=#1, cylinder, shape border rotate=90, aspect=0.25, very thick, fill=#1!8, minimum width=2.6cm, minimum height=1.3cm, align=center},",
        "  databaseNode/.default=ibmblue,",
        "  entityNode/.style={draw=#1, rounded corners=1pt, very thick, fill=#1!6, minimum width=2.8cm, minimum height=1.15cm, align=center, inner sep=6pt},",
        "  entityNode/.default=ibmblue,",
        "  classNode/.style={draw=#1, rectangle split, rectangle split parts=3, very thick, fill=#1!6, minimum width=3.1cm, align=left, inner sep=5pt},",
        "  classNode/.default=ibmblue,",
        "  inputNode/.style={draw=#1, trapezium, trapezium left angle=70, trapezium right angle=110, very thick, fill=#1!8, minimum width=2.8cm, minimum height=1.1cm, align=center, inner sep=6pt},",
        "  inputNode/.default=ibmblue,",
        "  connector/.style={draw=#1, very thick, -Stealth},",
        "  connector/.default=black,",
        "  softConnector/.style={draw=#1, thick, dashed, -Stealth},",
        "  softConnector/.default=black,",
        "}",
    ]


def render_nodes(nodes: list[TikzNode]) -> list[str]:
    """Render TikZ node declarations."""
    if not nodes:
        return ["% No nodes supplied."]

    return [render_node(node) for node in nodes]


def render_node(node: TikzNode) -> str:
    """Render one normalized node as a TikZ node command."""
    style = NODE_STYLE_BY_TYPE.get(node.type, "processNode")
    label = escape_latex(node.label)
    return (
        f"\\node[{style}={node.color}, minimum width={node.width:.2f}cm, "
        f"minimum height={node.height:.2f}cm] ({node.id}) "
        f"at ({node.x:.2f}, {node.y:.2f}) {{{label}}};"
    )


def render_edges(edges: list[TikzEdge], nodes: list[TikzNode]) -> list[str]:
    """Render TikZ edge declarations."""
    if not edges:
        return ["% No edges supplied."]

    node_ids = {node.id for node in nodes}
    rendered: list[str] = []

    for edge in edges:
        if edge.source in node_ids and edge.target in node_ids:
            rendered.append(render_node_edge(edge))
        elif edge.points:
            rendered.append(render_point_edge(edge))

    return rendered or ["% No renderable edges supplied."]


def render_node_edge(edge: TikzEdge) -> str:
    """Render an edge that connects two named nodes."""
    connector_style = "softConnector" if edge.type in {"dashed", "dependency"} else "connector"
    label = render_edge_label(edge.label)
    return f"\\draw[{connector_style}={edge.color}] ({edge.source}) -- {label}({edge.target});"


def render_point_edge(edge: TikzEdge) -> str:
    """Render an edge from explicit point coordinates."""
    connector_style = "softConnector" if edge.type in {"dashed", "dependency"} else "connector"
    coordinates = " -- ".join(f"({x:.2f}, {y:.2f})" for x, y in edge.points)
    label = render_edge_label(edge.label)
    if label and len(edge.points) >= 2:
        first_point = f"({edge.points[0][0]:.2f}, {edge.points[0][1]:.2f})"
        remaining = " -- ".join(f"({x:.2f}, {y:.2f})" for x, y in edge.points[1:])
        return f"\\draw[{connector_style}={edge.color}] {first_point} -- {label}{remaining};"
    return f"\\draw[{connector_style}={edge.color}] {coordinates};"


def render_edge_label(label: str) -> str:
    """Render an optional label for a connector edge."""
    if not label.strip():
        return ""

    return f"node[midway, fill=white, inner sep=2pt] {{{escape_latex(label)}}} "


def extract_position(node: dict[str, Any], index: int) -> tuple[float, float]:
    """Extract or infer node position in TikZ coordinates."""
    if "position" in node and isinstance(node["position"], dict):
        position = node["position"]
        return _scaled_point(position.get("x", 0), position.get("y", 0))

    if "center" in node and isinstance(node["center"], dict):
        center = node["center"]
        return _scaled_point(center.get("x", 0), center.get("y", 0))

    if "bbox" in node and isinstance(node["bbox"], dict):
        bbox = node["bbox"]
        x = float(bbox.get("x", 0)) + float(bbox.get("width", 0)) / 2
        y = float(bbox.get("y", 0)) + float(bbox.get("height", 0)) / 2
        return _scaled_point(x, y)

    row = (index - 1) // 3
    column = (index - 1) % 3
    return (column * 3.8, -row * 2.2)


def extract_size(node: dict[str, Any]) -> tuple[float, float]:
    """Extract node size and convert it to centimeters."""
    width = node.get("width")
    height = node.get("height")

    if "bbox" in node and isinstance(node["bbox"], dict):
        width = node["bbox"].get("width", width)
        height = node["bbox"].get("height", height)

    try:
        parsed_width = max(DEFAULT_NODE_WIDTH, float(width) * DEFAULT_SCALE)
    except (TypeError, ValueError):
        parsed_width = DEFAULT_NODE_WIDTH

    try:
        parsed_height = max(DEFAULT_NODE_HEIGHT, float(height) * DEFAULT_SCALE)
    except (TypeError, ValueError):
        parsed_height = DEFAULT_NODE_HEIGHT

    return (min(parsed_width, 5.8), min(parsed_height, 3.2))


def extract_edge_points(edge: dict[str, Any]) -> tuple[tuple[float, float], ...]:
    """Extract free-form edge points from dictionaries."""
    raw_points = edge.get("points")
    if not isinstance(raw_points, list):
        return ()

    points: list[tuple[float, float]] = []
    for point in raw_points:
        if isinstance(point, dict):
            points.append(_scaled_point(point.get("x", 0), point.get("y", 0)))
        elif isinstance(point, (list, tuple)) and len(point) >= 2:
            points.append(_scaled_point(point[0], point[1]))

    return tuple(points)


def normalize_color(color: str) -> str:
    """Normalize color names to a safe TikZ color identifier."""
    normalized = sanitize_identifier(color.lower())
    return normalized if normalized in COLOR_PALETTE else DEFAULT_COLOR


def sanitize_identifier(value: str) -> str:
    """Convert arbitrary IDs into TikZ-safe identifiers."""
    sanitized = re.sub(r"[^a-zA-Z0-9_]+", "_", value.strip())
    sanitized = sanitized.strip("_")
    if not sanitized:
        return "node"
    if sanitized[0].isdigit():
        sanitized = f"n_{sanitized}"
    return sanitized


def escape_latex(value: str) -> str:
    """Escape common LaTeX-sensitive characters in labels."""
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }

    return "".join(replacements.get(character, character) for character in value)


def _scaled_point(x_value: Any, y_value: Any) -> tuple[float, float]:
    """Convert image-space coordinates to TikZ coordinates."""
    try:
        x = float(x_value) * DEFAULT_SCALE
    except (TypeError, ValueError):
        x = 0.0

    try:
        y = -float(y_value) * DEFAULT_SCALE
    except (TypeError, ValueError):
        y = 0.0

    return (x, y)
