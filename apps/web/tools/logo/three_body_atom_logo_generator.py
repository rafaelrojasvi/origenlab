"""
Three-Body Atom Logo Generator
------------------------------
Generates a mathematical logo using:
1. a real 3-body gravitational simulation,
2. logo-safe smoothing and simplification,
3. atom-like orbit overlays,
4. SVG + PNG export.

Run:
    python three_body_atom_logo_generator.py

Output:
    ./outputs/three_body_atom_logo.svg
    ./outputs/three_body_atom_logo.png
    ./outputs/three_body_atom_logo_dark.svg
    ./outputs/three_body_atom_logo_dark.png

Dependencies:
    pip install numpy matplotlib
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Literal
import math
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, Ellipse


Theme = Literal["light", "dark"]
Variant = Literal["figure8_atom", "chaotic_atom", "minimal_atom"]


@dataclass
class BodyState:
    position: np.ndarray  # shape: (2,)
    velocity: np.ndarray  # shape: (2,)
    mass: float = 1.0


@dataclass
class LogoConfig:
    brand_name: str = "ORIGENLAB"
    tagline: str = "mathematical systems"
    variant: Variant = "figure8_atom"
    theme: Theme = "light"
    steps: int = 8500
    dt: float = 0.0035
    grav_const: float = 1.0
    softening: float = 0.015
    trail_stride: int = 5
    smooth_rounds: int = 2
    canvas_size: float = 8.0
    show_wordmark: bool = True
    show_tagline: bool = False
    export_dpi: int = 300


# -----------------------------
# Physics
# -----------------------------

def acceleration(positions: np.ndarray, masses: np.ndarray, g: float, softening: float) -> np.ndarray:
    """Compute gravitational acceleration for each body in 2D."""
    n = len(positions)
    acc = np.zeros_like(positions, dtype=float)

    for i in range(n):
        for j in range(n):
            if i == j:
                continue

            delta = positions[j] - positions[i]
            dist_sq = float(np.dot(delta, delta)) + softening**2
            inv_dist_cube = 1.0 / (dist_sq ** 1.5)
            acc[i] += g * masses[j] * delta * inv_dist_cube

    return acc


def simulate_three_body(
    bodies: list[BodyState],
    steps: int,
    dt: float,
    g: float,
    softening: float,
) -> np.ndarray:
    """
    Velocity-Verlet integration.

    Returns:
        positions_over_time: shape (steps, bodies, 2)
    """
    positions = np.array([b.position for b in bodies], dtype=float)
    velocities = np.array([b.velocity for b in bodies], dtype=float)
    masses = np.array([b.mass for b in bodies], dtype=float)

    history = np.zeros((steps, len(bodies), 2), dtype=float)
    acc = acceleration(positions, masses, g, softening)

    for step in range(steps):
        history[step] = positions

        positions = positions + velocities * dt + 0.5 * acc * dt * dt
        new_acc = acceleration(positions, masses, g, softening)
        velocities = velocities + 0.5 * (acc + new_acc) * dt
        acc = new_acc

    return history


# -----------------------------
# Initial conditions
# -----------------------------

def initial_conditions(variant: Variant) -> list[BodyState]:
    """
    Initial conditions are chosen for logo aesthetics.

    figure8_atom:
        Uses the famous equal-mass figure-eight choreography initial conditions.
    chaotic_atom:
        A slightly perturbed version that creates more chaotic, atomic-looking trails.
    minimal_atom:
        Stable-ish, cleaner motion for a simpler mark.
    """
    if variant == "figure8_atom":
        return [
            BodyState(np.array([0.97000436, -0.24308753]), np.array([0.4662036850, 0.4323657300]), 1.0),
            BodyState(np.array([-0.97000436, 0.24308753]), np.array([0.4662036850, 0.4323657300]), 1.0),
            BodyState(np.array([0.0, 0.0]), np.array([-0.93240737, -0.86473146]), 1.0),
        ]

    if variant == "chaotic_atom":
        return [
            BodyState(np.array([0.92, -0.25]), np.array([0.48, 0.44]), 1.00),
            BodyState(np.array([-1.05, 0.20]), np.array([0.42, 0.40]), 0.92),
            BodyState(np.array([0.04, 0.05]), np.array([-0.88, -0.78]), 1.08),
        ]

    if variant == "minimal_atom":
        return [
            BodyState(np.array([1.1, 0.0]), np.array([0.0, 0.58]), 1.0),
            BodyState(np.array([-0.55, 0.95]), np.array([-0.50, -0.29]), 1.0),
            BodyState(np.array([-0.55, -0.95]), np.array([0.50, -0.29]), 1.0),
        ]

    raise ValueError(f"Unknown variant: {variant}")


# -----------------------------
# Geometry utilities
# -----------------------------

def normalize_paths(paths: list[np.ndarray], target_radius: float = 2.25) -> list[np.ndarray]:
    """Center and scale all paths together."""
    all_points = np.vstack(paths)
    center = all_points.mean(axis=0)
    centered = [p - center for p in paths]
    max_radius = max(float(np.linalg.norm(p, axis=1).max()) for p in centered)
    scale = target_radius / max_radius if max_radius > 0 else 1.0
    return [p * scale for p in centered]


def rotate(points: np.ndarray, angle_degrees: float) -> np.ndarray:
    angle = math.radians(angle_degrees)
    matrix = np.array(
        [
            [math.cos(angle), -math.sin(angle)],
            [math.sin(angle), math.cos(angle)],
        ]
    )
    return points @ matrix.T


def chaikin_smooth(points: np.ndarray, rounds: int = 2, closed: bool = False) -> np.ndarray:
    """
    Chaikin corner-cutting to make simulation trails more logo-like.
    This turns noisy physics trails into smooth vector curves.
    """
    result = points.copy()

    for _ in range(rounds):
        new_points = []
        count = len(result)

        limit = count if closed else count - 1
        for i in range(limit):
            p0 = result[i]
            p1 = result[(i + 1) % count]
            q = 0.75 * p0 + 0.25 * p1
            r = 0.25 * p0 + 0.75 * p1
            new_points.extend([q, r])

        if not closed:
            new_points.insert(0, result[0])
            new_points.append(result[-1])

        result = np.array(new_points)

    return result


def path_length(points: np.ndarray) -> float:
    deltas = np.diff(points, axis=0)
    return float(np.linalg.norm(deltas, axis=1).sum())


def resample_by_index(points: np.ndarray, max_points: int = 900) -> np.ndarray:
    """Keep SVGs lightweight by reducing path point count."""
    if len(points) <= max_points:
        return points
    idx = np.linspace(0, len(points) - 1, max_points).astype(int)
    return points[idx]


def make_orbit_ellipse_points(rx: float, ry: float, angle: float, n: int = 500) -> np.ndarray:
    t = np.linspace(0, 2 * np.pi, n)
    points = np.column_stack([rx * np.cos(t), ry * np.sin(t)])
    return rotate(points, angle)


# -----------------------------
# Drawing
# -----------------------------

def theme_colors(theme: Theme) -> dict[str, str]:
    if theme == "dark":
        return {
            "background": "#050608",
            "primary": "#F2F4F8",
            "secondary": "#A9B4C2",
            "muted": "#6D7888",
            "nucleus": "#FFFFFF",
            "body": "#EAF2FF",
        }

    return {
        "background": "#FFFFFF",
        "primary": "#101418",
        "secondary": "#2E3742",
        "muted": "#87909C",
        "nucleus": "#101418",
        "body": "#101418",
    }


def draw_trail(ax, points: np.ndarray, color: str, linewidth: float, alpha: float, zorder: int) -> None:
    ax.plot(
        points[:, 0],
        points[:, 1],
        color=color,
        linewidth=linewidth,
        alpha=alpha,
        solid_capstyle="round",
        solid_joinstyle="round",
        zorder=zorder,
    )


def draw_atom_overlays(ax, colors: dict[str, str], variant: Variant) -> None:
    """Draw faint atom-like ellipses to keep the icon readable as an atom."""
    if variant == "minimal_atom":
        alpha = 0.35
        lw = 1.5
    else:
        alpha = 0.22
        lw = 1.2

    for angle in (0, 60, -60):
        ellipse = Ellipse(
            xy=(0, 0),
            width=5.2,
            height=1.75,
            angle=angle,
            fill=False,
            linewidth=lw,
            edgecolor=colors["muted"],
            alpha=alpha,
            zorder=1,
        )
        ax.add_patch(ellipse)


def draw_nucleus(ax, colors: dict[str, str]) -> None:
    """Layered nucleus: solid center + thin ring."""
    ax.add_patch(
        Circle(
            (0, 0),
            0.165,
            facecolor=colors["nucleus"],
            edgecolor="none",
            zorder=10,
        )
    )
    ax.add_patch(
        Circle(
            (0, 0),
            0.28,
            facecolor="none",
            edgecolor=colors["nucleus"],
            linewidth=1.2,
            alpha=0.38,
            zorder=9,
        )
    )


def draw_body_markers(ax, paths: list[np.ndarray], colors: dict[str, str]) -> None:
    """Three small bodies/electrons at different points on the paths."""
    fractions = [0.19, 0.52, 0.83]
    sizes = [0.095, 0.075, 0.085]

    for path, fraction, size in zip(paths, fractions, sizes):
        idx = int(len(path) * fraction) % len(path)
        point = path[idx]
        ax.add_patch(
            Circle(
                (float(point[0]), float(point[1])),
                size,
                facecolor=colors["body"],
                edgecolor="none",
                alpha=0.95,
                zorder=12,
            )
        )


def draw_wordmark(ax, config: LogoConfig, colors: dict[str, str]) -> None:
    if not config.show_wordmark:
        return

    ax.text(
        0,
        -3.2,
        config.brand_name,
        ha="center",
        va="center",
        fontsize=24,
        fontweight="bold",
        family="DejaVu Sans",
        color=colors["primary"],
        zorder=20,
    )

    if config.show_tagline:
        ax.text(
            0,
            -3.55,
            config.tagline,
            ha="center",
            va="center",
            fontsize=8.5,
            family="DejaVu Sans",
            color=colors["secondary"],
            alpha=0.82,
            zorder=20,
        )


def generate_logo_paths(config: LogoConfig) -> list[np.ndarray]:
    bodies = initial_conditions(config.variant)
    history = simulate_three_body(
        bodies=bodies,
        steps=config.steps,
        dt=config.dt,
        g=config.grav_const,
        softening=config.softening,
    )

    raw_paths = [history[:: config.trail_stride, body_index, :] for body_index in range(3)]
    paths = normalize_paths(raw_paths, target_radius=2.15)

    # Logo composition rotation: makes the mark feel less like a graph and more like an emblem.
    paths = [rotate(p, -18) for p in paths]

    # Smooth + reduce points for cleaner SVG.
    clean_paths = []
    for p in paths:
        p = chaikin_smooth(p, rounds=config.smooth_rounds, closed=False)
        p = resample_by_index(p, max_points=900)
        clean_paths.append(p)

    return clean_paths


def draw_logo(config: LogoConfig):
    colors = theme_colors(config.theme)
    paths = generate_logo_paths(config)

    fig, ax = plt.subplots(figsize=(config.canvas_size, config.canvas_size))
    fig.patch.set_facecolor(colors["background"])
    ax.set_facecolor(colors["background"])

    # Atom readability layer.
    draw_atom_overlays(ax, colors, config.variant)

    # Mathematical simulation trails.
    trail_widths = [1.7, 1.35, 1.5]
    trail_alphas = [0.98, 0.72, 0.86]

    for path, width, alpha in zip(paths, trail_widths, trail_alphas):
        draw_trail(ax, path, colors["primary"], width, alpha, zorder=5)

    # Fine ghost trails for more depth.
    if config.variant != "minimal_atom":
        for angle, alpha in [(60, 0.11), (-60, 0.09)]:
            ghost_paths = [rotate(p * 0.96, angle) for p in paths]
            for gp in ghost_paths:
                draw_trail(ax, gp, colors["muted"], 0.75, alpha, zorder=2)

    draw_nucleus(ax, colors)
    draw_body_markers(ax, paths, colors)
    draw_wordmark(ax, config, colors)

    limit = 3.85 if config.show_wordmark else 2.95
    ax.set_xlim(-3.6, 3.6)
    ax.set_ylim(-limit, 3.2)
    ax.set_aspect("equal")
    ax.axis("off")

    return fig, ax


def export_logo(config: LogoConfig, output_dir: Path, basename: str) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    fig, _ = draw_logo(config)

    svg_path = output_dir / f"{basename}.svg"
    png_path = output_dir / f"{basename}.png"

    fig.savefig(svg_path, format="svg", bbox_inches="tight", pad_inches=0.15)
    fig.savefig(png_path, format="png", dpi=config.export_dpi, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)

    print(f"Saved: {svg_path}")
    print(f"Saved: {png_path}")


def main() -> None:
    output_dir = Path("outputs")

    base = LogoConfig(
        brand_name="ORIGENLAB",
        tagline="three-body atomic mark",
        variant="figure8_atom",
        theme="light",
        steps=8500,
        dt=0.0035,
        softening=0.015,
        trail_stride=5,
        smooth_rounds=2,
        show_wordmark=True,
        show_tagline=False,
    )

    export_logo(base, output_dir, "three_body_atom_logo")

    dark = LogoConfig(**{**base.__dict__, "theme": "dark"})
    export_logo(dark, output_dir, "three_body_atom_logo_dark")

    chaos = LogoConfig(**{**base.__dict__, "variant": "chaotic_atom", "theme": "light"})
    export_logo(chaos, output_dir, "three_body_atom_logo_chaotic")

    minimal = LogoConfig(**{**base.__dict__, "variant": "minimal_atom", "theme": "light", "smooth_rounds": 3})
    export_logo(minimal, output_dir, "three_body_atom_logo_minimal")


if __name__ == "__main__":
    main()
