"""
OrigenLab — three-body motion mark (true simulation, path-first).

Run:
    python origenlab_three_body_animation.py

Outputs:
    outputs/origenlab_three_body.mp4
    outputs/origenlab_three_body.webm

Dependencies:
    pip install numpy matplotlib imageio imageio-ffmpeg
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import imageio
import matplotlib

matplotlib.use("Agg")
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.patches import Circle, Ellipse

# =========================================================
# ORIGENLAB PALETTE
# =========================================================
PALETTE = {
    "brand_50": "#f0fdfa",
    "brand_100": "#ccfbf1",
    "brand_200": "#99f6e4",
    "brand_300": "#5eead4",
    "brand_400": "#2dd4bf",
    "brand_500": "#14b8a6",
    "brand_600": "#0d9488",
    "brand_700": "#0f766e",
    "brand_800": "#115e59",
    "brand_900": "#134e4a",
    "brand_950": "#042f2e",
}

BODY_COLORS = [
    PALETTE["brand_200"],
    PALETTE["brand_300"],
    PALETTE["brand_400"],
]

@dataclass
class Config:
    # Physics (figure-eight choreography — unchanged)
    steps: int = 12000
    dt: float = 0.0035
    grav_const: float = 1.0
    softening: float = 0.02

    # Timing: premium hero loop
    fps: int = 30
    loop_seconds: float = 14.0

    # Trails — simulated path is the hero
    tail_length: int = 170
    tail_gap_pattern: int = 5
    tail_segment_keep: int = 2
    trail_linewidth: float = 2.15
    glow_linewidth: float = 5.0
    glow_alpha_scale: float = 0.18

    # Atom rings (subtle background)
    ring_alpha: float = 0.10
    ring_color: str = PALETTE["brand_700"]

    # Bodies & nucleus
    body_radius: float = 0.085
    body_glow_scale: float = 2.4
    body_glow_alpha: float = 0.18
    nucleus_radius: float = 0.18
    nucleus_pulse_amount: float = 0.04

    # Layout
    figsize: tuple[float, float] = (8, 8)
    xlim: tuple[float, float] = (-2.85, 2.85)
    ylim: tuple[float, float] = (-2.85, 2.85)
    export_dpi: int = 160

    # Export
    output_dir: str = "outputs"
    mp4_name: str = "origenlab_three_body.mp4"
    webm_name: str = "origenlab_three_body.webm"


# =========================================================
# PHYSICS
# =========================================================
def acceleration(positions: np.ndarray, masses: np.ndarray, g: float, eps: float) -> np.ndarray:
    n = len(positions)
    acc = np.zeros_like(positions)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            delta = positions[j] - positions[i]
            dist_sq = float(np.dot(delta, delta)) + eps**2
            inv_dist_cube = 1.0 / (dist_sq**1.5)
            acc[i] += g * masses[j] * delta * inv_dist_cube
    return acc


def simulate_three_body(steps: int, dt: float, g: float, eps: float) -> np.ndarray:
    """Velocity-Verlet. Returns history shape (steps, 3, 2)."""
    positions = np.array(
        [
            [0.97000436, -0.24308753],
            [-0.97000436, 0.24308753],
            [0.0, 0.0],
        ],
        dtype=float,
    )
    velocities = np.array(
        [
            [0.4662036850, 0.4323657300],
            [0.4662036850, 0.4323657300],
            [-0.93240737, -0.86473146],
        ],
        dtype=float,
    )
    masses = np.ones(3, dtype=float)

    history = np.zeros((steps, 3, 2), dtype=float)
    acc = acceleration(positions, masses, g, eps)

    for s in range(steps):
        history[s] = positions
        positions = positions + velocities * dt + 0.5 * acc * dt * dt
        new_acc = acceleration(positions, masses, g, eps)
        velocities = velocities + 0.5 * (acc + new_acc) * dt
        acc = new_acc

    return history


def find_loop_end(history: np.ndarray, min_step: int = 400) -> int:
    """First step after min_step where all three bodies match t=0 (seamless loop)."""
    ref = history[0].reshape(-1)
    best_i = min_step
    best_err = float("inf")

    for i in range(min_step, len(history)):
        err = float(np.linalg.norm(history[i].reshape(-1) - ref))
        if err < best_err:
            best_err = err
            best_i = i

    return best_i + 1


def normalize_history(history: np.ndarray, target_radius: float = 2.15) -> np.ndarray:
    pts = history.reshape(-1, 2)
    center = pts.mean(axis=0)
    history = history - center

    radii = np.linalg.norm(history.reshape(-1, 2), axis=1)
    scale = target_radius / float(radii.max())
    history = history * scale

    theta = np.deg2rad(-18)
    rot = np.array(
        [
            [np.cos(theta), -np.sin(theta)],
            [np.sin(theta), np.cos(theta)],
        ]
    )
    return history @ rot.T


def hex_to_rgb(color_hex: str) -> tuple[float, float, float]:
    return (
        int(color_hex[1:3], 16) / 255,
        int(color_hex[3:5], 16) / 255,
        int(color_hex[5:7], 16) / 255,
    )


def make_trail_layers(
    points: np.ndarray,
    color_hex: str,
    *,
    gap_pattern: int,
    keep: int,
    trail_width: float,
    glow_width: float,
    glow_alpha_scale: float,
    broken: bool = True,
) -> tuple[LineCollection | None, LineCollection | None]:
    if len(points) < 2:
        return None, None

    segments = np.stack([points[:-1], points[1:]], axis=1)
    n = len(segments)
    rgb = hex_to_rgb(color_hex)

    trail_rgba: list[tuple[float, float, float, float]] = []
    glow_rgba: list[tuple[float, float, float, float]] = []
    trail_segments: list[np.ndarray] = []
    glow_segments: list[np.ndarray] = []

    for i, seg in enumerate(segments):
        if broken:
            if (i % gap_pattern) >= keep:
                continue

        t = (i + 1) / n
        trail_alpha = 0.12 + 0.82 * t
        glow_alpha = glow_alpha_scale * (0.35 + 0.65 * t)

        trail_segments.append(seg)
        trail_rgba.append((*rgb, trail_alpha))

        glow_segments.append(seg)
        glow_rgba.append((*rgb, glow_alpha))

    if not trail_segments:
        return None, None

    glow_lc = LineCollection(
        glow_segments,
        colors=glow_rgba,
        linewidths=glow_width,
        capstyle="round",
        joinstyle="round",
    )
    trail_lc = LineCollection(
        trail_segments,
        colors=trail_rgba,
        linewidths=trail_width,
        capstyle="round",
        joinstyle="round",
    )
    return glow_lc, trail_lc


def build_frame_schedule(history: np.ndarray, cfg: Config) -> tuple[np.ndarray, int]:
    loop_end = find_loop_end(history)
    n_frames = max(int(round(cfg.loop_seconds * cfg.fps)), 1)
    frame_indices = np.linspace(0, loop_end - 1, n_frames, dtype=int)
    return frame_indices, loop_end


def export_video(frames: list[np.ndarray], path: Path, fps: int, codec: str, extra_args: list[str]) -> None:
    writer = imageio.get_writer(
        path,
        fps=fps,
        codec=codec,
        format="FFMPEG",
        ffmpeg_params=extra_args,
    )
    try:
        for frame in frames:
            writer.append_data(frame)
    finally:
        writer.close()


def capture_frame(fig: plt.Figure) -> np.ndarray:
    fig.canvas.draw()
    rgba = np.asarray(fig.canvas.buffer_rgba())
    return rgba[:, :, :3].copy()


def main() -> None:
    cfg = Config()
    output_dir = Path(cfg.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Simulating three-body system...")
    history = simulate_three_body(cfg.steps, cfg.dt, cfg.grav_const, cfg.softening)
    history = normalize_history(history)

    frame_indices, loop_end = build_frame_schedule(history, cfg)
    n_frames = len(frame_indices)
    duration = n_frames / cfg.fps

    print(f"Loop: {loop_end} sim steps -> {n_frames} frames @ {cfg.fps} fps ({duration:.1f}s)")

    plt.rcParams.update(
        {
            "figure.facecolor": PALETTE["brand_950"],
            "axes.facecolor": PALETTE["brand_950"],
            "savefig.facecolor": PALETTE["brand_950"],
            "font.family": ["DejaVu Sans", "sans-serif"],
        }
    )

    fig, ax = plt.subplots(figsize=cfg.figsize, dpi=cfg.export_dpi)
    ax.set_xlim(*cfg.xlim)
    ax.set_ylim(*cfg.ylim)
    ax.set_aspect("equal")
    ax.axis("off")

    for w, h, ang in ((4.6, 1.55, 0), (4.6, 1.55, 60), (4.6, 1.55, -60)):
        ax.add_patch(
            Ellipse(
                (0, 0),
                width=w,
                height=h,
                angle=ang,
                fill=False,
                linewidth=1.0,
                edgecolor=cfg.ring_color,
                alpha=cfg.ring_alpha,
                zorder=1,
            )
        )

    nucleus_outer = Circle(
        (0, 0),
        cfg.nucleus_radius * 1.8,
        facecolor="none",
        edgecolor=PALETTE["brand_400"],
        linewidth=1.0,
        alpha=0.16,
        zorder=8,
    )
    nucleus = Circle(
        (0, 0),
        cfg.nucleus_radius,
        facecolor=PALETTE["brand_100"],
        edgecolor="none",
        zorder=12,
    )
    ax.add_patch(nucleus_outer)
    ax.add_patch(nucleus)

    body_glows: list[Circle] = []
    body_dots: list[Circle] = []
    for color in BODY_COLORS:
        glow = Circle(
            (0, 0),
            cfg.body_radius * cfg.body_glow_scale,
            facecolor=color,
            edgecolor="none",
            alpha=cfg.body_glow_alpha,
            zorder=18,
        )
        ax.add_patch(glow)
        body_glows.append(glow)

        dot = Circle(
            (0, 0),
            cfg.body_radius,
            facecolor=color,
            edgecolor=PALETTE["brand_50"],
            linewidth=0.6,
            alpha=0.98,
            zorder=20,
        )
        ax.add_patch(dot)
        body_dots.append(dot)

    trail_artists: list[LineCollection | None] = []

    def clear_trails() -> None:
        for artist in trail_artists:
            if artist is not None:
                artist.remove()
        trail_artists.clear()

    def update(frame_number: int) -> None:
        clear_trails()
        idx = int(frame_indices[frame_number])

        mean_r = float(np.mean(np.linalg.norm(history[idx], axis=1)))
        pulse_scale = 1.0 + cfg.nucleus_pulse_amount * (mean_r - 1.5)
        nucleus.radius = cfg.nucleus_radius * pulse_scale
        nucleus_outer.radius = cfg.nucleus_radius * 1.8 * pulse_scale
        nucleus_outer.set_alpha(0.14 + 0.05 * min(max(pulse_scale, 1.0), 1.15))

        for body_idx, color in enumerate(BODY_COLORS):
            path = history[: idx + 1, body_idx, :]
            tail = path[-cfg.tail_length :]

            glow_lc, trail_lc = make_trail_layers(
                tail,
                color,
                gap_pattern=cfg.tail_gap_pattern,
                keep=cfg.tail_segment_keep,
                trail_width=cfg.trail_linewidth,
                glow_width=cfg.glow_linewidth,
                glow_alpha_scale=cfg.glow_alpha_scale,
            )
            if glow_lc is not None:
                glow_lc.set_zorder(6 + body_idx)
                ax.add_collection(glow_lc)
                trail_artists.append(glow_lc)
            if trail_lc is not None:
                trail_lc.set_zorder(10 + body_idx)
                ax.add_collection(trail_lc)
                trail_artists.append(trail_lc)

            x, y = path[-1]
            body_glows[body_idx].center = (x, y)
            body_dots[body_idx].center = (x, y)

    print(f"Rendering {n_frames} frames...")
    frames: list[np.ndarray] = []
    for f in range(n_frames):
        update(f)
        frames.append(capture_frame(fig))
        if (f + 1) % 60 == 0 or f + 1 == n_frames:
            print(f"  {f + 1}/{n_frames}")

    plt.close(fig)

    mp4_path = output_dir / cfg.mp4_name
    webm_path = output_dir / cfg.webm_name

    print(f"Encoding MP4 -> {mp4_path}")
    export_video(
        frames,
        mp4_path,
        cfg.fps,
        "libx264",
        ["-crf", "20", "-movflags", "+faststart"],
    )

    print(f"Encoding WebM -> {webm_path}")
    export_video(
        frames,
        webm_path,
        cfg.fps,
        "libvpx-vp9",
        ["-crf", "32", "-b:v", "0"],
    )

    mp4_mb = mp4_path.stat().st_size / (1024 * 1024)
    webm_mb = webm_path.stat().st_size / (1024 * 1024)
    print(f"Done. MP4: {mp4_mb:.2f} MB | WebM: {webm_mb:.2f} MB")


if __name__ == "__main__":
    main()
