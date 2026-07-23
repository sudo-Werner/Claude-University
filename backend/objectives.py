"""Objective registry + resolver (Phase 0 objective-id backbone).

Single source of truth for objective identity. On disk (schemaVersion 3) a course
carries a course-level `objectives[]` registry of {id, text, bloom, knowledge}, and each
lesson carries `objectiveIds[]` referencing it -- no embedded lesson objectives. This
module is the one resolver every objective-reader goes through and the one builder every
writer goes through.

Two shapes exist by design:
- WIRE (compile/revise output, API responses, apply-revision input): objectives are
  embedded on each lesson as lesson["objectives"], exactly as before, optionally carrying
  an id. This is what the frontend and the LLM stages see.
- DISK (persisted course.json, v3): the registry + objectiveIds refs.

build_registry converts WIRE -> DISK (assigning/preserving ids). resolved_manifest
converts DISK -> WIRE (hydrating lesson["objectives"] from the registry). for_lesson is
the read primitive: it returns a lesson's objective dicts from whichever shape is present,
so a reader works on both a migrated (v3) and a not-yet-migrated (v2) course during the
deploy window. Course/module `outcomes` are NOT part of the registry.
"""
import re

_OBJ_ID_RE = re.compile(r"-o(\d+)$")


def objective_index(manifest):
    """Map objective id -> objective dict, from the course-level registry."""
    out = {}
    for o in manifest.get("objectives", []) or []:
        if isinstance(o, dict) and isinstance(o.get("id"), str):
            out[o["id"]] = o
    return out


def for_lesson(manifest, lesson):
    """A lesson's objective dicts: resolved through the registry when the lesson carries
    objectiveIds (v3 disk), else the lesson's embedded objectives (v2/wire), else [].
    The returned dicts are the registry's own objects by reference -- callers must not
    mutate them in place."""
    ids = lesson.get("objectiveIds")
    if isinstance(ids, list):
        index = objective_index(manifest)
        return [index[i] for i in ids if i in index]
    embedded = lesson.get("objectives")
    if isinstance(embedded, list):
        return embedded
    return []


def resolved_manifest(manifest):
    """DISK -> WIRE: a copy where every lesson carries embedded `objectives` (hydrated from
    the registry), so the frontend and the LLM stages see the pre-registry shape. The input
    manifest is not mutated, but the embedded objective dicts are the registry's own objects
    by reference -- callers must not mutate them in place."""
    modules = []
    for m in manifest.get("modules", []):
        lessons = [{**l, "objectives": for_lesson(manifest, l)} for l in m.get("lessons", [])]
        modules.append({**m, "lessons": lessons})
    return {**manifest, "modules": modules}


def _max_objective_num(manifest):
    nums = []
    for oid in ([o.get("id", "") for o in manifest.get("objectives", []) or [] if isinstance(o, dict)]):
        mo = _OBJ_ID_RE.search(oid or "")
        if mo:
            nums.append(int(mo.group(1)))
    for m in manifest.get("modules", []):
        for l in m.get("lessons", []):
            for oid in l.get("objectiveIds", []) or []:
                mo = _OBJ_ID_RE.search(oid or "")
                if mo:
                    nums.append(int(mo.group(1)))
            for o in l.get("objectives", []) or []:
                mo = _OBJ_ID_RE.search(o.get("id", "") if isinstance(o, dict) else "")
                if mo:
                    nums.append(int(mo.group(1)))
    return max(nums) if nums else 0


def build_registry(manifest):
    """WIRE -> DISK: lift every lesson's objectives into a course-level `objectives[]`
    registry with stable ids, replace them with `objectiveIds` refs, and stamp
    schemaVersion 3. An objective already carrying a valid, unused `<courseId>-oN` id keeps
    it (id preservation across revisions); a new one is minted above the current max. Reads
    each lesson via `for_lesson`, so it is idempotent on disk-shape input. Course/module
    `outcomes` are left untouched. The input manifest is not mutated."""
    course_id = manifest.get("id", "")
    counter = _max_objective_num(manifest)
    registry, used, modules = [], set(), []
    for m in manifest.get("modules", []):
        lessons = []
        for l in m.get("lessons", []):
            ids = []
            for o in for_lesson(manifest, l):
                if not isinstance(o, dict):
                    continue
                oid = o.get("id")
                if not (isinstance(oid, str) and _OBJ_ID_RE.search(oid) and oid not in used):
                    counter += 1
                    oid = f"{course_id}-o{counter}"
                used.add(oid)
                registry.append({"id": oid, "text": o.get("text", ""),
                                 "bloom": o.get("bloom", ""), "knowledge": o.get("knowledge", "")})
                ids.append(oid)
            new_l = {k: v for k, v in l.items() if k != "objectives"}
            new_l["objectiveIds"] = ids
            lessons.append(new_l)
        modules.append({**m, "lessons": lessons})
    return {**manifest, "schemaVersion": 3, "objectives": registry, "modules": modules}
