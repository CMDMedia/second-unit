"""Prepare a modest 2D following-camera pose guide without changing pose timing."""
import json
import math
import cv2
import numpy as np
import torch


class SecondUnitPoseFollowGuide:
    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {
            "images": ("IMAGE",), "pose_kps": ("POSE_KEYPOINT",),
            "smoothing_window": ("INT", {"default": 9, "min": 1, "max": 51, "step": 2}),
            "target_x": ("FLOAT", {"default": .49, "min": .1, "max": .9, "step": .01}),
            "target_feet_y": ("FLOAT", {"default": .92, "min": .3, "max": .99, "step": .01}),
            "target_body_height": ("FLOAT", {"default": .69, "min": .1, "max": .95, "step": .01}),
            "scale_response": ("FLOAT", {"default": .7, "min": 0, "max": 1, "step": .05}),
            "min_scale": ("FLOAT", {"default": .95, "min": .1, "max": 4, "step": .01}),
            "max_scale": ("FLOAT", {"default": 1.12, "min": .1, "max": 4, "step": .01}),
            "pad_for_h3": ("BOOLEAN", {"default": True}),
        }}

    RETURN_TYPES = ("IMAGE", "INT", "INT", "STRING")
    RETURN_NAMES = ("pose_guide", "source_frame_count", "padded_frame_count", "receipt")
    FUNCTION = "prepare"
    CATEGORY = "Second Unit/Pose"
    DESCRIPTION = "Recenter and scale a single actor's 2D skeleton smoothly. Preserves frame timing; does not reconstruct a 3D camera or unseen angles."

    def prepare(self, images, pose_kps, smoothing_window=9, target_x=.49,
                target_feet_y=.92, target_body_height=.69, scale_response=.7,
                min_scale=.95, max_scale=1.12, pad_for_h3=True):
        n, height, width, channels = images.shape
        if channels != 3 or n < 1:
            raise ValueError("Pose guide needs a nonempty RGB image batch.")
        if len(pose_kps) != n:
            raise ValueError("Pose count must match the source image frame count.")
        if smoothing_window % 2 != 1 or min_scale > max_scale:
            raise ValueError("Use an odd smoothing window and min_scale <= max_scale.")
        track = []
        for index, frame in enumerate(pose_kps):
            people = frame.get("people", [])
            if len(people) != 1:
                raise ValueError(f"Frame {index}: expected one actor; found {len(people)}. Review the pose source.")
            k = np.asarray(people[0]["pose_keypoints_2d"], dtype=np.float64).reshape(-1, 3)
            if k.shape[0] < 14 or not (k[[1, 8, 11, 9, 12, 10, 13], 2] > 0).all():
                raise ValueError(f"Frame {index}: missing torso or leg joints. Review detection before generating.")
            k[:, 0] *= width / frame["canvas_width"]
            k[:, 1] *= height / frame["canvas_height"]
            valid = k[:, 2] > 0
            body_height = float(np.ptp(k[valid, 1]))
            if body_height <= 0:
                raise ValueError(f"Frame {index}: invalid actor height.")
            track.append([k[[8, 11], 0].mean(), max(k[10, 1], k[13, 1]), body_height])
        track = np.asarray(track)
        half = smoothing_window // 2
        smooth = np.stack([np.convolve(np.pad(track[:, i], (half, half), mode="edge"),
                           np.ones(smoothing_window) / smoothing_window, mode="valid") for i in range(3)], axis=1)
        native_count = max(5, math.ceil(max(0, n - 5) / 17) * 17 + 5) if pad_for_h3 else n
        pixels = images.detach().cpu().numpy()
        result = np.empty((native_count, height, width, 3), dtype=np.float32)
        scales = []
        for index in range(n):
            scale = float(np.clip((target_body_height * height / smooth[index, 2]) ** scale_response, min_scale, max_scale))
            tx = target_x * width - scale * smooth[index, 0]
            ty = target_feet_y * height - scale * smooth[index, 1]
            matrix = np.asarray([[scale, 0, tx], [0, scale, ty]], dtype=np.float32)
            result[index] = cv2.warpAffine(pixels[index], matrix, (width, height), flags=cv2.INTER_LINEAR, borderValue=0)
            scales.append(scale)
        result[n:] = result[n - 1]
        receipt = json.dumps({"source_frames": n, "guide_frames": native_count, "tail_padding": native_count-n,
                              "width": width, "height": height, "scale_range": [min(scales), max(scales)],
                              "method": "2D uniform frame transform; no retiming or 3D camera reconstruction"})
        return torch.from_numpy(result), n, native_count, receipt


NODE_CLASS_MAPPINGS = {"SecondUnitPoseFollowGuide": SecondUnitPoseFollowGuide}
NODE_DISPLAY_NAME_MAPPINGS = {"SecondUnitPoseFollowGuide": "Second Unit — Prepare Following Pose"}
