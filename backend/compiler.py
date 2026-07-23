"""Staged, web-grounded course compiler (sub-project A). Turns a learner brief into a
compiled, Bloom-tagged, prerequisite-graphed syllabus. Grounded stages (outline, accuracy
sweep) use run_sourced + generation._resolve_sources (only real retrieved URLs survive);
structured stages (objectives/graph) use run_structured. Each stage validates its output."""
import json
import re

from backend import claude_client, generation


def valid_outline(obj):
    if not isinstance(obj, dict):
        return False
    if not (isinstance(obj.get("title"), str) and obj["title"].strip()):
        return False
    level = obj.get("level")
    if not (isinstance(level, dict) and level.get("code") in generation.LEVEL_CODES
            and isinstance(level.get("label"), str) and level["label"].strip()):
        return False
    modules = obj.get("modules")
    if not (isinstance(modules, list) and modules):
        return False
    for m in modules:
        if not (isinstance(m, dict) and isinstance(m.get("title"), str) and m["title"].strip()):
            return False
        lessons = m.get("lessons")
        if not (isinstance(lessons, list) and lessons):
            return False
        for l in lessons:
            if not (isinstance(l, dict) and isinstance(l.get("id"), str) and l["id"]):
                return False
            if not (isinstance(l.get("title"), str) and l["title"].strip()):
                return False
            if not (isinstance(l.get("estMinutes"), (int, float)) and l["estMinutes"] > 0):
                return False
    return True


def _outline_prompt(learner_brief):
    return (
        "You are a university curriculum designer. Using web search, consult CANONICAL sources for "
        "this subject — university syllabi (.edu), established textbooks, and professional-society "
        "curricula — and design a course OUTLINE grounded in what a real course at the appropriate "
        "level covers.\n"
        f"Learner brief (JSON): {json.dumps(learner_brief, ensure_ascii=False)}\n\n"
        "Decide the DEPTH LEVEL from the learner's goal, background, and desired depth. Choose exactly "
        "one level code from: foundation, bachelor-y1, bachelor-y2, bachelor-y3, master. Size the "
        "outline to a real course at that level: enough modules and lessons, each lesson carrying an "
        "estimated total effort in minutes (estMinutes = reading + practice + review), so the whole "
        "course plausibly totals 125-150 hours. Give each lesson a stable id 'l1','l2',... in reading "
        "order and each module an id 'm1','m2',.... List ONLY grounding sources whose URL you actually "
        "retrieved via search.\n"
        "Reply with ONLY a JSON object, no prose, no code fence:\n"
        '{"title": "...", "subtitle": "...", "level": {"code": "bachelor-y2", "label": "Bachelor '
        'Year 2-equivalent"}, "targetHours": 130, "groundingSources": [{"title": "...", "url": '
        '"https://..."}], "modules": [{"id": "m1", "title": "...", "lessons": [{"id": "l1", '
        '"title": "...", "estMinutes": 90}]}]}'
    )


def _grounded_outline(learner_brief, *, generate_sourced):
    obj, captured = generate_sourced(_outline_prompt(learner_brief), valid_outline)
    sources = generation._resolve_sources(obj.get("groundingSources"), captured)
    return obj, sources


def valid_objectives_result(obj):
    if not isinstance(obj, dict):
        return False
    if not generation.valid_outcomes(obj.get("outcomes")):
        return False
    skills = obj.get("skills")
    if not (isinstance(skills, list) and skills and all(isinstance(s, str) and s.strip() for s in skills)):
        return False
    modules = obj.get("modules")
    if not (isinstance(modules, list) and modules):
        return False
    for m in modules:
        if not (isinstance(m, dict) and generation.valid_outcomes(m.get("outcomes"))):
            return False
        for l in m.get("lessons", []):
            if not (isinstance(l, dict) and l.get("id") and generation.valid_outcomes(l.get("objectives"))):
                return False
    return generation.valid_prereq_graph(modules)


