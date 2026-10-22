# Changelog

## 1.0.0 — MK Edition

- Added Retrolens — Mikael Kalesaran Edition identity, logo assets, copyright notices, and attribution documentation.
- Added double-click launchers for macOS and Windows with automatic Python environment and dependency setup.
- Pinned a compatible MediaPipe/OpenCV/NumPy dependency set for the original MediaPipe Solutions API.
- Fixed held-pinch and held-fist gestures repeatedly switching filters or modes; gestures now trigger once per press/hold.
- Cached reusable rainbow-filter coordinate axes to reduce per-frame allocations.
- Kept hand landmarks visible above the portal effect and added a compact branded HUD.
- Improved camera/error cleanup and saved screenshots to the local `Captures` folder with readable timestamps.
