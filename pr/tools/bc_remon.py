"""remonsterate as Beyond Chaos starts it (a child process per attempt), with our additions:

- (on; FF6_BC_REMON_FAST=0 turns it off) its hot path made fast with the same answers, so the same draws and the
  same seed (`check`: the same ROM and spoiler log): install_speedups (memoized sizes, scores, signatures; a set
  for its used-image list), install_fast_select (each monster size's compatible images scored and sorted once,
  not once per monster) and install_lazy_images (an image file opened only when chosen: the ~13,400 images'
  prepared sizes kept in remonsterate's folder, .image_sizes.json, made by the first run).

- (off; FF6_BC_REMON_CACHE=1) its prepared images cached (bc_home/remonsterate/.prepared_images.pickle, 77 MB):
  superseded by install_lazy_images.
- ROM-free (FF6_BC_ROMFREE_CHILD=1, set by tools/bc_romfree.py): its stand-ins, as BC's child process
  imports BC afresh.
- (dev) FF6_BC_REMON_PROFILE=PATH: a cProfile of each attempt (PATH.<pid>).

bc_run.run points BC's randomizer at child() (randomizer.remonsterate); the target is this module's function,
so a child process (spawn) imports it by name from tools/.
"""
import os
import pickle
import sys

CACHE_NAME = ".prepared_images.pickle"
VERSION = 1


def install_cache():
    import remonsterate.remonsterate as R
    path = os.path.join(R.file_paths, CACHE_NAME)
    cache, dirty = {}, [False]
    try:
        with open(path, "rb") as f:
            doc = pickle.load(f)
        if doc.get("version") == VERSION:
            cache = doc["images"]
    except (OSError, EOFError, pickle.UnpicklingError, AttributeError, KeyError, ValueError, TypeError):
        cache = {}
    original = R.prepare_image

    def prepare_image(image):
        fn = getattr(image, "filename", None)
        try:
            st = os.stat(fn)
            stamp = (st.st_size, st.st_mtime_ns)
        except (OSError, TypeError):
            return original(image)
        key = os.path.relpath(fn, R.sprite_paths).replace("\\", "/")
        hit = cache.get(key)
        if hit and hit[0] == stamp:
            out = pickle.loads(hit[1])
            out.filename = fn
            image.close()
            return out
        out = original(image)
        cache[key] = (stamp, pickle.dumps(out, protocol=pickle.HIGHEST_PROTOCOL))
        dirty[0] = True
        return out

    begin = R.begin_remonsterate

    def begin_remonsterate(*a, **kw):
        # every image is prepared by now (remonsterate's loop runs before this): keep what was new
        if dirty[0]:
            tmp = path + ".tmp"
            try:
                with open(tmp, "wb") as f:
                    pickle.dump({"version": VERSION, "images": cache}, f, protocol=pickle.HIGHEST_PROTOCOL)
                os.replace(tmp, path)
            except OSError:
                pass
            dirty[0] = False
        return begin(*a, **kw)

    R.prepare_image, R.begin_remonsterate = prepare_image, begin_remonsterate


