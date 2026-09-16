# Environment workflows

| Workflow | Result | Controls |
| --- | --- | --- |
| Juggernaut XL v9 Environment Still | One 1216 × 832 environment PNG | Environment description and seed |
| LTX 2.5 Environment Animate — Prompt Camera | A short environment video from a reference still | Describe the environment and camera motion in SHOT |

Each installed workflow has a ComfyUI canvas (UI) version and an API version for Second Unit. Both environment pairs are included in this package.

## Requirements

Use a running ComfyUI server with the workflow's checkpoint, text encoder, VAE and required nodes installed. LTX also needs an environment reference image. Model weights are not included.

## Use

For a still, choose **Juggernaut XL v9 → Environment still → Best quality**. Second Unit saves the PNG in a new Environments folder and imports it into the **Second Unit Environments** bin.

For the video workflow, choose **LTX 2.5 → Animate a still → Fast**, select **Environment Animate — Prompt Camera**, and supply the environment image. In SHOT, describe the scene and camera motion, for example: “The camera pans slowly left through the empty cave” or “The camera pushes slowly forward toward the opening.” The workflow passes that request to LTX directly, with no fixed-direction camera adapter. Camera motion follows the prompt, but precise paths and unseen geometry are not guaranteed. Keep requests short and test the result.

**LOAD WORKFLOW** accepts compatible API JSON. The **custom** label identifies a user import; it does not certify visual quality.

## Export size

LTX exports default to **1080p (1920 × 1080)**. In the panel's **EXPORT** selector, choose **720p**, **1080p** or **4K (3840 × 2160)**. The ComfyUI canvas exposes the same delivery width and height in its **EXPORT SIZE** node.

Export resizing keeps the 1216 × 832 generation canvas unchanged and center-crops the result to 16:9. Higher export sizes do not add an AI detail pass or make generation native 4K. Audio stays attached; the panel delivers ProRes HQ. Your export choice is saved for the next session.

## Optional photographic detail

The LTX 2.5 detail stage uses the 2.5 pixel-spatial x2 adapter, source guidance 1, CFG 1 and an eight-step distilled schedule. It refines existing photographic materials while asking the model to retain identity, pose, motion, framing and lighting. It is generative and may change faces or fine details. The same optional stage serves supported video workflows; it does not run automatically or process still-image outputs.

The finish preserves source frame count and audio and retains your selected 720p, 1080p or 4K delivery size. Native x2 refinement and final export resizing are separate. The candidate remains unavailable for normal generation until its visual validation is complete.

## Reference camera information

Before prompt expansion or generation, Second Unit captures available camera metadata for the selected source. It uses exact media paths and explicit source receipts for exported clips. Missing or conflicting metadata is reported as unknown; lens values are never guessed.

Recorded focal length can guide the environment prompt. Your lens override and requested camera position, framing, movement and cuts take priority. Recorded clip metadata does not establish camera height, scene scale, sensor crop or frame-specific zoom. Identity reference crops are kept separate from the source geometry record.


## H3 Pose Follow preview

Choose MiniMax H3 ? Environment Swap ? Fast and **PREVIEW - H3 Pose Follow**. Supply a source video, environment still, and front, three-quarter, profile and body reference cards. One Generate action stages the selected source moment at24fps/1536?864, extracts DWPose, makes a smoothed2D follow guide, applies native H3 ControlNet and saves the trimmed native1536?864 result. No LTX or RTX upscale runs. Source staging center-crops to16:9.

The ComfyUI UI/API pair performs the same pose-to-video graph. For direct ComfyUI use, supply a24fps1536?864 source. Copy `custom_nodes/SecondUnit-PoseFollow` into ComfyUI's custom_nodes directory and restart ComfyUI when idle. DWPose (`comfyui_controlnet_aux`), native MiniMax H3 nodes, VideoHelperSuite and the models named in the graph are required.

This preview is selectable at the user's request; it is not one of the two render-proven environment presets. Full render and visual validation remain pending. The follow guide is an approximate2D framing transform, not3D camera reconstruction.

## Installed preset catalog

Every preset is an API graph verified against the local ComfyUI lane; the panel shows **proven** for presets with a seen panel-path render and **unproven** for presets that passed schema and model checks only. Fast presets target the Distilled lane, Quality presets the Best quality lane.

| Family | Mode | Fast | Best quality |
| --- | --- | --- | --- |
| MiniMax H3 | World Generation (environment replacement, depth locked) | SECONDUNIT - H3 - Environment Replacement Depth Locked Fast | SECONDUNIT - H3 - Environment Replacement Depth Locked Quality; ... Master |
| MiniMax H3 | World Generation (free camera) | SECONDUNIT - H3 - Environment Replacement Free Camera Fast; ... Draft | - |
| MiniMax H3 | Replace the performer | SECONDUNIT - H3 - Character Replacement Depth Locked Fast; ... Draft | SECONDUNIT - H3 - Character Replacement Depth Locked Quality; ... Quality |
| MiniMax H3 | Restyle footage | SECONDUNIT - H3 - Restyle Footage With Sound Fast; ... Draft | SECONDUNIT - H3 - Restyle Footage With Sound Quality |
| MiniMax H3 | Second angle | SECONDUNIT - H3 - Second Angle Fast | SECONDUNIT - H3 - Second Angle Quality |
| MiniMax H3 | Animate a still | SECONDUNIT - H3 - Animate Still With Sound Fast | SECONDUNIT - H3 - Animate Still With Sound Quality |
| MiniMax H3 | First and last frame | SECONDUNIT - H3 - First Last Frame Fast | SECONDUNIT - H3 - First Last Frame Quality |
| MiniMax H3 | Text to video | SECONDUNIT - H3 - Text To Video With Sound Fast | - |
| LTX 2.5 | Animate a still | SECONDUNIT - LTX 2.5 - Animate Still With Audio Fast; ... Camera Arc Shot Fast; Environment Animate - Prompt Camera | - |
| LTX 2.5 | Text to video | SECONDUNIT - LTX 2.5 - Text To Video With Audio | - |
| LTX 2.5 | Replace the performer | SECONDUNIT - LTX 2.5 - Character Replacement | - |
| LTX 2.5 | Restyle footage | SECONDUNIT - LTX 2.5 - Restyle Footage | - |
| SAM 3.1 | Cut a matte | SECONDUNIT - SAM 3.1 - Segment Roto Matte | - |
| WAN 2.2 | Animate a still | - | SECONDUNIT - WAN 2.2 - Animate Still 5B Quality |
| Juggernaut XL v9 | Environment still | - | SecondUnit-Juggernaut-Environment-Stills-API |

Custom imports made with LOAD WORKFLOW live in `workflows/loaded/` and stay labeled **custom**.

Seed box: leave blank or `-1` to keep the preset's seed, type a whole number to pin one, or type `random` for a fresh seed. A negative number other than -1 is treated as `random`.