def _module_objectives_prompt(module, earlier_lessons):
    return (
        "You are designing learning objectives and prerequisites for ONE module of a course, using "
        "BACKWARD DESIGN. This module (JSON):\n"
        f"{json.dumps(module, ensure_ascii=False)}\n"
        "Lessons ALREADY covered earlier in the course — you may cite any of these as a prerequisite by "
        "its id:\n"
        f"{json.dumps(earlier_lessons, ensure_ascii=False)}\n\n"
        "For EACH lesson in THIS module write 1-3 MEASURABLE objectives. Every objective centers on an "
        "observable action verb and is tagged with a Bloom level (remember, understand, apply, analyze, "
        "evaluate, create) and a knowledge dimension (factual, conceptual, procedural, metacognitive). "
        "NEVER use 'understand', 'know', 'learn', 'appreciate', 'grasp', 'be aware/familiar' in objective "
        "text — use verbs like calculate, derive, compare, implement, critique, design. Also write 1-3 "
        "outcomes for the module as a whole. For each lesson set 'prereqs' to the ids of EARLIER lessons "
        "it directly builds on — earlier lessons in THIS module, or ids from the already-covered list "
        "above (may be empty). Preserve every lesson id, title, and estMinutes EXACTLY.\n"
        "Reply with ONLY a JSON object, no prose, no code fence:\n"
        '{"outcomes": [{"text": "...", "bloom": "apply", "knowledge": "procedural"}], "lessons": '
        '[{"id": "l1", "title": "...", "objectives": [{"text": "Calculate ...", "bloom": "apply", '
        '"knowledge": "procedural"}], "prereqs": []}]}'
    )


def valid_module_objectives(obj):
    if not isinstance(obj, dict):
        return False
    if not generation.valid_outcomes(obj.get("outcomes")):
        return False
    lessons = obj.get("lessons")
    if not (isinstance(lessons, list) and lessons):
        return False
    for l in lessons:
        if not (isinstance(l, dict) and l.get("id") and generation.valid_outcomes(l.get("objectives"))):
            return False
        prereqs = l.get("prereqs", [])
        if not (isinstance(prereqs, list) and all(isinstance(p, str) for p in prereqs)):
            return False
    return True


def _course_rollup_prompt(title, module_summaries):
    return (
        "You are rolling module-level outcomes up into course-level outcomes and skills for a course "
        f"titled {json.dumps(title, ensure_ascii=False)}. Modules and their outcomes (JSON):\n"
        f"{json.dumps(module_summaries, ensure_ascii=False)}\n\n"
        "Write 3-6 course-level outcomes. Each centers on an observable action verb and is Bloom-tagged "
        "and knowledge-tagged; NEVER use 'understand', 'know', 'learn', 'appreciate', 'grasp', 'be "
        "aware/familiar'. Then list the concrete SKILLS the learner can do by the end. Reply with ONLY a "
        "JSON object, no prose, no code fence:\n"
        '{"outcomes": [{"text": "...", "bloom": "analyze", "knowledge": "conceptual"}], "skills": ["..."]}'
    )


def valid_course_rollup(obj):
    if not isinstance(obj, dict):
        return False
    if not generation.valid_outcomes(obj.get("outcomes")):
        return False
    skills = obj.get("skills")
    return isinstance(skills, list) and bool(skills) and all(isinstance(s, str) and s.strip() for s in skills)


def _objectives_and_graph(outline, *, verify):
    """Backward-design objectives + prereq graph, generated ONE MODULE AT A TIME so each structured
    call stays small enough to finish inside the CLI timeout on large courses. Each later module is
    given the ids/titles of all earlier lessons, so cross-module prerequisites survive. A final tiny
    roll-up call turns the module outcomes into course-level outcomes and skills. Returns the SAME
    shape a single whole-course pass produced, so _merge_objectives consumes it unchanged."""
    modules_out, module_summaries, earlier = [], [], []
    for m in outline.get("modules", []):
        module_in = {"id": m.get("id"), "title": m.get("title"),
                     "lessons": [{"id": l.get("id"), "title": l.get("title"), "estMinutes": l.get("estMinutes")}
                                 for l in m.get("lessons", [])]}
        # Require the response to carry EVERY lesson we sent: a dropped lesson would pass
        # shape validation, get objectives: [], and 502 the whole compile downstream —
        # rejecting here converts that into run_structured's cheap targeted retry.
        expected = len(module_in["lessons"])
        res = verify(
            _module_objectives_prompt(module_in, earlier),
            lambda o: valid_module_objectives(o) and len(o.get("lessons", [])) == expected,
        )
        outcomes = res.get("outcomes", []) if isinstance(res, dict) else []
        lessons = res.get("lessons", []) if isinstance(res, dict) else []
        modules_out.append({"id": m.get("id"), "title": m.get("title"), "outcomes": outcomes, "lessons": lessons})
        module_summaries.append({"title": m.get("title"), "outcomes": outcomes})
        earlier += [{"id": l.get("id"), "title": l.get("title")} for l in m.get("lessons", [])]
    rollup = verify(_course_rollup_prompt(outline.get("title", ""), module_summaries), valid_course_rollup)
    return {"outcomes": rollup.get("outcomes", []) if isinstance(rollup, dict) else [],
            "skills": rollup.get("skills", []) if isinstance(rollup, dict) else [],
            "modules": modules_out}