def install_speedups():
    """remonsterate's hot path while it chooses each monster's image among ~13,400 (pure functions, memoized; the
    same answers, so the same draws and the same seed: `check`):
    - MonsterSpriteObject.width_tiles / height_tiles: recomputed from its stencil millions of times; memoized by
      (is_big, stencil).
    - get_size_compatibility(image): per monster and image, a function of the monster's tile size (now and its first
      max sizes) and the image's; memoized by those numbers (the monster's own per-file cache kept as it was).
    - DONE_IMAGES: a list asked `in` for every candidate of every monster; the same list, with a set beside it.
    - sig_func(image): an md5 of the file name and the seed, for every candidate in every sort; memoized."""
    import math
    import remonsterate.remonsterate as R
    M = R.MonsterSpriteObject
    width, height = M.width_tiles.fget, M.height_tiles.fget
    widths, heights, scores, sigs = {}, {}, {}, {}

    def width_tiles(self):
        key = (self.is_big, tuple(self.stencil))
        v = widths.get(key)
        if v is None:
            v = widths[key] = width(self)
        return v

    def height_tiles(self):
        key = tuple(self.stencil)
        v = heights.get(key)
        if v is None:
            v = heights[key] = height(self)
        return v

    M.width_tiles, M.height_tiles = property(width_tiles), property(height_tiles)

    def get_size_compatibility(self, image):
        # as remonsterate's: the monster's own cache by file name first, else computed (and kept there)
        if not hasattr(self, '_image_scores'):
            self._image_scores = {}
        if image.filename in self._image_scores:
            return self._image_scores[image.filename]
        if isinstance(image, str):
            image = R.Image.open(image)
        w, h = math.ceil(image.width / 8), math.ceil(image.height / 8)
        key = (self.max_width_tiles, self.max_height_tiles, self.width_tiles, self.height_tiles, w, h)
        if key in scores:
            score = scores[key]
        else:
            if w > self.max_width_tiles or h > self.max_height_tiles:
                score = None
            else:
                a, b = max(w, self.width_tiles), min(w, self.width_tiles)
                width_score = b / a
                a, b = max(h, self.height_tiles), min(h, self.height_tiles)
                score = width_score * (b / a)
            scores[key] = score
        self._image_scores[image.filename] = score
        return score

    M.get_size_compatibility = get_size_compatibility

    class DoneList(list):
        """remonsterate's DONE_IMAGES (appended to, its length compared, asked `in`), with a set for `in`."""

        def __init__(self, *a):
            super().__init__(*a)
            self._set = set(self)

        def append(self, x):
            super().append(x)
            self._set.add(x)

        def __contains__(self, x):
            return x in self._set

    M.DONE_IMAGES = DoneList(M.DONE_IMAGES)
    sig = R.sig_func

    def sig_func(c):
        key = (c.filename, R.get_seed())
        v = sigs.get(key)
        if v is None:
            v = sigs[key] = sig(c)
        return v

    R.sig_func = sig_func
    install_fast_select(R)
    install_lazy_images(R)


def install_fast_select(R):
    """select_image as remonsterate's, without re-scoring and re-sorting all ~13,400 images for each monster:
    for the whole image list (its first call per monster) the compatible images sorted by (score, sig_func) are
    kept per monster size (max width/height, width/height in tiles: what the score depends on) and the monster's
    candidates are that list less the images already used. The same list in the same order (the sort is stable and
    sig_func's names are unique; filtering keeps the order), so the same draws. The monster's own score cache gets
    the scores remonsterate would have kept (a retry after a failed load_image reads them, as remonsterate's)."""
    M = R.MonsterSpriteObject
    lists = {}      # monster size -> (the image list, [compatible images sorted], {file name: score})

    def sort_func_of(self):
        def sort_func(c):
            return self.get_size_compatibility(c), R.sig_func(c)
        return sort_func

    def say(text):
        R.pipe_print(output=text, connection=R.randomize_connection)

    def select_image(self, list_of_monsters, images=None):
        monster_original_name = None
        if self.get_index() < len(list_of_monsters):
            monster_original_name = list_of_monsters[self.get_index()].name.strip("_")
        if self.is_protected:
            if monster_original_name:
                say("Remonsterate: " + monster_original_name + " is protected and did not receive a randomized sprite.")
            self.load_image(self.image)
            return True

        done = self.DONE_IMAGES
        if images is None and not getattr(self, "_image_scores", None):   # (scores of its own: as remonsterate)
            images = M.import_images
            if len(images) == len(done):
                return False
            key = (self.max_width_tiles, self.max_height_tiles, self.width_tiles, self.height_tiles)
            hit = lists.get(key)
            if hit is None or hit[0] is not images:
                self._image_scores = {}
                comp = sorted([i for i in images if self.get_size_compatibility(i) is not None],
                              key=sort_func_of(self))
                hit = lists[key] = (images, comp, {i.filename: self._image_scores[i.filename] for i in comp})
            self._image_scores = dict(hit[2])
            candidates = [i for i in hit[1] if i.filename not in done]
            presorted = True
        else:
            if images is None:
                images = M.import_images
                if len(images) == len(done):
                    return False
            candidates = [i for i in images if i.filename not in done and self.get_size_compatibility(i) is not None]
            presorted = False

        if self.is_actually_big and R.random.random() > 0.1:
            temp = [c for c in candidates if c.width > 64 or c.height > 64]
            candidates = temp or candidates

        if hasattr(self, 'whitelist') and self.whitelist:
            candidates = [c for c in candidates if hasattr(c, 'tags') and c.tags >= self.whitelist]
            if not candidates:
                if monster_original_name:
                    say("Remonsterate: " + monster_original_name + " was not sprite randomized: " +
                        "No eligible sprites matching the whitelist tags '" + str(self.whitelist) + "' were found.")
                self.load_image(self.image)
                return True

        if hasattr(self, 'blacklist') and self.blacklist:
            candidates = [c for c in candidates if not (hasattr(c, 'tags') and c.tags & self.blacklist)]
            if not candidates:
                if monster_original_name:
                    say("Remonsterate: " + monster_original_name + " was not sprite randomized: " +
                        "No eligible sprites were left after processing blacklisted tags '" + str(self.blacklist) + "'.")
                self.load_image(self.image)
                return True

        if not candidates:
            self.load_image(self.image)
            if monster_original_name:
                say("Remonsterate: " + monster_original_name + " was not sprite randomized: No suitable sprite was found.")
            return True

        if not presorted:
            candidates = sorted(candidates, key=sort_func_of(self))
        max_index = len(candidates) - 1
        index = R.random.randint(R.random.randint(R.random.randint(0, max_index), max_index), max_index)
        chosen = candidates[index]
        done.append(chosen.filename)
        result = self.load_image(_real(chosen))
        if not result:
            self.select_image(images=candidates, list_of_monsters=list_of_monsters)
        return True

    M.select_image = select_image


