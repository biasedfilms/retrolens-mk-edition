"""
Retrolens — Mikael Kalesaran Edition
Real-time hand-gesture portal effects.

Copyright (c) 2026 Mikael Kalesaran (modifications and product edition).
Derived from the original Retrolens project by Sy4hdan; see LICENSE and NOTICE.md.
"""

from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path
import random
import sys
import time
from typing import Dict, List, Tuple, Callable

import cv2
import mediapipe as mp
import numpy as np


APP_VERSION = "1.0.0"


@dataclass
class PipelineConfig:
    cam_index: int = 0
    frame_width: int = 960
    frame_height: int = 540
    pinch_threshold_px: float = 45.0
    filter_cooldown_sec: float = 0.15
    mode_cooldown_sec: float = 1.2
    fist_dist_threshold_px: float = 80.0


class FilterBank:
    @staticmethod
    def dual_tone(roi: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, 110, 255, cv2.THRESH_BINARY)
        out = np.zeros_like(roi)
        out[mask == 255] = (10, 140, 255)
        out[mask == 0] = (180, 30, 220)
        return out

    @staticmethod
    def thermal(roi: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        return cv2.applyColorMap(gray, cv2.COLORMAP_JET)

    @staticmethod
    def sketch(roi: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        inv = 255 - gray
        blur = cv2.GaussianBlur(inv, (21, 21), 0)
        sketch = cv2.divide(gray, 255 - blur, scale=256)
        return cv2.cvtColor(sketch, cv2.COLOR_GRAY2BGR)

    @staticmethod
    def pixelate(roi: np.ndarray, block_size: int = 14) -> np.ndarray:
        h, w = roi.shape[:2]
        if h < 2 or w < 2:
            return roi
        small = cv2.resize(roi, (max(1, w // block_size), max(1, h // block_size)), interpolation=cv2.INTER_LINEAR)
        return cv2.resize(small, (w, h), interpolation=cv2.INTER_NEAREST)

    @staticmethod
    def glitch(roi: np.ndarray) -> np.ndarray:
        h, w = roi.shape[:2]
        if h < 2 or w < 2:
            return roi
        b, g, r = cv2.split(roi)
        shift = random.randint(4, 12)
        r = np.roll(r, shift, axis=1)
        b = np.roll(b, -shift, axis=1)
        out = cv2.merge([b, g, r])
        for _ in range(2):
            y = random.randint(0, h - 1)
            out[y : y + 1, :] = np.random.randint(0, 255, (1, w, 3), dtype=np.uint8)
        return out

    @staticmethod
    def invert(roi: np.ndarray) -> np.ndarray:
        return 255 - roi

    @staticmethod
    def red_channel(roi: np.ndarray) -> np.ndarray:
        b, g, r = cv2.split(roi)
        zeros = np.zeros_like(b)
        return cv2.merge([zeros, zeros, r])

    @staticmethod
    def edge(roi: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 60, 150)
        colored = cv2.applyColorMap(edges, cv2.COLORMAP_SUMMER)
        return cv2.bitwise_and(colored, colored, mask=edges)

    @staticmethod
    def blur(roi: np.ndarray) -> np.ndarray:
        return cv2.GaussianBlur(roi, (25, 25), 0)

    @staticmethod
    def cartoon(roi: np.ndarray) -> np.ndarray:
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        gray_blur = cv2.medianBlur(gray, 5)
        edges = cv2.adaptiveThreshold(gray_blur, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 9, 9)
        color = cv2.bilateralFilter(roi, 9, 250, 250)
        return cv2.bitwise_and(color, cv2.cvtColor(edges, cv2.COLOR_GRAY2BGR))

    @staticmethod
    @lru_cache(maxsize=64)
    def _wave_axis(length: int) -> np.ndarray:
        # Reuse one-dimensional axes instead of allocating two full meshgrids every frame.
        return np.arange(length, dtype=np.float32)

    @staticmethod
    def rainbow_wave(roi: np.ndarray) -> np.ndarray:
        h, w = roi.shape[:2]
        t = time.time() * 5.0
        x = FilterBank._wave_axis(w)[None, :]
        y = FilterBank._wave_axis(h)[:, None]
        pattern = np.sin((x + y) * 0.05 + t) * 127 + 128
        rainbow = cv2.applyColorMap(pattern.astype(np.uint8), cv2.COLORMAP_HSV)
        return cv2.addWeighted(roi, 0.3, rainbow, 0.7, 0)


class GeometryUtils:
    @staticmethod
    def euclidean_dist(p1: Tuple[int, int], p2: Tuple[int, int]) -> float:
        return float(np.hypot(p1[0] - p2[0], p1[1] - p2[1]))

    @staticmethod
    def is_fist_closed(landmarks, w: int, h: int, threshold: float) -> bool:
        wrist = np.array([landmarks[0].x * w, landmarks[0].y * h])
        tips = [8, 12, 16, 20]
        distances = [np.linalg.norm(np.array([landmarks[t].x * w, landmarks[t].y * h]) - wrist) for t in tips]
        return float(np.mean(distances)) < threshold

    @staticmethod
    def is_hand_rotated(thumb: Tuple[int, int], index: Tuple[int, int]) -> bool:
        dx, dy = index[0] - thumb[0], index[1] - thumb[1]
        return (dy > 25) or (abs(dx) > abs(dy) * 1.1)

    @staticmethod
    def sort_quad_clean(pts: List[Tuple[int, int]]) -> np.ndarray:
        arr = np.array(pts, dtype=np.float32)
        x_sorted = arr[np.argsort(arr[:, 0]), :]
        leftmost = x_sorted[:2, :][np.argsort(x_sorted[:2, 1]), :]
        rightmost = x_sorted[2:, :][np.argsort(x_sorted[2:, 1]), :]
        return np.array([leftmost[0], rightmost[0], rightmost[1], leftmost[1]], dtype=np.int32)

    @staticmethod
    def sort_quad_bowtie(pts: List[Tuple[int, int]]) -> np.ndarray:
        arr = np.array(pts, dtype=np.float32)
        x_sorted = arr[np.argsort(arr[:, 0]), :]
        leftmost = x_sorted[:2, :][np.argsort(x_sorted[:2, 1]), :]
        rightmost = x_sorted[2:, :][np.argsort(x_sorted[2:, 1]), :]
        return np.array([leftmost[0], rightmost[1], rightmost[0], leftmost[1]], dtype=np.int32)


class PortalProcessor:
    """Real-time hand tracker and portal renderer."""

    def __init__(self, cfg: PipelineConfig):
        self.cfg = cfg
        self.filters: Dict[str, Callable[[np.ndarray], np.ndarray]] = {
            "dual-tone": FilterBank.dual_tone,
            "thermal": FilterBank.thermal,
            "sketch": FilterBank.sketch,
            "pixelate": FilterBank.pixelate,
            "glitch": FilterBank.glitch,
            "invert": FilterBank.invert,
            "red-channel": FilterBank.red_channel,
            "edge": FilterBank.edge,
            "blur": FilterBank.blur,
            "cartoon": FilterBank.cartoon,
            "rainbow-wave": FilterBank.rainbow_wave,
        }
        self.filter_keys = list(self.filters.keys())
        self.active_filter_idx = 0
        self.is_3d_mode = False
        self.last_switch_time = 0.0
        self.last_mode_toggle = 0.0

        # Gesture transitions are edge-triggered: holding a gesture won't repeatedly fire.
        self._pinch_was_active = False
        self._both_fists_were_closed = False

        self.mp_hands = mp.solutions.hands
        self.mp_draw = mp.solutions.drawing_utils
        self.detector = self.mp_hands.Hands(
            static_image_mode=False,
            max_num_hands=2,
            model_complexity=1,
            min_detection_confidence=0.7,
            min_tracking_confidence=0.65,
        )

    @property
    def current_filter_name(self) -> str:
        return self.filter_keys[self.active_filter_idx]

    @property
    def secondary_filter_name(self) -> str:
        return self.filter_keys[(self.active_filter_idx + 1) % len(self.filter_keys)]

    def cycle_filter(self, step: int = 1) -> None:
        self.active_filter_idx = (self.active_filter_idx + step) % len(self.filter_keys)

    def toggle_mode(self) -> None:
        self.is_3d_mode = not self.is_3d_mode
        self.last_mode_toggle = time.time()

    def close(self) -> None:
        """Release MediaPipe resources when the camera window closes."""
        detector = getattr(self, "detector", None)
        if detector is not None:
            detector.close()

    def render_portal(self, frame: np.ndarray, pts: List[Tuple[int, int]], filter_key: str) -> np.ndarray:
        poly = np.array(pts, dtype=np.int32)
        if len(poly) < 3:
            return frame

        x, y, w, h = cv2.boundingRect(poly)
        frame_h, frame_w = frame.shape[:2]
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(frame_w, x + w), min(frame_h, y + h)
        if x2 - x1 <= 10 or y2 - y1 <= 10:
            return frame

        # Keep polygon coordinates aligned to the clipped frame region.
        roi = frame[y1:y2, x1:x2].copy()
        processed_roi = self.filters[filter_key](roi)
        mask = np.zeros(roi.shape[:2], dtype=np.uint8)
        local_poly = poly - np.array([x1, y1], dtype=np.int32)
        cv2.fillPoly(mask, [local_poly], 255)
        bg = cv2.bitwise_and(roi, roi, mask=cv2.bitwise_not(mask))
        fg = cv2.bitwise_and(processed_roi, processed_roi, mask=mask)
        frame[y1:y2, x1:x2] = cv2.add(bg, fg)
        cv2.polylines(frame, [poly], isClosed=True, color=(229, 205, 255), thickness=2, lineType=cv2.LINE_AA)
        return frame

    def process_frame(self, frame: np.ndarray) -> np.ndarray:
        frame = cv2.flip(frame, 1)
        interpolation = cv2.INTER_AREA if frame.shape[1] > self.cfg.frame_width else cv2.INTER_LINEAR
        frame = cv2.resize(frame, (self.cfg.frame_width, self.cfg.frame_height), interpolation=interpolation)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = self.detector.process(rgb)
        now = time.time()

        detected_hands = results.multi_hand_landmarks or []
        all_hand_tips: List[List[Tuple[int, int]]] = []
        fist_count = 0
        pinch_active = False

        for hand_lm in detected_hands:
            lm = hand_lm.landmark
            tips = [
                (int(lm[i].x * self.cfg.frame_width), int(lm[i].y * self.cfg.frame_height))
                for i in (4, 8, 12, 16, 20)
            ]
            all_hand_tips.append(tips)

            # A thumb-to-pinky pinch advances one filter per gesture, not continuously.
            if GeometryUtils.euclidean_dist(tips[0], tips[4]) < self.cfg.pinch_threshold_px:
                pinch_active = True

            if GeometryUtils.is_fist_closed(
                lm, self.cfg.frame_width, self.cfg.frame_height, self.cfg.fist_dist_threshold_px
            ):
                fist_count += 1

        if pinch_active and not self._pinch_was_active and now - self.last_switch_time > self.cfg.filter_cooldown_sec:
            self.cycle_filter(1)
            self.last_switch_time = now
        self._pinch_was_active = pinch_active

        both_fists_closed = len(detected_hands) == 2 and fist_count == 2
        if both_fists_closed and not self._both_fists_were_closed and now - self.last_mode_toggle > self.cfg.mode_cooldown_sec:
            self.is_3d_mode = not self.is_3d_mode
            self.last_mode_toggle = now
        self._both_fists_were_closed = both_fists_closed

        if self.is_3d_mode:
            if len(all_hand_tips) == 2:
                t1, t2 = all_hand_tips[0], all_hand_tips[1]
                frame = self.render_portal(
                    frame,
                    [t1[0], t1[1], t1[2], t2[2], t2[1], t2[0]],
                    self.current_filter_name,
                )
                frame = self.render_portal(
                    frame,
                    [t1[2], t1[3], t1[4], t2[4], t2[3], t2[2]],
                    self.secondary_filter_name,
                )
            elif len(all_hand_tips) == 1:
                frame = self.render_portal(frame, all_hand_tips[0], self.current_filter_name)
        else:
            if len(all_hand_tips) == 2:
                corners = [all_hand_tips[0][0], all_hand_tips[0][1], all_hand_tips[1][0], all_hand_tips[1][1]]
                if GeometryUtils.is_hand_rotated(corners[0], corners[1]) or GeometryUtils.is_hand_rotated(corners[2], corners[3]):
                    quad = GeometryUtils.sort_quad_bowtie(corners)
                    is_bowtie = True
                else:
                    quad = GeometryUtils.sort_quad_clean(corners)
                    is_bowtie = False
                frame = self.render_portal(frame, quad.tolist(), self.current_filter_name)
            elif len(all_hand_tips) == 1:
                tips = all_hand_tips[0]
                frame = self.render_portal(frame, [tips[0], tips[1], tips[2], tips[4]], self.current_filter_name)
                is_bowtie = False
            else:
                is_bowtie = False

        # Draw landmarks after the effect so hands remain visible over the portal.
        for hand_lm in detected_hands:
            self.mp_draw.draw_landmarks(frame, hand_lm, self.mp_hands.HAND_CONNECTIONS)

        frame = self._draw_hud(frame, is_bowtie if not self.is_3d_mode else False)
        return frame

    def _draw_hud(self, frame: np.ndarray, is_bowtie: bool) -> np.ndarray:
        """Draw a compact, branded overlay without obscuring the center of the camera."""
        height, width = frame.shape[:2]
        overlay = frame.copy()
        cv2.rectangle(overlay, (14, 12), (330, 78), (17, 16, 24), -1)
        panel_x = max(344, width - 276)
        cv2.rectangle(overlay, (panel_x, 12), (width - 14, 78), (17, 16, 24), -1)
        cv2.rectangle(overlay, (14, height - 46), (width - 14, height - 12), (17, 16, 24), -1)
        frame = cv2.addWeighted(overlay, 0.78, frame, 0.22, 0)

        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(frame, "RETROLENS", (27, 41), font, 0.72, (246, 243, 251), 2, cv2.LINE_AA)
        cv2.putText(frame, "MIKAEL KALESARAN EDITION", (28, 62), font, 0.37, (208, 163, 255), 1, cv2.LINE_AA)

        mode_str = "3D PORTAL" if self.is_3d_mode else ("2D BOWTIE" if is_bowtie else "2D PORTAL")
        cv2.putText(frame, mode_str, (panel_x + 12, 38), font, 0.47, (231, 224, 245), 1, cv2.LINE_AA)
        cv2.putText(frame, self.current_filter_name.upper(), (panel_x + 12, 60), font, 0.42, (208, 163, 255), 1, cv2.LINE_AA)

        controls = "PINCH: FILTER   N/P: NEXT/PREV   C: MODE   S: SAVE   Q/ESC: QUIT"
        cv2.putText(frame, controls, (27, height - 25), font, 0.36, (229, 225, 236), 1, cv2.LINE_AA)
        return frame


def _open_camera(index: int) -> cv2.VideoCapture:
    """Open the default camera with the platform's preferred backend."""
    if sys.platform == "darwin":
        capture = cv2.VideoCapture(index, cv2.CAP_AVFOUNDATION)
    else:
        capture = cv2.VideoCapture(index)
    if capture.isOpened():
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    return capture


def main() -> int:
    cfg = PipelineConfig()
    processor = None
    capture = None
    window_title = f"Retrolens MK Edition v{APP_VERSION} — Mikael Kalesaran"

    try:
        processor = PortalProcessor(cfg)
        capture = _open_camera(cfg.cam_index)
        if not capture.isOpened():
            raise RuntimeError(
                "Kamera tidak dapat dibuka. Izinkan akses kamera untuk aplikasi ini di pengaturan privasi, "
                "lalu tutup aplikasi lain yang sedang memakai kamera."
            )

        cv2.namedWindow(window_title, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(window_title, cfg.frame_width, cfg.frame_height)
        print(f"Retrolens MK Edition v{APP_VERSION} is running. Press Q or Esc to quit.")

        while True:
            ok, frame = capture.read()
            if not ok or frame is None:
                raise RuntimeError("Frame kamera gagal dibaca. Coba sambungkan kembali kamera lalu jalankan ulang.")

            output = processor.process_frame(frame)
            cv2.imshow(window_title, output)
            key = cv2.waitKey(1) & 0xFF

            if key in (ord("q"), 27):
                break
            if key == ord("c"):
                processor.toggle_mode()
            elif key == ord("n"):
                processor.cycle_filter(1)
            elif key == ord("p"):
                processor.cycle_filter(-1)
            elif key == ord("s"):
                captures_dir = Path(__file__).resolve().parent / "Captures"
                captures_dir.mkdir(parents=True, exist_ok=True)
                stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                screenshot_path = captures_dir / f"retrolens_{stamp}.png"
                if cv2.imwrite(str(screenshot_path), output):
                    print(f"Screenshot saved: {screenshot_path}")
                else:
                    print("Screenshot could not be saved. Check folder permissions.")

        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        print(f"\n[Retrolens] {exc}", file=sys.stderr)
        print("If this keeps happening, check README.md for setup and camera permissions.", file=sys.stderr)
        return 1
    finally:
        if capture is not None:
            capture.release()
        if processor is not None:
            processor.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    raise SystemExit(main())