def _merge_objectives(outline, result):
    """Graft the objectives result onto the outline BY POSITION: the outline's ids, titles, and
    estMinutes always win (the model is told to preserve them, but we enforce it), and prereqs are
    remapped from the result's lesson ids to the outline's and filtered to earlier-only/known edges.
    Guarantees a valid prereq graph for both new-course compile and existing-course enrich."""
    out_lessons = [l for m in outline.get("modules", []) for l in m.get("lessons", [])]
    res_lessons = [l for m in result.get("modules", []) for l in m.get("lessons", []) if isinstance(l, dict)]
    id_map = {r.get("id"): o.get("id") for r, o in zip(res_lessons, out_lessons)}
    res_modules = result.get("modules", [])
    seen, modules = set(), []
    for mi, m in enumerate(outline.get("modules", [])):
        rm = res_modules[mi] if mi < len(res_modules) and isinstance(res_modules[mi], dict) else {}
        r_lessons = rm.get("lessons", []) if isinstance(rm.get("lessons"), list) else []
        lessons = []
        for li, l in enumerate(m.get("lessons", [])):
            rl = r_lessons[li] if li < len(r_lessons) and isinstance(r_lessons[li], dict) else {}
            raw = rl.get("prereqs", []) if isinstance(rl.get("prereqs"), list) else []
            prereqs = [id_map.get(p, p) for p in raw]
            prereqs = [p for p in prereqs if p in seen]  # earlier-only + known
            lessons.append({
                "id": l.get("id"), "title": l.get("title"), "estMinutes": l.get("estMinutes"),
                "objectives": rl.get("objectives", []) if isinstance(rl.get("objectives"), list) else [],
                "prereqs": prereqs,
            })
            seen.add(l.get("id"))
        modules.append({
            "id": m.get("id"), "title": m.get("title"),
            "outcomes": rm.get("outcomes", []) if isinstance(rm.get("outcomes"), list) else [],
            "lessons": lessons,
        })
    return {"outcomes": result.get("outcomes", []), "skills": result.get("skills", []), "modules": modules}


def _lesson_ids(course):
    return [l.get("id") for m in course.get("modules", []) for l in m.get("lessons", [])]


def _sweep_audit_prompt(enriched, grounding_sources):
    return (
        "You are a subject-matter expert auditing a course's outline and objectives for ACCURACY "
        "against canonical sources. Use web search to verify. Course as JSON:\n"
        f"{json.dumps(enriched, ensure_ascii=False)}\n"
        f"Grounding sources: {json.dumps(grounding_sources, ensure_ascii=False)}\n\n"
        "Are the topics correct and current, the ordering sound, the objectives accurate and correctly "
        "leveled, with no glaring omissions for a course at this level? Reply with ONLY a JSON object, "
        "no prose, no fence. If it is sound, reply exactly {\"ok\": true}. Otherwise "
        "{\"ok\": false, \"issues\": [\"<each specific inaccuracy or omission>\"]}."
    )


def _sweep_correct_prompt(enriched, issues):
    joined = "; ".join(str(i) for i in issues)
    return (
        "You are a subject-matter expert correcting a course's outline and objectives. Use web search "
        "to ground corrections in canonical sources. Course as JSON:\n"
        f"{json.dumps(enriched, ensure_ascii=False)}\n"
        f"A reviewer flagged these problems to fix: {joined}\n\n"
        "Return a CORRECTED version with the SAME JSON shape and the SAME module/lesson ids. Fix only "
        "what is needed for accuracy; keep objectives measurable and Bloom-tagged; keep prereqs "
        "earlier-only. Reply with ONLY the corrected JSON object, no prose, no code fence:\n"
        "{\"outcomes\": [...], \"skills\": [...], \"modules\": [...]}"
    )