# --- remonsterate's images, opened only when chosen ---------------------------------------------------------------
SIZES_NAME = ".image_sizes.json"
_prepare = [None]          # remonsterate's own prepare_image


class _Unopened:
    """What Image.open gives remonsterate's image loop for a file whose prepared size is known: nothing opened."""
    __slots__ = ("filename",)

    def __init__(self, filename):
        self.filename = filename


class _Lazy:
    """A prepared image remonsterate hasn't opened: its file name, prepared size and tags (all select_image reads);
    opened and prepared (remonsterate's prepare_image: no draws) when chosen: _real."""

    def __init__(self, filename, width, height):
        self.filename, self.width, self.height, self.tags = filename, width, height, set()
        self._image = None

    @property
    def size(self):
        return self.width, self.height

    def close(self):
        if self._image is not None:
            self._image.close()


def _real(image):
    if not isinstance(image, _Lazy):
        return image
    if image._image is None:
        from PIL import Image
        real = _prepare[0](Image.open(image.filename))
        if real.size != image.size:
            raise RuntimeError(f"bc_remon: {image.filename} is {real.size}, its known size {image.size}: "
                               f"delete {SIZES_NAME}")
        real.tags = image.tags
        image._image = real
    return image._image


def install_lazy_images(R):
    """remonsterate opens and prepares all ~13,400 images on every run (and every retry) though it loads ~416:
    their prepared sizes are kept in remonsterate's folder (.image_sizes.json, by file, size and time; ~1 MB) and a
    known file is opened only when chosen. A file new or changed since is opened and prepared as remonsterate does
    (and its size kept). The same images in the same order, the same draws (`check`)."""
    import json
    from PIL import Image as PILImage
    path = os.path.join(R.file_paths, SIZES_NAME)
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        sizes = doc["sizes"] if doc.get("version") == VERSION else {}
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        sizes = {}
    new = {}
    _prepare[0] = prepare = R.prepare_image

    def stamp(fn):
        st = os.stat(fn)
        return [st.st_size, st.st_mtime_ns]

    def rel(fn):
        return os.path.relpath(fn, R.sprite_paths).replace("\\", "/")

    class ImageModule:
        """PIL.Image for remonsterate, but open() of a known image file opens nothing."""

        def __getattr__(self, name):
            return getattr(PILImage, name)

        def open(self, fp, *a, **kw):
            if isinstance(fp, str) and not a and not kw:
                hit = sizes.get(rel(fp))
                try:
                    if hit and hit[:2] == stamp(fp):
                        return _Unopened(fp)
                except OSError:
                    pass
            return PILImage.open(fp, *a, **kw)

    def prepare_image(image):
        if isinstance(image, _Unopened):
            hit = sizes[rel(image.filename)]
            return _Lazy(image.filename, hit[2], hit[3])
        out = prepare(image)
        fn = getattr(out, "filename", None)
        try:
            new[rel(fn)] = stamp(fn) + list(out.size)
        except (OSError, TypeError, ValueError):
            pass
        return out

    begin = R.begin_remonsterate

    def begin_remonsterate(*a, **kw):
        # every image is in by now (remonsterate's loop runs before this): keep the sizes that were new
        if new:
            sizes.update(new)
            new.clear()
            tmp = path + ".tmp"
            try:
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump({"version": VERSION, "sizes": sizes}, f, separators=(",", ":"))
                os.replace(tmp, path)
            except OSError:
                pass
        return begin(*a, **kw)

    R.Image, R.prepare_image, R.begin_remonsterate = ImageModule(), prepare_image, begin_remonsterate


