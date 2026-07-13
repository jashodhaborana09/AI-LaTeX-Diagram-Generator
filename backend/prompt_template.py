"""Reusable prompt templates for IBM Granite TikZ generation."""

from __future__ import annotations

from dataclasses import dataclass


SUPPORTED_DIAGRAM_TYPES = {
    "flowchart": "Flowcharts with clear process steps, decisions, loops, and directional arrows.",
    "block_diagram": "Block diagrams with grouped components, interfaces, inputs, outputs, and signal flow.",
    "uml": "UML diagrams such as class, sequence, component, and use-case diagrams.",
    "er_diagram": "Entity relationship diagrams with entities, attributes, keys, and relationships.",
    "architecture": "Architecture diagrams with services, layers, APIs, databases, and deployment boundaries.",
    "decision_tree": "Decision trees with branching conditions, outcomes, and readable hierarchy.",
    "neural_network": "Neural network diagrams with layers, nodes, tensor flow, labels, and dimensions.",
    "general": "General academic diagrams using precise TikZ geometry and publication-quality styling.",
}


@dataclass(frozen=True)
class TikzPromptRequest:
    """Normalized prompt request for TikZ prompt construction."""

    prompt: str
    diagram_type: str = "general"


def build_granite_tikz_prompt(prompt: str, diagram_type: str = "general") -> str:
    """Build a strict IBM Granite prompt for generating publication-quality TikZ."""
    request = TikzPromptRequest(
        prompt=_validate_prompt(prompt),
        diagram_type=_normalize_diagram_type(diagram_type),
    )
    diagram_guidance = SUPPORTED_DIAGRAM_TYPES[request.diagram_type]

    return f"""You are an expert LaTeX TikZ author for academic research publications.

Your task is to convert the user's diagram request into professional, compilable TikZ code.

Output contract:
- Return ONLY TikZ code.
- Do not include explanations.
- Do not include Markdown code fences.
- Do not include prose before or after the TikZ.
- Start with \\begin{{tikzpicture}}.
- End with \\end{{tikzpicture}}.

Quality rules:
- Produce publication-quality visual structure suitable for papers, theses, and technical reports.
- Use clean geometry, consistent spacing, readable labels, and balanced alignment.
- Prefer semantic styles declared inside the tikzpicture with \\tikzstyle or \\tikzset.
- Use professional colors sparingly and ensure the diagram remains readable in grayscale.
- Use arrows, labels, grouping boxes, legends, and annotations only when they clarify the research idea.
- Avoid decorative clutter.
- Avoid overlapping text, nodes, arrows, and labels.
- Escape LaTeX-sensitive characters when needed.
- Keep the code self-contained inside the tikzpicture environment.

Supported diagram families:
- Flowcharts
- Block diagrams
- UML
- ER diagrams
- Architecture diagrams
- Decision Trees
- Neural Networks

Requested diagram type:
{request.diagram_type}

Diagram-specific guidance:
{diagram_guidance}

User request:
{request.prompt}
"""


def supported_diagram_types() -> tuple[str, ...]:
    """Return supported diagram type identifiers."""
    return tuple(SUPPORTED_DIAGRAM_TYPES.keys())


def _validate_prompt(prompt: str) -> str:
    """Validate and trim a prompt string."""
    if not isinstance(prompt, str):
        raise TypeError("prompt must be a string.")

    clean_prompt = prompt.strip()
    if not clean_prompt:
        raise ValueError("prompt must not be empty.")

    return clean_prompt


def _normalize_diagram_type(diagram_type: str) -> str:
    """Normalize user-supplied diagram type aliases."""
    if not isinstance(diagram_type, str):
        return "general"

    normalized = diagram_type.strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "block": "block_diagram",
        "blocks": "block_diagram",
        "entity_relationship": "er_diagram",
        "erd": "er_diagram",
        "er": "er_diagram",
        "system_architecture": "architecture",
        "architecture_diagram": "architecture",
        "decision": "decision_tree",
        "tree": "decision_tree",
        "nn": "neural_network",
        "neural_net": "neural_network",
        "network": "neural_network",
    }

    normalized = aliases.get(normalized, normalized)
    if normalized not in SUPPORTED_DIAGRAM_TYPES:
        return "general"

    return normalized
