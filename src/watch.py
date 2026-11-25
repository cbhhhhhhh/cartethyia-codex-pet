"""Watch the shallow Codex rollout tree with Darwin vnode notifications."""

import os
import select


class RolloutWatch:
    def __init__(self, root):
        self.root = root
        self.queue = select.kqueue()
        self.descriptors = {}
        self.paths = {}
        self.initial = set()
        try:
            self.index(root, 0, self.initial)
        except Exception:
            self.close()
            raise

    def close(self):
        self.queue.close()
        for fd in self.paths:
            os.close(fd)
        self.paths.clear()
        self.descriptors.clear()

    def subscribe(self, path, depth):
        if path in self.descriptors:
            return False
        if len(self.paths) >= 2048:
            raise OSError("rollout watch limit")
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW)
        flags = (
            select.KQ_NOTE_WRITE
            | select.KQ_NOTE_EXTEND
            | select.KQ_NOTE_DELETE
            | select.KQ_NOTE_RENAME
        )
        try:
            event = select.kevent(
                fd,
                filter=select.KQ_FILTER_VNODE,
                flags=select.KQ_EV_ADD | select.KQ_EV_CLEAR,
                fflags=flags,
            )
            self.queue.control([event], 0, 0)
        except BaseException:
            os.close(fd)
            raise
        self.descriptors[path] = fd
        self.paths[fd] = (path, depth)
        return True

    def index(self, directory, depth, added):
        self.subscribe(directory, depth)
        for child in directory.iterdir():
            if child in self.descriptors or child.is_symlink():
                continue
            try:
                if depth < 3 and child.name.isdigit() and child.is_dir():
                    self.index(child, depth + 1, added)
                elif depth == 3 and child.suffix == ".jsonl" and child.is_file():
                    self.subscribe(child, 4)
                    added.add(child)
            except FileNotFoundError:
                pass

    def changes(self):
        changed = set()
        for event in self.queue.control(None, max(1, len(self.paths)), 0):
            info = self.paths.get(event.ident)
            if not info:
                continue
            path, depth = info
            if event.fflags & (select.KQ_NOTE_DELETE | select.KQ_NOTE_RENAME):
                self.paths.pop(event.ident)
                self.descriptors.pop(path, None)
                os.close(event.ident)
                if depth == 4:
                    changed.add(path)
                if path == self.root:
                    raise FileNotFoundError(str(path))
                if path.parent.is_dir():
                    self.index(path.parent, depth - 1, changed)
            elif depth == 4:
                changed.add(path)
            else:
                self.index(path, depth, changed)
        return changed
