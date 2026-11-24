"""Our own "blocky parkour" background gameplay, drawn entirely by code.

The split-screen facts channel (Mochi 2026-11-24, reference TikTok) puts satisfying parkour under the
main footage. Downloading other people's Minecraft parkour is a copyright-strike risk, so this renders a
fresh run every time: a voxel world made of pixel-textured blocks floating over lava, with a first-person
camera that sprint-jumps from block to block. No game files or textures are used, so it's 100% ours.

    python -m splitfacts.parkour --seconds 45 --out parkour.mp4 [--seed 3]
"""
import argparse
import math
import subprocess

import numpy as np
from numba import njit, prange

RW, RH = 540, 480          # render size; ffmpeg scales 2x (nearest) to 1080x960 for the crisp pixel look
FOV = math.radians(78)
SX, SY = 44, 52            # world width (x) and height (y)

AIR, GRASS, DIRT, STONE, LAVA, PLANK, LOG, LEAF, OBSID, SAND = range(10)
WOOL = list(range(10, 16))  # red, pink, lime, cyan, yellow, purple
WOOL_RGB = [(200, 50, 45), (235, 120, 170), (110, 200, 40), (30, 150, 160), (240, 200, 40), (130, 50, 180)]
NB = 16


def _noise(rng, base, var, shape=(16, 16)):
    n = rng.integers(-var, var + 1, size=shape + (1,))
    return np.clip(np.array(base, np.float32)[None, None, :] + n, 0, 255).astype(np.float32)


def make_textures(rng) -> np.ndarray:
    """tex[block, face(0 top, 1 side, 2 bottom), v, u, rgb], 16x16 procedural pixel art."""
    t = np.zeros((NB, 3, 16, 16, 3), np.float32)
    dirt = _noise(rng, (134, 96, 67), 18)
    grass_top = _noise(rng, (95, 160, 60), 22)
    side = dirt.copy()
    edge = 3 + rng.integers(0, 3, size=16)
    for u in range(16):
        side[: edge[u], u] = grass_top[: edge[u], u]
    t[GRASS] = [grass_top, side, dirt]
    t[DIRT] = [dirt, dirt, dirt]
    stone = _noise(rng, (125, 125, 125), 16)
    for _ in range(10):  # cracks
        y, x = rng.integers(0, 16, 2)
        stone[y, x:x + 3] *= 0.75
    t[STONE] = [stone, stone, stone]
    lava = _noise(rng, (230, 100, 20), 30)
    lava[rng.random((16, 16)) < 0.15] = (255, 200, 60)
    t[LAVA] = [lava, lava, lava]
    plank = _noise(rng, (170, 130, 80), 12)
    plank[3::4, :] *= 0.7
    t[PLANK] = [plank, plank, plank]
    bark = _noise(rng, (100, 75, 45), 14)
    bark[:, 1::3] *= 0.8
    ring = _noise(rng, (180, 145, 90), 10)
    t[LOG] = [ring, bark, ring]
    leaf = _noise(rng, (60, 130, 40), 30)
    leaf[rng.random((16, 16)) < 0.2] *= 0.5
    t[LEAF] = [leaf, leaf, leaf]
    obs = _noise(rng, (30, 20, 45), 12)
    obs[rng.random((16, 16)) < 0.1] = (90, 60, 130)
    t[OBSID] = [obs, obs, obs]
    sand = _noise(rng, (220, 205, 150), 10)
    t[SAND] = [sand, sand, sand]
    for b, rgb in zip(WOOL, WOOL_RGB):
        w = _noise(rng, rgb, 10)
        w[::4, :] *= 0.9
        w[:, ::4] *= 0.92
        t[b] = [w, w, w]
    return t


