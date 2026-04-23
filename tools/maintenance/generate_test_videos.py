import subprocess
from pathlib import Path

def create_test_videos():
    test_dir = Path("test_videos")
    test_dir.mkdir(exist_ok=True)


    print(" Generating video_original.mp4...")
    subprocess.run([
        'ffmpeg', '-y', '-f', 'lavfi', '-i', 'color=c=blue:s=320x240:d=3',
        '-f', 'lavfi', '-i', 'sine=f=440:d=3',
        '-c:v', 'libx264', '-c:a', 'aac', '-shortest', str(test_dir / "video_original.mp4")
    ], capture_output=True)


    print(" Generating video_v1_reencoded.mp4...")
    subprocess.run([
        'ffmpeg', '-y', '-i', str(test_dir / "video_original.mp4"),
        '-vf', 'hue=h=30', '-c:v', 'libx264', '-b:v', '100k', str(test_dir / "video_v1_reencoded.mp4")
    ], capture_output=True)


    print(" Generating video_audio_dupe.mp4...")
    subprocess.run([
        'ffmpeg', '-y', '-f', 'lavfi', '-i', 'color=c=red:s=320x240:d=3',
        '-f', 'lavfi', '-i', 'sine=f=440:d=3',
        '-c:v', 'libx264', '-c:a', 'aac', '-shortest', str(test_dir / "video_audio_dupe.mp4")
    ], capture_output=True)

if __name__ == "__main__":
    create_test_videos()
