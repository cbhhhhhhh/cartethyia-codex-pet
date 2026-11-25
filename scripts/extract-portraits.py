"""Build the ten local portraits from the user's existing cyan-backed Cartethyia pose sheets."""
from pathlib import Path
import subprocess
import sys

source, dest = map(Path, sys.argv[1:3])
dest.mkdir(parents=True, exist_ok=True)
pairs = {
    "happy": [("jumping", 5, 2), ("waving", 4, 2)],
    "curious": [("waiting", 6, 2), ("waiting", 6, 0)],
    "sad": [("failed", 8, 4), ("failed", 8, 2)],
    "focused": [("review", 6, 1), ("review", 6, 0)],
    "calm": [("idle", 6, 0), ("idle", 6, 2)],
}
for mood, pair in pairs.items():
    for v, (pose, count, col) in enumerate(pair):
        path = source/(pose+".png")
        dims = subprocess.check_output(["ffprobe","-v","error","-show_entries","stream=width,height","-of","csv=p=0:s=x",str(path)],text=True)
        w,h = map(int,dims.strip().split("x"))
        step = w//count
        filters = f"format=rgba,crop={step}:{h}:{col*step}:0,colorkey=0x01fbfc:0.24:0.14"
        data = subprocess.check_output(["ffmpeg","-v","error","-i",str(path),"-vf",filters,"-pix_fmt","rgba","-f","rawvideo","pipe:1"])
        mask = data[3::4]
        xs,ys = [],[]
        for y in range(h):
            indices = [x for x,a in enumerate(mask[y*step:(y+1)*step]) if a>180]
            if indices:
                xs.extend((indices[0],indices[-1])); ys.append(y)
        top, bottom = min(ys), max(ys)
        head_h = round((bottom-top)*0.65)
        midpoint = (min(xs)+max(xs))//2
        width = min(step-2, max(max(xs)-min(xs)+3, round(head_h*.92)))
        left = max(0,min(step-width,midpoint-width//2))
        crop = f"crop={width}:{head_h}:{left}:{max(0,top-5)},scale=-1:336:flags=lanczos"
        subprocess.run(["ffmpeg","-v","error","-y","-f","rawvideo","-pixel_format","rgba","-video_size",f"{step}x{h}","-i","pipe:0","-vf",crop,"-frames:v","1",str(dest/f"{mood}-{v}.png")],input=data,check=True)