def _accuracy_sweep(enriched, grounding_sources, *, generate_sourced):
    """Web-grounded, audit-first accuracy pass. Cheap audit against the sources; rewrite only the
    flagged parts. Returns the enriched course UNCHANGED if the audit clears it, anything errors, or
    the correction fails re-validation — the sweep can only improve accuracy, never make it worse."""
    try:
        audit, _ = generate_sourced(_sweep_audit_prompt(enriched, grounding_sources), generation.valid_audit)
    except claude_client.ClaudeError:
        return enriched
    if not (isinstance(audit, dict) and audit.get("ok") is False):
        return enriched  # clean or unparseable -> trust the input
    issues = audit.get("issues") if isinstance(audit.get("issues"), list) else []
    try:
        corrected, _ = generate_sourced(_sweep_correct_prompt(enriched, issues), valid_objectives_result)
    except claude_client.ClaudeError:
        return enriched
    if not valid_objectives_result(corrected):
        return enriched
    # The sweep corrects CONTENT only. A correction that changes the lesson-id set (adds, drops, or
    # renames lessons) must be rejected, or it breaks migration's id/structure-preservation guarantee
    # and progress keyed on those ids. Fall back to the aligned pre-correction course.
    if _lesson_ids(corrected) != _lesson_ids(enriched):
        return enriched
    return corrected


def _brief_paragraph(learner_brief, level):
    goal = (learner_brief.get("goal") or "").strip()
    depth = (learner_brief.get("desiredDepth") or "").strip()
    background = (learner_brief.get("background") or "").strip()
    parts = []
    if goal:
        parts.append(f"The learner wants to be able to {goal}")
    parts.append(f"Pitch the material at {level.get('label', 'the declared level')}")
    if depth:
        parts.append(f"desired depth: {depth}")
    if background:
        parts.append(f"background: {background}")
    return ". ".join(parts) + "."


def _assemble_contract(learner_brief, outline, enriched, grounding_sources):
    # estMinutes is authoritative from the outline (objectives stage may not echo it); overlay it
    # onto the enriched lessons by id so the compiled course carries per-lesson estMinutes.
    est = {l.get("id"): l.get("estMinutes", 0)
           for m in outline.get("modules", []) for l in m.get("lessons", [])}
    modules = []
    for m in enriched.get("modules", []):
        lessons = [{**l, "estMinutes": est.get(l.get("id"), l.get("estMinutes", 0))}
                   for l in m.get("lessons", [])]
        modules.append({**m, "lessons": lessons})
    total_minutes = sum(est.values())
    level = outline.get("level", {})
    return {
        "schemaVersion": 3,
        "title": outline.get("title", ""),
        "subtitle": outline.get("subtitle", ""),
        "brief": _brief_paragraph(learner_brief, level),
        "learnerBrief": learner_brief,
        "level": level,
        "targetHours": round(total_minutes / 60) or 1,
        "skills": enriched.get("skills", []),
        "outcomes": enriched.get("outcomes", []),
        "groundingSources": grounding_sources,
        "modules": modules,
    }


def compile_course(learner_brief, *, generate_sourced, verify):
    outline, sources = _grounded_outline(learner_brief, generate_sourced=generate_sourced)
    enriched = _merge_objectives(outline, _objectives_and_graph(outline, verify=verify))
    swept = _accuracy_sweep(enriched, sources, generate_sourced=generate_sourced)
    return _assemble_contract(learner_brief, outline, swept, sources)


def _brief_from_manifest(manifest):
    return {"goal": manifest.get("brief", ""), "background": "", "priorKnowledge": [],
            "motivation": "", "desiredDepth": ""}


