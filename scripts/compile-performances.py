"""Pack original 4x4 RGBA key-pose sheets for the Mac animation player.

Authoring tool only: python3 with Pillow, numpy and opencv-python-headless.
Run from the checkout: python scripts/compile-performances.py SOURCE_FOLDER
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "art/repertoire.json").read_text())
FEATURED = [11, 19, 37, 72]
ORDER = FEATURED + [i for i in range(len(CATALOG)) if i not in FEATURED]
WIDTH, HEIGHT = 192, 208
TIMING = [0, .06, .17, .33, .55, .78, 1, 1, 1.12, 1.34, 1.65, 1.9,
          2, 2, 2, 2.08, 2.25, 2.51, 2.75, 2.91, 3, 3, 3, 3]
cv2.setNumThreads(1)


def clear_exterior(sheet):
    border = np.concatenate([sheet[0], sheet[-1], sheet[:,0], sheet[:,-1]])
    if np.median(border[:,3]) < 32 or np.min(np.median(border[:,:3],axis=0)) < 242:
        return sheet
    # One original page has a nearly-white translucent paper matte. Flood only
    # the contiguous exterior, preserving pale hair, paper and enclosed highlights.
    light = ((sheet[:,:,:3].min(2) >= 237) & (sheet[:,:,3] < 247)).astype(np.uint8)
    _, labels = cv2.connectedComponents(light)
    edges = set(np.concatenate([labels[0],labels[-1],labels[:,0],labels[:,-1]]))
    edges.discard(0)
    outside = np.isin(labels,list(edges))
    sheet = sheet.copy()
    sheet[outside] = 0
    return sheet


def dividers(alpha, axis):
    length = alpha.shape[axis]
    density = (alpha > 70).sum(axis=1-axis)
    edges = [0]
    for index in range(1, 4):
        point = index * length // 4
        radius = int(length * .043)
        lo, hi = point-radius, point+radius
        costs = density[lo:hi] + np.abs(np.arange(lo, hi)-point) * .08
        edges.append(lo + int(np.argmin(costs)))
    return edges + [length]


def extract(tile):
    tile = tile.copy()
    alpha = tile[:, :, 3]
    # Transparent matting sometimes contains almost-invisible pixels across the grid.
    mask = (alpha > 24).astype(np.uint8)
    n, labels, stats, centroids = cv2.connectedComponentsWithStats(mask)
    keep = np.zeros(n, dtype=np.uint8)
    for idx in range(1, n):
        x,y,w,h,area = stats[idx]
        cx,cy = centroids[idx]
        border = x == 0 or y == 0 or x+w == tile.shape[1] or y+h == tile.shape[0]
        if area >= 14 and not (border and area < 330 and min(w,h) < 12):
            keep[idx] = 1
    support = cv2.dilate(keep[labels], np.ones((3,3), np.uint8))
    alpha[:] = np.where(support, np.maximum(alpha.astype(float)-5,0)*255/248, 0).clip(0,255).astype(np.uint8)
    box = Image.fromarray(alpha).getbbox()
    if not box:
        raise ValueError("Empty key pose")
    return Image.fromarray(tile).crop(box)


def align(poses):
    scale = min((WIDTH-12)/max(im.width for im in poses), (HEIGHT-10)/max(im.height for im in poses))
    aligned = []
    for pose in poses:
        pose = pose.resize((round(pose.width*scale),round(pose.height*scale)), Image.Resampling.LANCZOS)
        frame = Image.new("RGBA", (WIDTH,HEIGHT))
        frame.paste(pose, ((WIDTH-pose.width)//2,HEIGHT-5-pose.height))
        aligned.append(np.asarray(frame).copy())
    return aligned


def transition(first, second):
    # Interpolate premultiplied artwork so transparent contours do not acquire dark halos.
    a, b = (im.astype(np.float32)/255 for im in (first, second))
    for im in (a, b):
        im[:, :, :3] *= im[:, :, 3:4]
    def guide(pixel):
        return cv2.cvtColor(((pixel[:, :, :3]+.72*(1-pixel[:, :, 3:4]))*255).clip(0,255).astype(np.uint8), cv2.COLOR_RGB2GRAY)
    left,right = guide(a), guide(b)
    flow = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    forward = flow.calc(left,right,None)
    backward = flow.calc(right,left,None)
    yy,xx = np.mgrid[:HEIGHT,:WIDTH].astype(np.float32)
    def blend(t):
        x = cv2.remap(a,xx-t*forward[:,:,0],yy-t*forward[:,:,1],cv2.INTER_LINEAR)
        y = cv2.remap(b,xx-(1-t)*backward[:,:,0],yy-(1-t)*backward[:,:,1],cv2.INTER_LINEAR)
        mixed = (1-t)*x + t*y
        mixed[:, :, :3] /= np.maximum(mixed[:, :, 3:4],1/255)
        return Image.fromarray((mixed*255).clip(0,255).astype(np.uint8))
    return blend


def clip(row, path):
    keys = align(row)
    transitions = [transition(a,b) for a,b in zip(keys,keys[1:])]
    strip = Image.new("RGBA",(WIDTH*len(TIMING),HEIGHT))
    for index, moment in enumerate(TIMING):
        pos = int(moment)
        frame = Image.fromarray(keys[pos]) if pos==moment else transitions[pos](moment-pos)
        strip.paste(frame,(index*WIDTH,0))
    strip.save(path, "WEBP", quality=87, method=5, alpha_quality=96)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--pages", type=int, nargs="*")
    parser.add_argument("--refinements", action="store_true", help="pack refine-N.png pages using the recorded second-pass briefs")
    args = parser.parse_args()
    out = ROOT / "art/performances"
    (out / "clips").mkdir(parents=True, exist_ok=True)
    groups = [ORDER[i:i+4] for i in range(0, len(ORDER),4)]
    pattern = "page-{:02}.png"
    if args.refinements:
        index = {a["title"]:i for i,a in enumerate(CATALOG)}
        briefs = json.loads((ROOT/"art/performance-refinements.json").read_text())
        groups = [[index[item["title"]] for item in row] for row in briefs]
        pattern = "refine-{}.png"
    for page in args.pages if args.pages is not None else range(len(groups)):
        sheet = np.asarray(Image.open(args.source/pattern.format(page)).convert("RGBA"))
        sheet = clear_exterior(sheet)
        edges_y = dividers(sheet[:,:,3],0)
        for row,index in enumerate(groups[page]):
            band = sheet[edges_y[row]:edges_y[row+1]]
            edges_x = dividers(band[:,:,3],1)
            poses = [extract(band[:,left:right]) for left,right in zip(edges_x,edges_x[1:])]
            clip(poses, out/"clips"/(CATALOG[index]["id"]+".webp"))
        print("Packed",page,flush=True)
    meta = {}
    for i,action in enumerate(CATALOG):
        spec = dict(file="clips/"+action["id"]+".webp",group=action["group"],frames=len(TIMING),fps=10,weight=1)
        if i in (2,3,4,24,36,78,103):
            spec["travel"] = {2:"side",3:"float",4:"return",24:"side",36:"side",78:"float",103:"return"}[i]
        meta[action["title"]] = spec
    manifest = dict(version=2,clips=meta,idle=[a["title"] for a in CATALOG[5:50]+CATALOG[62:83]],
                    sleep=[CATALOG[107]["title"]],waking=[CATALOG[108]["title"]],bedtime=[CATALOG[106]["title"]])
    (out/"pet-plus.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+"\n")


if __name__ == "__main__":
    main()
