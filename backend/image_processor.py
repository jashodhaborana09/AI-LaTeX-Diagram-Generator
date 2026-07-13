"""OpenCV diagram image processing pipeline."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cv2
import numpy as np


MIN_NODE_AREA = 400
MAX_NODE_AREA_RATIO = 0.65
CONNECTION_DISTANCE_RATIO = 0.08


@dataclass(frozen=True)
class ShapeNode:
    """Detected diagram node and bounding box metadata."""

    id: str
    type: str
    x: int
    y: int
    width: int
    height: int
    confidence: float

    @property
    def center(self) -> tuple[int, int]:
        return (self.x + self.width // 2, self.y + self.height // 2)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "bbox": {
                "x": self.x,
                "y": self.y,
                "width": self.width,
                "height": self.height,
            },
            "center": {
                "x": self.center[0],
                "y": self.center[1],
            },
            "confidence": round(self.confidence, 3),
        }


@dataclass(frozen=True)
class DiagramEdge:
    """Detected connector metadata between diagram nodes."""

    id: str
    source: str | None
    target: str | None
    type: str
    points: list[tuple[int, int]]
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source": self.source,
            "target": self.target,
            "type": self.type,
            "points": [{"x": x, "y": y} for x, y in self.points],
            "confidence": round(self.confidence, 3),
        }


def process_image(image_path: str | Path) -> dict[str, list[dict[str, Any]]]:
    """Process a diagram image and return detected nodes and edges."""
    image = read_image(image_path)
    grayscale = convert_grayscale(image)
    thresholded = threshold_image(grayscale)
    contours = detect_contours(thresholded)

    rectangles = detect_rectangles(contours, image.shape)
    circles = detect_circles(grayscale, image.shape)
    nodes = merge_nodes(rectangles + circles)

    arrows = detect_arrows(thresholded, image.shape)
    edges = estimate_connections(arrows, nodes)

    return {
        "nodes": [node.to_dict() for node in nodes],
        "edges": [edge.to_dict() for edge in edges],
    }


def read_image(image_path: str | Path) -> np.ndarray:
    """Read an image from disk."""
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image does not exist: {path}")

    image = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError(f"Unable to read image: {path}")

    return image


def convert_grayscale(image: np.ndarray) -> np.ndarray:
    """Convert a BGR image to grayscale."""
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def threshold_image(grayscale: np.ndarray) -> np.ndarray:
    """Threshold a grayscale image for shape and line detection."""
    blurred = cv2.GaussianBlur(grayscale, (5, 5), 0)
    thresholded = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        31,
        8,
    )
    kernel = np.ones((3, 3), np.uint8)
    return cv2.morphologyEx(thresholded, cv2.MORPH_CLOSE, kernel, iterations=1)


def detect_contours(thresholded: np.ndarray) -> list[np.ndarray]:
    """Detect external contours from a thresholded image."""
    contours, _hierarchy = cv2.findContours(
        thresholded,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE,
    )
    return list(contours)


def detect_rectangles(contours: list[np.ndarray], image_shape: tuple[int, ...]) -> list[ShapeNode]:
    """Detect rectangular nodes from contours."""
    image_area = image_shape[0] * image_shape[1]
    nodes: list[ShapeNode] = []

    for contour in contours:
        area = cv2.contourArea(contour)
        if not _is_valid_node_area(area, image_area):
            continue

        perimeter = cv2.arcLength(contour, True)
        approximation = cv2.approxPolyDP(contour, 0.03 * perimeter, True)
        if len(approximation) != 4 or not cv2.isContourConvex(approximation):
            continue

        x, y, width, height = cv2.boundingRect(approximation)
        if not _has_reasonable_dimensions(width, height):
            continue

        rectangularity = area / float(width * height)
        if rectangularity < 0.65:
            continue

        node_type = "rectangle" if abs(width - height) > min(width, height) * 0.15 else "square"
        nodes.append(
            ShapeNode(
                id=f"node_{len(nodes) + 1}",
                type=node_type,
                x=int(x),
                y=int(y),
                width=int(width),
                height=int(height),
                confidence=min(0.98, rectangularity),
            )
        )

    return nodes


def detect_circles(grayscale: np.ndarray, image_shape: tuple[int, ...]) -> list[ShapeNode]:
    """Detect circular nodes using Hough circles."""
    height, width = image_shape[:2]
    min_radius = max(8, min(width, height) // 80)
    max_radius = max(min_radius + 2, min(width, height) // 5)

    blurred = cv2.medianBlur(grayscale, 5)
    circles = cv2.HoughCircles(
        blurred,
        cv2.HOUGH_GRADIENT,
        dp=1.2,
        minDist=max(24, min(width, height) // 12),
        param1=80,
        param2=28,
        minRadius=min_radius,
        maxRadius=max_radius,
    )

    if circles is None:
        return []

    nodes: list[ShapeNode] = []
    for circle in np.round(circles[0, :]).astype("int"):
        center_x, center_y, radius = circle.tolist()
        diameter = radius * 2
        if diameter < 12:
            continue

        nodes.append(
            ShapeNode(
                id=f"circle_{len(nodes) + 1}",
                type="circle",
                x=int(center_x - radius),
                y=int(center_y - radius),
                width=int(diameter),
                height=int(diameter),
                confidence=0.82,
            )
        )

    return nodes


def detect_arrows(thresholded: np.ndarray, image_shape: tuple[int, ...]) -> list[list[tuple[int, int]]]:
    """Detect likely arrow or connector strokes as line segments."""
    height, width = image_shape[:2]
    min_line_length = max(24, min(width, height) // 14)
    max_line_gap = max(8, min(width, height) // 80)

    edges = cv2.Canny(thresholded, 50, 150, apertureSize=3)
    lines = cv2.HoughLinesP(
        edges,
        rho=1,
        theta=np.pi / 180,
        threshold=35,
        minLineLength=min_line_length,
        maxLineGap=max_line_gap,
    )

    if lines is None:
        return []

    arrows: list[list[tuple[int, int]]] = []
    for line in lines:
        x1, y1, x2, y2 = line[0].tolist()
        if _line_length((x1, y1), (x2, y2)) < min_line_length:
            continue
        arrows.append([(int(x1), int(y1)), (int(x2), int(y2))])

    return _deduplicate_lines(arrows)


def estimate_connections(
    arrows: list[list[tuple[int, int]]],
    nodes: list[ShapeNode],
) -> list[DiagramEdge]:
    """Estimate source and target nodes for detected connector lines."""
    if not arrows:
        return []

    max_distance = _connection_distance(nodes)
    edges: list[DiagramEdge] = []

    for arrow in arrows:
        start, end = arrow[0], arrow[-1]
        source = _nearest_node(start, nodes, max_distance)
        target = _nearest_node(end, nodes, max_distance)

        if source is None and target is None:
            continue

        confidence = 0.55
        if source is not None:
            confidence += 0.18
        if target is not None:
            confidence += 0.18
        if source is not None and target is not None and source.id != target.id:
            confidence += 0.09

        edges.append(
            DiagramEdge(
                id=f"edge_{len(edges) + 1}",
                source=source.id if source else None,
                target=target.id if target else None,
                type="arrow" if source and target and source.id != target.id else "connector",
                points=arrow,
                confidence=min(confidence, 0.95),
            )
        )

    return edges


def merge_nodes(nodes: list[ShapeNode]) -> list[ShapeNode]:
    """Merge overlapping node detections from rectangle and circle detectors."""
    sorted_nodes = sorted(nodes, key=lambda node: node.confidence, reverse=True)
    merged: list[ShapeNode] = []

    for node in sorted_nodes:
        if any(_intersection_over_union(node, existing) > 0.45 for existing in merged):
            continue
        merged.append(node)

    merged.sort(key=lambda node: (node.y, node.x))
    return [
        ShapeNode(
            id=f"node_{index + 1}",
            type=node.type,
            x=node.x,
            y=node.y,
            width=node.width,
            height=node.height,
            confidence=node.confidence,
        )
        for index, node in enumerate(merged)
    ]


def _is_valid_node_area(area: float, image_area: int) -> bool:
    """Return True when a contour area is plausible for a diagram node."""
    return MIN_NODE_AREA <= area <= image_area * MAX_NODE_AREA_RATIO


def _has_reasonable_dimensions(width: int, height: int) -> bool:
    """Return True when a bounding box has plausible node dimensions."""
    if width < 18 or height < 18:
        return False

    aspect_ratio = width / float(height)
    return 0.2 <= aspect_ratio <= 5.0


def _line_length(start: tuple[int, int], end: tuple[int, int]) -> float:
    """Return Euclidean distance between two image points."""
    return math.dist(start, end)


def _deduplicate_lines(lines: list[list[tuple[int, int]]]) -> list[list[tuple[int, int]]]:
    """Remove near-duplicate connector line detections."""
    unique: list[list[tuple[int, int]]] = []

    for line in lines:
        start, end = line
        duplicate = False
        for existing in unique:
            existing_start, existing_end = existing
            same_direction = (
                _line_length(start, existing_start) < 12
                and _line_length(end, existing_end) < 12
            )
            opposite_direction = (
                _line_length(start, existing_end) < 12
                and _line_length(end, existing_start) < 12
            )
            if same_direction or opposite_direction:
                duplicate = True
                break

        if not duplicate:
            unique.append(line)

    return unique


def _connection_distance(nodes: list[ShapeNode]) -> float:
    """Calculate the maximum distance for linking line endpoints to nodes."""
    if not nodes:
        return 0.0

    max_extent = max(max(node.width, node.height) for node in nodes)
    return max(32.0, max_extent * (1.0 + CONNECTION_DISTANCE_RATIO))


def _nearest_node(
    point: tuple[int, int],
    nodes: list[ShapeNode],
    max_distance: float,
) -> ShapeNode | None:
    """Return the nearest node to a point within the configured distance."""
    nearest: ShapeNode | None = None
    nearest_distance = float("inf")

    for node in nodes:
        distance = _distance_to_box(point, node)
        if distance < nearest_distance:
            nearest = node
            nearest_distance = distance

    if nearest is None or nearest_distance > max_distance:
        return None

    return nearest


def _distance_to_box(point: tuple[int, int], node: ShapeNode) -> float:
    """Return the distance from a point to a node bounding box."""
    px, py = point
    left = node.x
    right = node.x + node.width
    top = node.y
    bottom = node.y + node.height

    dx = max(left - px, 0, px - right)
    dy = max(top - py, 0, py - bottom)
    return math.hypot(dx, dy)


def _intersection_over_union(first: ShapeNode, second: ShapeNode) -> float:
    """Return the intersection-over-union score for two node boxes."""
    first_x2 = first.x + first.width
    first_y2 = first.y + first.height
    second_x2 = second.x + second.width
    second_y2 = second.y + second.height

    inter_x1 = max(first.x, second.x)
    inter_y1 = max(first.y, second.y)
    inter_x2 = min(first_x2, second_x2)
    inter_y2 = min(first_y2, second_y2)

    inter_width = max(0, inter_x2 - inter_x1)
    inter_height = max(0, inter_y2 - inter_y1)
    intersection = inter_width * inter_height

    first_area = first.width * first.height
    second_area = second.width * second.height
    union = first_area + second_area - intersection

    return intersection / union if union else 0.0