def _enrich_outline_prompt(manifest):
    skeleton = {"title": manifest.get("title", ""), "subtitle": manifest.get("subtitle", ""),
                "modules": [{"id": m.get("id"), "title": m.get("title"),
                             "lessons": [{"id": l.get("id"), "title": l.get("title")}
                                         for l in m.get("lessons", [])]}
                            for m in manifest.get("modules", [])]}
    return (
        "You are retrofitting rigor onto an EXISTING course WITHOUT changing its structure. Using web "
        "search, consult canonical sources for the subject. Existing outline:\n"
        f"{json.dumps(skeleton, ensure_ascii=False)}\n\n"
        "Do NOT add, remove, reorder, or rename any module or lesson, and keep every id EXACTLY. Decide "
        "the appropriate level code (foundation, bachelor-y1, bachelor-y2, bachelor-y3, master) from the "
        "material, add an estimated total effort in minutes (estMinutes) to each existing lesson, and "
        "list the real grounding sources you used. Reply with ONLY a JSON object, no prose, no fence, "
        "echoing every id and title unchanged:\n"
        '{"title": "...", "subtitle": "...", "level": {"code": "...", "label": "..."}, '
        '"groundingSources": [{"title": "...", "url": "..."}], "modules": [{"id": "m1", "title": "...", '
        '"lessons": [{"id": "...", "title": "...", "estMinutes": 90}]}]}'
    )


def _grounded_outline_for_existing(manifest, *, generate_sourced):
    """Migration outline: rebuild the outline from the EXISTING manifest structure (ids, titles, and
    order preserved regardless of what the model echoes), taking only the level and per-lesson
    estMinutes from the grounded reply. Guarantees progress-critical ids survive."""
    obj, captured = generate_sourced(_enrich_outline_prompt(manifest), valid_outline)
    est = {l["id"]: l.get("estMinutes", 60)
           for m in obj.get("modules", []) for l in m.get("lessons", []) if isinstance(l, dict) and l.get("id")}
    # position-based fallback when the model did not echo the real ids
    reply_flat = [l for m in obj.get("modules", []) for l in m.get("lessons", []) if isinstance(l, dict)]
    existing_flat = [l for m in manifest.get("modules", []) for l in m.get("lessons", [])]
    for pos, l in enumerate(existing_flat):
        if l["id"] not in est and pos < len(reply_flat):
            est[l["id"]] = reply_flat[pos].get("estMinutes", 60)
    outline = {
        "title": manifest.get("title", ""), "subtitle": manifest.get("subtitle", ""),
        "level": obj.get("level", {}),
        "modules": [{"id": m.get("id"), "title": m.get("title"),
                     "lessons": [{"id": l.get("id"), "title": l.get("title"),
                                  "estMinutes": est.get(l.get("id"), 60)} for l in m.get("lessons", [])]}
                    for m in manifest.get("modules", [])],
    }
    sources = generation._resolve_sources(obj.get("groundingSources"), captured)
    return outline, sources


def enrich_course(existing_manifest, *, generate_sourced, verify):
    outline, sources = _grounded_outline_for_existing(existing_manifest, generate_sourced=generate_sourced)
    enriched = _merge_objectives(outline, _objectives_and_graph(outline, verify=verify))
    swept = _accuracy_sweep(enriched, sources, generate_sourced=generate_sourced)
    compiled = _assemble_contract(_brief_from_manifest(existing_manifest), outline, swept, sources)
    compiled["id"] = existing_manifest["id"]
    return compiled


def _revise_outline_prompt(existing_manifest, messages):
    skeleton = {"id": existing_manifest.get("id"), "title": existing_manifest.get("title", ""),
                "subtitle": existing_manifest.get("subtitle", ""),
                "level": existing_manifest.get("level", {}),
                "modules": [{"id": m.get("id"), "title": m.get("title"),
                             "lessons": [{"id": l.get("id"), "title": l.get("title")}
                                         for l in m.get("lessons", [])]}
                            for m in existing_manifest.get("modules", [])]}
    convo = "\n".join(f"{msg.get('role', 'user')}: {msg.get('content', '')}"
                      for msg in messages if isinstance(msg, dict))
    return (
        "You are revising an EXISTING course based on a discussion with the learner. Using web "
        "search where the change needs new material, produce the revised syllabus. Current course:\n"
        f"{json.dumps(skeleton, ensure_ascii=False)}\n\n"
        f"Discussion:\n{convo}\n\n"
        "For every lesson that CONTINUES an existing one (kept as-is, renamed, or moved), set "
        "\"keepId\" to that existing lesson id EXACTLY. OMIT keepId for brand-new lessons. Never "
        "invent ids. Keep the course coherent and correctly ordered. changeSummary lists, in short "
        "human-readable phrases, what changed versus the current course. Reply with ONLY a JSON "
        "object, no prose, no fence:\n"
        '{"title": "...", "subtitle": "...", "level": {"code": "...", "label": "..."}, '
        '"groundingSources": [{"title": "...", "url": "..."}], "changeSummary": ["..."], '
        '"modules": [{"title": "...", "lessons": [{"title": "...", "keepId": "c-l1", "estMinutes": 90}]}]}'
    )