def child(*a, **kw):
    """remonsterate.remonsterate(...) in BC's child process, with the cache (and ROM-free, the stand-ins)."""
    here = os.path.dirname(os.path.abspath(__file__))
    if here not in sys.path:
        sys.path.insert(0, here)
    if os.environ.get("FF6_BC_ROMFREE_CHILD") == "1":
        import bc_romfree
        bc_romfree.patch_remonsterate()
    if os.environ.get("FF6_BC_REMON_CACHE") == "1":
        install_cache()
    if os.environ.get("FF6_BC_REMON_FAST", "1") != "0":
        install_speedups()
    from remonsterate.remonsterate import remonsterate
    prof = os.environ.get("FF6_BC_REMON_PROFILE")       # (dev) a cProfile of this attempt, to that path
    if prof:
        import cProfile
        p = cProfile.Profile()
        try:
            return p.runcall(remonsterate, *a, **kw)
        finally:
            p.dump_stats(f"{prof}.{os.getpid()}")
    return remonsterate(*a, **kw)


def check(seed="2718281828", preset="Advanced Player"):
    """(dev) Our additions keep the seed: BC run on the ROM plain (FF6_BC_REMON_FAST=0), with the speedups and no
    image sizes known (cold: they're kept) and with them known (warm): the same output ROM and spoiler log each
    time. Prints the times. The sizes file there before is put back after."""
    import shutil
    import subprocess
    import tempfile
    here = os.path.dirname(os.path.abspath(__file__))
    tmp = tempfile.mkdtemp(prefix="bc_remon_")
    code = ("import sys, time, hashlib; sys.path.insert(0, %r); import bc_run, bc_trace, prdata as P, ff6snes as S\n"
            "t = time.time(); d, log = bc_run.run(S.rom_bytes(P.VANILLA_ROM), %r, 'normal', bc_trace.preset_flags(%r),"
            " say=lambda m: None)\n"
            "print(hashlib.sha1(d).hexdigest(), hashlib.sha1(log.encode()).hexdigest(), round(time.time() - t, 1))"
            % (here, seed, preset))
    import bc_run
    folder = os.path.join(os.path.abspath(bc_run.HOME), "remonsterate")
    kept = {n: os.path.join(tmp, n) for n in (CACHE_NAME, SIZES_NAME)}
    runs = []
    try:
        for n, k in kept.items():
            if os.path.exists(os.path.join(folder, n)):
                os.replace(os.path.join(folder, n), k)
        for label, env in (("plain", {"FF6_BC_REMON_CACHE": "0", "FF6_BC_REMON_FAST": "0"}),
                           ("fast, sizes unknown", {"FF6_BC_REMON_CACHE": "0", "FF6_BC_REMON_FAST": "1"}),
                           ("fast, sizes known", {"FF6_BC_REMON_CACHE": "0", "FF6_BC_REMON_FAST": "1"})):
            p = subprocess.run([sys.executable, "-W", "ignore", "-c", code], capture_output=True, text=True,
                               env=dict(os.environ, **env), encoding="utf-8", errors="replace")
            line = (p.stdout.strip().splitlines() or ["?"])[-1]
            runs.append((label, line))
            print(f"{label}: {line}" if p.returncode == 0 else f"{label}: failed {p.stderr[-800:]}")
    finally:
        for n, k in kept.items():
            mine = os.path.join(folder, n)
            if os.path.exists(k):
                os.replace(k, mine)
        shutil.rmtree(tmp, ignore_errors=True)
    same = len({r[1].rsplit(" ", 1)[0] for r in runs}) == 1
    print("the same ROM and log every time" if same else "DIFFERENT")
    return same


if __name__ == "__main__":
    sys.exit(0 if check(*sys.argv[1:3]) else 1)