def build_course(rng, seconds: float):
    """World grid + the list of landing spots the camera jumps between."""
    n_jumps = int(seconds * 1.6) + 12
    sz = n_jumps * 5 + 80
    w = np.zeros((SX, SY, sz), np.uint8)
    w[:, :2, :] = LAVA
    # stone pillars and floating islands for depth
    for _ in range(sz // 6):
        x, z = rng.integers(0, SX), rng.integers(0, sz)
        if abs(x - SX // 2) < 9:
            continue
        h = rng.integers(4, 30)
        r = rng.integers(1, 3)
        w[max(0, x - r):x + r, 2:h, max(0, z - r):z + r] = rng.choice([STONE, STONE, OBSID, SAND])
        if rng.random() < 0.4:  # tree on top
            w[x, h:h + 4, z] = LOG
            w[max(0, x - 2):x + 3, h + 3:h + 6, max(0, z - 2):z + 3] = LEAF
            w[x, h:h + 4, z] = LOG

    spots = []
    x, y, z = SX // 2, 20, 4
    w[x - 2:x + 3, y - 1, z - 3:z + 4] = GRASS   # start platform
    w[x - 2:x + 3, y - 4:y - 1, z - 3:z + 4] = DIRT
    spots.append((x + 0.5, y, z + 0.5))
    theme = rng.choice(WOOL)
    for i in range(n_jumps):
        if i % 12 == 0:
            theme = rng.choice(WOOL + [STONE, PLANK, OBSID])
        dz = int(rng.integers(2, 5))
        dx = int(rng.integers(-2, 3))
        dy = int(rng.choice([-1, 0, 0, 1])) if dz <= 3 else int(rng.choice([-1, 0]))
        x = int(np.clip(x + dx, 12, SX - 13))
        y = int(np.clip(y + dy, 10, 34))
        z += dz
        kind = rng.random()
        block = theme if rng.random() < 0.8 else rng.choice(WOOL)
        if kind < 0.12:           # wide platform: run across it
            w[x - 1:x + 2, y - 1, z:z + 4] = GRASS
            w[x - 1:x + 2, y - 3:y - 1, z:z + 4] = DIRT
            spots.append((x + 0.5, y, z + 0.5))
            z += 3
        else:
            w[x, y - 1, z] = block
        spots.append((x + 0.5, y, z + 0.5))
    return w, spots


def camera_path(spots, fps: int, seconds: float, speed: float = 4.6):
    """Per-frame eye position, sprint-jumping between spots."""
    pos = []
    for (x0, y0, z0), (x1, y1, z1) in zip(spots, spots[1:]):
        d = math.hypot(x1 - x0, z1 - z0)
        flat = d >= 2.9 and abs(x1 - x0) < 0.1 and y1 == y0 and (z1 - z0) == 3  # run across a platform
        steps = max(2, int(round(d / speed * fps)))
        apex = 0.0 if flat else max(1.15, (y1 - y0) + 0.55)
        for k in range(steps):
            s = k / steps
            yy = y0 + (y1 - y0) * s + 4 * apex * s * (1 - s)
            pos.append((x0 + (x1 - x0) * s, yy + 1.62, z0 + (z1 - z0) * s))
    pos = np.array(pos, np.float64)
    n = int(seconds * fps)
    return pos[:n] if len(pos) >= n else np.vstack([pos, np.repeat(pos[-1:], n - len(pos), 0)])


@njit(parallel=True, fastmath=True, cache=True)
def render(world, tex, cam, yaw, pitch, out):
    h, w_ = out.shape[0], out.shape[1]
    sxw, syw, szw = world.shape
    cy, sy_ = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    fx = math.tan(0.5 * 1.3614) # FOV 78 deg
    fy = fx * h / w_
    maxd = 64.0
    for j in prange(h):
        for i in range(w_):
            # camera-space ray
            u = (2.0 * (i + 0.5) / w_ - 1.0) * fx
            v = (1.0 - 2.0 * (j + 0.5) / h) * fy
            # forward = (sin(yaw)cos(p), sin(p), cos(yaw)cos(p)); right = (cos(yaw), 0, -sin(yaw)); up = r x f
            fxw, fyw, fzw = sy_ * cp, sp, cy * cp
            rxw, ryw, rzw = cy, 0.0, -sy_
            uxw, uyw, uzw = -sy_ * sp, cp, -cy * sp
            dx = fxw + u * rxw + v * uxw
            dy = fyw + u * ryw + v * uyw
            dz = fzw + u * rzw + v * uzw
            inv = 1.0 / math.sqrt(dx * dx + dy * dy + dz * dz)
            dx *= inv; dy *= inv; dz *= inv
            # sky
            tsky = max(0.0, dy)
            sr = 150.0 + (90.0 - 150.0) * tsky
            sg = 200.0 + (150.0 - 200.0) * tsky
            sb = 255.0 + (240.0 - 255.0) * tsky
            r, g, b = sr, sg, sb
            ox, oy, oz = cam[0], cam[1], cam[2]
            ix, iy, iz = int(math.floor(ox)), int(math.floor(oy)), int(math.floor(oz))
            stx = 1 if dx > 0 else -1
            sty = 1 if dy > 0 else -1
            stz = 1 if dz > 0 else -1
            tdx = abs(1.0 / dx) if dx != 0 else 1e30
            tdy = abs(1.0 / dy) if dy != 0 else 1e30
            tdz = abs(1.0 / dz) if dz != 0 else 1e30
            tmx = ((ix + 1 - ox) if dx > 0 else (ox - ix)) * tdx
            tmy = ((iy + 1 - oy) if dy > 0 else (oy - iy)) * tdy
            tmz = ((iz + 1 - oz) if dz > 0 else (oz - iz)) * tdz
            t = 0.0
            axis = -1
            for _ in range(400):
                if tmx < tmy and tmx < tmz:
                    ix += stx; t = tmx; tmx += tdx; axis = 0
                elif tmy < tmz:
                    iy += sty; t = tmy; tmy += tdy; axis = 1
                else:
                    iz += stz; t = tmz; tmz += tdz; axis = 2
                if t > maxd:
                    break
                if iy < 2 and (ix < 0 or ix >= sxw or iz < 0 or iz >= szw or iy < 0):
                    blk = 4  # lava sea everywhere around the world
                elif ix < 0 or ix >= sxw or iy >= syw or iz < 0 or iz >= szw:
                    if iy >= syw and dy > 0:
                        break
                    continue
                else:
                    blk = world[ix, iy, iz]
                if blk == 0:
                    continue
                hx, hy, hz = ox + dx * t, oy + dy * t, oz + dz * t
                if axis == 1:
                    face = 0 if sty < 0 else 2
                    tu, tv = hx - math.floor(hx), hz - math.floor(hz)
                    shade = 1.0 if sty < 0 else 0.5
                elif axis == 0:
                    face = 1
                    tu, tv = hz - math.floor(hz), 1.0 - (hy - math.floor(hy))
                    shade = 0.62
                else:
                    face = 1
                    tu, tv = hx - math.floor(hx), 1.0 - (hy - math.floor(hy))
                    shade = 0.8
                if blk == 4:
                    shade = 1.0
                pu = min(15, int(tu * 16.0))
                pv = min(15, int(tv * 16.0))
                cr = tex[blk, face, pv, pu, 0] * shade
                cg = tex[blk, face, pv, pu, 1] * shade
                cb = tex[blk, face, pv, pu, 2] * shade
                fog = min(1.0, max(0.0, (t - 20.0) / (maxd - 20.0)))
                fog = fog * fog
                r = cr + (sr - cr) * fog
                g = cg + (sg - cg) * fog
                b = cb + (sb - cb) * fog
                break
            out[j, i, 0] = min(255.0, r)
            out[j, i, 1] = min(255.0, g)
            out[j, i, 2] = min(255.0, b)


def make(out_path: str, seconds: float = 45.0, seed: int | None = None, fps: int = 30) -> str:
    rng = np.random.default_rng(seed)
    tex = make_textures(rng)
    world, spots = build_course(rng, seconds)
    path = camera_path(spots, fps, seconds)
    n = len(path)
    # look toward where we'll be ~1.3 s from now, smoothed so the view never snaps
    look = int(0.9 * fps)
    yaw = 0.0
    frame = np.zeros((RH, RW, 3), np.uint8)
    proc = subprocess.Popen(
        ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
         "-s", f"{RW}x{RH}", "-r", str(fps), "-i", "-",
         "-vf", "scale=1080:960:flags=neighbor", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", out_path],
        stdin=subprocess.PIPE)
    for f in range(n):
        a, b = path[f], path[min(n - 1, f + look)]
        target = math.atan2(b[0] - a[0], b[2] - a[2]) if abs(b[2] - a[2]) + abs(b[0] - a[0]) > 0.01 else yaw
        yaw += (target - yaw) * 0.12 if f else (target - yaw)
        bob = 0.015 * math.sin(f * 0.35)
        render(world, tex, a, yaw, -0.62 + bob, frame)
        # crosshair
        cx, cy = RW // 2, RH // 2
        frame[cy, cx - 6:cx + 7] = 235
        frame[cy - 6:cy + 7, cx] = 235
        proc.stdin.write(frame.tobytes())
    proc.stdin.close()
    if proc.wait():
        raise RuntimeError("ffmpeg failed while writing parkour video")
    return out_path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seconds", type=float, default=45)
    ap.add_argument("--seed", type=int)
    ap.add_argument("--out", default="parkour.mp4")
    a = ap.parse_args()
    make(a.out, a.seconds, a.seed)