def revise_course(existing_manifest, messages, *, generate_sourced, verify):
    obj, captured = generate_sourced(_revise_outline_prompt(existing_manifest, messages),
                                     valid_revise_outline)
    outline, retained = _resolve_revised_ids(existing_manifest, obj)
    sources = generation._resolve_sources(obj.get("groundingSources"), captured)
    enriched = _merge_objectives(outline, _objectives_and_graph(outline, verify=verify))
    # Overlay: retained lessons keep their previously approved objectives; only prereqs (which
    # depend on the new order) come from the fresh graph. New lessons keep generated objectives.
    existing_obj = {l.get("id"): l.get("objectives")
                    for m in existing_manifest.get("modules", []) for l in m.get("lessons", [])}
    for m in enriched.get("modules", []):
        for l in m.get("lessons", []):
            if l.get("id") in retained and existing_obj.get(l["id"]):
                l["objectives"] = existing_obj[l["id"]]
    compiled = _assemble_contract(_brief_from_manifest(existing_manifest), outline, enriched, sources)
    compiled["id"] = existing_manifest["id"]
    compiled["changeSummary"] = obj.get("changeSummary", [])
    return compiled


def valid_revise_outline(obj):
    if not isinstance(obj, dict):
        return False
    if not isinstance(obj.get("changeSummary", []), list):
        return False
    modules = obj.get("modules")
    if not (isinstance(modules, list) and modules):
        return False
    for m in modules:
        if not (isinstance(m, dict) and isinstance(m.get("title"), str) and m["title"].strip()):
            return False
        lessons = m.get("lessons")
        if not (isinstance(lessons, list) and lessons):
            return False
        for l in lessons:
            if not (isinstance(l, dict) and isinstance(l.get("title"), str) and l["title"].strip()):
                return False
            keep = l.get("keepId")
            if keep is not None and not isinstance(keep, str):
                return False
    return True


def _max_lesson_num(existing_manifest):
    nums = []
    for m in existing_manifest.get("modules", []):
        for l in m.get("lessons", []):
            mo = re.search(r"-l(\d+)$", l.get("id", ""))
            if mo:
                nums.append(int(mo.group(1)))
    return max(nums) if nums else 0


def _resolve_revised_ids(existing_manifest, revised_outline):
    course_id = existing_manifest["id"]
    existing_ids = {l.get("id") for m in existing_manifest.get("modules", [])
                    for l in m.get("lessons", [])}
    counter = _max_lesson_num(existing_manifest)
    used, retained, modules = set(), [], []
    for mi, m in enumerate(revised_outline.get("modules", []), start=1):
        lessons = []
        for l in m.get("lessons", []):
            keep = l.get("keepId")
            if isinstance(keep, str) and keep in existing_ids and keep not in used:
                lid, is_keep = keep, True
                used.add(keep)
                retained.append(keep)
            else:
                counter += 1
                lid, is_keep = f"{course_id}-l{counter}", False
            lessons.append({"id": lid, "title": l.get("title"),
                            "estMinutes": l.get("estMinutes", 60), "_keep": is_keep})
        modules.append({"id": f"m{mi}", "title": m.get("title"), "lessons": lessons})
    outline = {"title": revised_outline.get("title", existing_manifest.get("title", "")),
               "subtitle": revised_outline.get("subtitle", existing_manifest.get("subtitle", "")),
               "level": revised_outline.get("level", existing_manifest.get("level", {})),
               "modules": modules}
    return outline, retained
