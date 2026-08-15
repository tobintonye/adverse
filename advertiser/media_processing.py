"""
Media processing: verifies uploaded ad creatives are safe to decode on
billboard hardware, and transcodes them to a known spec when they aren't. 
(this make sure the media player does not choke, crash or hit a security issue when it tries to open(encode) a file)

this module is a safety/compatibility gate for ad media it checks uploads, and if they don't meet spec, it converts them into something the billboard displays can safely play.
"""
import json
import logging
import subprocess
from PIL import Image
from django.conf import settings
logger = logging.getLogger("advertiser.media_processing")

# Safe fallback profile: Forces 1080p H.264 to guarantee smooth playback.
# Prevents cheap player boxes from lagging or crashing on heavy video files.
TARGET_MAX_WIDTH = 1920
TARGET_MAX_HEIGHT= 1080
TARGET_VIDEO_CODEC= "h264"
TARGET_PIXEL_FORMAT= "yuv420p"

MAX_IMAGE_DIMENSION = 3840  # device itself scales down further to its own resolution


FFMPEG_BINARY = getattr(settings, "FFMPEG_BINARY", "ffmpeg")
FFPROBE_BINARY = getattr(settings, "FFPROBE_BINARY", "ffprobe")

FFPROBE_TIMEOUT_SECONDS = 60
FFMPEG_TIMEOUT_SECONDS = 60 # 10 min ceiling for a single transcode

class MediaProcessingError(Exception):
    pass

def download_field_file(field_file, destination_path: str) -> None:
    # download or copy user uploads and save it to a local temp path so FFmpeg can access it.
    field_file.open("rb")
    try:
        with open(destination_path, "wb") as out:
            for chunk in field_file.chunks():
                out.write(chunk)
    finally:
        field_file.close()

def probe_video(local_path:str) -> dict:
    cmd = [FFPROBE_BINARY, "-v", "error", "-print_format", "json", "-show_streams", "-show_format", local_path]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=FFPROBE_TIMEOUT_SECONDS)
    if result.returncode != 0:
        raise MediaProcessingError(f"ffprobe failed: {result.stderr[:500]}")
    return json.loads(result.stdout)

# get the returned data from probe and extract the specific layer that contains the actual video track(codec_type)
def _video_stream(probe_data: dict) -> dict:
    stream = next((s for s in probe_data.get("streams", []) if s.get("codec_type") == "video"), None)
    if not stream:
        raise MediaProcessingError("No video stream found in file")
    return stream

def needs_transcode(probe_data: dict) -> tuple[bool, str]: 
    # Gatekeeper - checks if the video can be sent with out transcode or needs to be transcode
    stream = _video_stream(probe_data)
    codec = stream.get("codec_name") # h.264 or h.265
    width = int(stream.get("width", 0))
    height = int(stream.get("height", 0))
    pix_fmt = stream.get("pix_fmt")

    if codec != TARGET_VIDEO_CODEC: 
        return True, f"codec '{codec}' is not {TARGET_VIDEO_CODEC}"
    if width > TARGET_MAX_WIDTH or height > TARGET_MAX_HEIGHT: 
        return True, f"resolution {width}x{height} exceeds {TARGET_MAX_WIDTH}x{TARGET_MAX_HEIGHT}"
    if pix_fmt != TARGET_PIXEL_FORMAT:
        return True, f"pixel format '{pix_fmt}' is not {TARGET_PIXEL_FORMAT} (common hardware-decoder blocker)"
    return False, ""

def transcode_video(input_path: str, output_path: str) -> None:
    cmd = [
       FFMPEG_BINARY, "-y", "-i", input_path,
        "-vf", (
            f"scale='min({TARGET_MAX_WIDTH},iw)':'min({TARGET_MAX_HEIGHT},ih)':"
            "force_original_aspect_ratio=decrease"
        ),
        "-c:v", "libx264", "-profile:v", "high", "-level", "4.0",
        "-pix_fmt", TARGET_PIXEL_FORMAT,
        "-preset", "medium", "-crf", "23",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",  # metadata at file start — starts playing before full download
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=FFMPEG_TIMEOUT_SECONDS)
    if result.returncode != 0:
        raise MediaProcessingError(f"ffmpeg transcode failed: {result.stderr[-1000:]}")


def process_image(input_path: str, output_path: str) -> tuple[int, int]:
    """Verifies the file actually decodes, downsizes if oversized, and
    normalizes to JPEG. Returns (width, height) of the output."""
    with Image.open(input_path) as img:
        img.load()  # forces full decode now — catches truncated/corrupt files here, not on-device
        if img.mode not in ("RGB",):
            img = img.convert("RGB")
        if img.width > MAX_IMAGE_DIMENSION or img.height > MAX_IMAGE_DIMENSION:
            img.thumbnail((MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION), Image.LANCZOS)
        img.save(output_path, "JPEG", quality=88, optimize=True)
        return img.width, img.height
