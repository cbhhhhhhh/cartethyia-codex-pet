"""Generate one reply for the configured route; apply the same speech rules on every route."""
import json
import re
from pathlib import Path
from chat import generate
from dialogue import HERE, Rules, gallery, gallery_pick, action_request
from providers import route, api_chat, codex_chat


def actions():
    resource = HERE / "repertoire.json"
    if not resource.exists():
        resource = HERE.parent / "art/repertoire.json"
    return [x["title"] for x in json.loads(resource.read_text())]


def answer(base, folder, cfg, history, user, whisper, mode, image, forced, last_action,
           last_picture, cancel, publish, retrieved_weather="", last_kind="", recent_picture=None, audit=None):
    source, model = route(cfg, whisper)
    rules = Rules(cfg)
    available = gallery(folder, cfg.get("pack", "cartethyia"))
    replay_picture = not whisper and last_picture in available and (
        bool(re.search(r"(刚才|上次|之前).{0,5}(那张|配图|图片|表情图)|再看.{0,4}(那张|配图)|同一张", user)) or
        last_kind == "picture" and bool(re.search(r"刚才那个再|再来一次|再来一遍", user)))
    if replay_picture:
        forced = last_picture
    if forced and forced not in available:
        raise ValueError("这张配图已移除")
    if not whisper and not replay_picture and cfg.get("pack", "cartethyia") == "cartethyia":
        requested = action_request(user, actions(), last_action)
    else:
        requested = ""
    persona = (cfg.get("persona") or "") + "\n" + rules.instruction()
    memory = []
    if not whisper:
        for item in history[-max(0, int(cfg.get("rounds", 10))):] if cfg.get("rounds", 10) else []:
            if not all(rules.allows(item[k]) for k in ("user", "assistant")):
                continue
            label = available.get(item.get("picture"), {}).get("title", "")
            markers = " ".join(x for x in (item.get("clip"), label) if x and rules.allows(x))
            memory.append(dict(user=item["user"], assistant=item["assistant"] + ("（" + markers + "）" if markers else "")))
    prompt = "结合人设说一句三十字以内的闲聊。" if whisper else user
    if not whisper and rules.strict and not rules.allows(user):
        prompt = "用户问到了人设要求避开的话题。不要复述原话，请自然地回应并换一个话题。"
    if mode == "dream":
        prompt = "结合人设，说一句短短的梦话。"
    if forced:
        cue = available[forced]["description"]
        if rules.allows(cue):
            prompt += "\n配图的表情或动作：" + cue
    if requested and rules.allows(requested):
        prompt += "\n你正在表演：" + requested
    if cfg.get("localTime"):
        import time
        prompt += "\n本地时间 " + time.strftime("%H:%M")
    if retrieved_weather and not rules.weather and not rules.places:
        prompt += "\n" + retrieved_weather
    if source == "local" and image and not cfg.get("projector"):
        model = "Qwen3VL-2B-Instruct-Q4_K_M.gguf"
    projector = cfg.get("projector") or "mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf"
    def request(instruction):
        callback = (lambda _: None) if rules.strict or whisper else publish
        if source == "local":
            return generate(base / "runtime", model, persona, memory, instruction, cancel, callback,
                            image=image, projector=projector)
        messages = [{"role": "system", "content": persona +
                     '\n用简短中文交流。只返回 JSON，字段为 text、emotion（calm/happy/curious/sad/focused）、action（idle/waving/jumping/waiting/review/running/failed）。'}]
        for pair in memory:
            messages.extend([dict(role="user", content=pair["user"][:1200]),
                             dict(role="assistant", content=pair["assistant"][:1200])])
        messages.append(dict(role="user", content=instruction))
        if source == "api":
            return api_chat(cfg, model, messages, cancel, callback, image)
        return codex_chat(base, model, messages, cancel, callback, image)
    def infer(instruction):
        if audit:
            audit("start", source, None)
        result = request(instruction)
        if audit and result:
            audit("result", source, result.get("usageTokens"))
        return result
    try:
        result = infer(prompt)
    except (RuntimeError, ValueError, OSError):
        fallback = cfg.get("model")
        if not (whisper and source == "local" and fallback and model != fallback and not cancel.is_set()):
            raise
        model = fallback
        result = infer(prompt)
    if not result or cancel.is_set():
        return None
    calls, reported = 1, [result.get("usageTokens")]
    if not rules.allows(result["text"]):
        result = infer("请换一句符合人设的简短回应。不要重复违规话题。" + rules.instruction())
        if not result or cancel.is_set():
            return None
        calls += 1
        reported.append(result.get("usageTokens"))
        if not rules.allows(result["text"]):
            result.update(text=rules.safe_line(), action="idle", emotion="calm")
    previous = last_picture
    recent = recent_picture if recent_picture is not None else (history[-1].get("picture", "") if history else "")
    picture = gallery_pick(available, user, result["emotion"], previous, forced,
                           cfg.get("replyArt") is True, whisper, rules, recent)
    result.update(route=source, calls=calls, reported=reported, clip=requested,
                  picture=picture["id"] if picture else "", art=[picture["file"]] if picture else [])
    return result
