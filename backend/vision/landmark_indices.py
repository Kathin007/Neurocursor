"""MediaPipe Face Landmarker (478-point mesh incl. iris) indices used by the vision pipeline.

"Right"/"left" are the subject's eyes: the subject's right eye appears on the image's left.
"""
from __future__ import annotations

N_LANDMARKS = 478

R_OUTER, R_INNER, R_UPPER, R_LOWER, R_IRIS = 33, 133, 159, 145, 468
L_OUTER, L_INNER, L_UPPER, L_LOWER, L_IRIS = 263, 362, 386, 374, 473

# Six-point eye-aspect-ratio sets: corner, upper, upper, corner, lower, lower.
R_EAR = (33, 160, 158, 133, 153, 144)
L_EAR = (362, 385, 387, 263, 373, 380)

R_IRIS_RING = (469, 470, 471, 472)
L_IRIS_RING = (474, 475, 476, 477)

# Head-pose points: nose tip, chin, eye outer corners (image-left, image-right), mouth corners (image-left, image-right).
POSE_IDX = (1, 152, 33, 263, 61, 291)
