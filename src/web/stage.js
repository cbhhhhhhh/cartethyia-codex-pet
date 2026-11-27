"use strict";
const $ = (s) => document.querySelector(s),
  pet = $("#pet"),
  anchor = $("#anchor"),
  card = $("#card"),
  menu = $("#menu"),
  stage = $("#stage");
const token = location.hash.slice(1) || sessionStorage.getItem("pet-stage");
if (location.hash) {
  sessionStorage.setItem("pet-stage", token);
  history.replaceState(null, "", "/");
}
const rows = [
    "idle",
    "running-right",
    "running-left",
    "waving",
    "jumping",
    "failed",
    "waiting",
    "running",
    "review",
  ],
  counts = [6, 8, 8, 4, 5, 8, 6, 6, 6];
let state = {},
  mode = "",
  lastBubble = "",
  bubbleTimer = 0,
  pack = "",
  atlas = "",
  row = 0,
  frame = 0,
  x = 0,
  y = 0,
  vx = 0,
  vy = 0,
  flight = 0,
  grab = null,
  tilt = 0,
  lastTap = 0,
  heightRows = 9,
  requesting = false;
const clamp = (a, b, c) => Math.max(b, Math.min(c, a));
async function api(path, data) {
  const r = await fetch("/v1/" + path, {
    method: data ? "POST" : "GET",
    headers: {
      Authorization: "Bearer " + token,
      "X-Pet-Stage": "visible",
      "Content-Type": "application/json",
    },
    body: data ? JSON.stringify(data) : undefined,
  });
  if (!r.ok) throw Error("连接已失效，请从桌宠右键菜单重新打开舞台");
  return r;
}
const cmd = (op, values = {}) =>
  api("control", { op, ...values }).catch((e) => show("notice", e.message));
function show(kind, txt) {
  mode = kind;
  card.hidden = !kind;
  card.replaceChildren();
  card.dataset.kind = kind;
  if (kind === "detail" || kind === "speech" && state.picture) {
    const mood = kind === "detail"
      ? ({working: "focused", review: "focused", thinking: "curious", error: "sad", success: "happy",
          "waiting-for-approval": "curious"}[state.state] || "calm")
      : state.mood || "calm";
    const face = document.createElement("div");
    face.className = "cameo";
    face.setAttribute("aria-hidden", "true");
    const figure = document.createElement("i");
    if (kind === "speech" && state.picture) {
      fetch("/v1/picture/" + encodeURIComponent(state.picture), {headers:{Authorization:"Bearer "+token}})
        .then(r => r.ok ? r.blob() : Promise.reject()).then(blob => {
          if (!figure.isConnected) return;
          const image = new Image(), url = URL.createObjectURL(blob);
          image.onload = image.onerror = () => URL.revokeObjectURL(url);
          image.src = url;
          image.style.cssText = "width:100%;height:100%;object-fit:contain";
          figure.append(image);
        }).catch(() => {});
      figure.className = "illustration";
    } else if (pack === "cartethyia" && ["calm","happy","curious","focused","sad"].includes(mood)) {
      figure.style.backgroundImage = "url(/portraits/" + mood + "-" + ((Number(state.variant)||0)%2) + ".png)";
      figure.className = "illustration";
    } else if (atlas) {
      const r = {calm: 0, happy: 3, curious: 6, focused: 8, sad: 5}[mood] ?? 0;
      const frame = (Number(state.variant) || 0) % counts[r];
      figure.style.backgroundImage = "url(" + atlas + ")";
      figure.style.backgroundSize = "800% " + heightRows * 100 + "%";
      figure.style.backgroundPosition = (frame / 7) * 100 + "% " + (r / (heightRows - 1)) * 100 + "%";
    }
    face.dataset.mood = mood;
    face.append(figure);
    const copy = document.createElement("div");
    copy.className = "card-copy";
    copy.textContent = txt || "";
    card.append(face, copy);
  } else if (txt) card.textContent = txt;
  position();
}
function position() {
  x = clamp(x, 0, stage.clientWidth - anchor.offsetWidth);
  y = clamp(y, 0, stage.clientHeight - anchor.offsetHeight);
  anchor.style.transform = "translate(" + x + "px," + y + "px)";
  card.style.bottom = y > card.offsetHeight + 5 ? "100%" : "auto";
  card.style.top = y > card.offsetHeight + 5 ? "auto" : "100%";
  const center = clamp(
    x + anchor.offsetWidth / 2,
    card.offsetWidth / 2,
    stage.clientWidth - card.offsetWidth / 2,
  );
  card.style.left = center - x + "px";
  card.dataset.above = y > card.offsetHeight + 5 ? "true" : "false";
  card.style.setProperty("--tip", clamp(x + anchor.offsetWidth/2 - center + card.offsetWidth/2, 17, card.offsetWidth - 17) + "px");
}
function home() {
  cancelAnimationFrame(flight);
  flight = 0;
  x = (stage.clientWidth - anchor.offsetWidth) / 2;
  y = (stage.clientHeight - anchor.offsetHeight) / 2;
  position();
}
function compose() {
  if (state.asleep) {
    cmd("wake");
    return;
  }
  show("compose");
  card.append($("#composer").content.cloneNode(true));
  const form = card.firstChild;
  form.onsubmit = async (e) => {
    e.preventDefault();
    const text = form.elements[0].value.trim(),
      file = form.querySelector("[type=file]").files[0];
    if (!text && !file) return;
    try {
      const values = { text: text || "请描述这张图。" };
      if (file) {
        if (file.size > 8 * 1024 * 1024) throw Error("图片上限为 8 MB");
        const r = await fetch("/v1/image", {
          method: "POST",
          headers: { Authorization: "Bearer " + token },
          body: file,
        });
        if (!r.ok) throw Error("请选择 PNG 或 JPEG");
        values.image = (await r.json()).image;
      }
      show("speech", "…");
      await cmd("chat", values);
    } catch (e) {
      show("notice", e.message);
    }
  };
  form.elements[0].focus();
  position();
}
function detail() {
  const t = state.since
    ? Math.max(0, Math.floor(Date.now() / 1000 - state.since)) + " 秒"
    : "—";
  show(
    "detail",
    "工具　" +
      (state.tool || "—") +
      "\n耗时　" +
      t +
      "\n计划　" +
      (state.progress || "暂无计划进度"),
  );
}
function button(label, run) {
  const b = document.createElement("button");
  b.type = "button";
  b.textContent = label;
  b.onclick = run;
  return b;
}
async function listCard(kind) {
  try {
    const data = await (
      await api(kind === "todos" ? "todos" : "history")
    ).json();
    show(kind);
    const head = document.createElement("strong");
    head.textContent = kind === "todos" ? "待办事项" : "聊天记录";
    card.append(
      head,
      button("收起", () => show("")),
    );
    const list = document.createElement("ul");
    list.className = "list";
    card.append(list);
    for (const item of data) {
      const li = document.createElement("li");
      list.append(li);
      const line = document.createElement("span");
      if (kind === "todos") {
        line.textContent =
          item.text +
          (item.due ? " · " + new Date(item.due * 1000).toLocaleString() : "");
        if (item.done) line.style.textDecoration = "line-through";
        li.append(
          button(item.done ? "↶" : "✓", async () => {
            await cmd("todo-toggle", { id: item.id });
            setTimeout(() => listCard(kind), 180);
          }),
          line,
        );
      } else {
        line.textContent = "你　" + item.user + "\n卡提　" + item.assistant;
        li.append(line);
      }
      const del = button("删除", async () => {
        if (del.textContent !== "确认") {
          del.textContent = "确认";
          return;
        }
        await cmd(
          kind === "todos" ? "todo-delete" : "history-delete",
          kind === "todos" ? { id: item.id } : { ids: [item.id] },
        );
        setTimeout(() => listCard(kind), 180);
      });
      li.append(del);
    }
    if (kind === "todos") {
      const f = document.createElement("form"),
        task = document.createElement("input"),
        date = document.createElement("input");
      task.placeholder = "添加待办";
      task.required = true;
      date.type = "datetime-local";
      const add = document.createElement("button");
      add.textContent = "添加";
      f.append(task, date, add);
      f.onsubmit = async (e) => {
        e.preventDefault();
        const v = { text: task.value };
        if (date.value) v.due = new Date(date.value).toISOString();
        await cmd("todo-add", v);
        setTimeout(() => listCard(kind), 180);
      };
      card.append(f);
    }
    position();
  } catch (e) {
    show("notice", e.message);
  }
}
let clips = {},
  clipName = "",
  clipURL = "",
  clipStarted = 0;
function galleryCard() {
  show("gallery", "");
  for (const p of state.gallery || []) {
    const button = document.createElement("button");
    button.textContent = p.title;
    button.title = p.description;
    if (/^(calm|curious|happy|sad|focused)-[01]$/.test(p.id)) {
      const img = document.createElement("img");
      img.src = "/portraits/" + p.id + ".png";
      img.width = 36;
      img.height = 36;
      img.style.objectFit = "contain";
      button.prepend(img);
    } else {
      fetch("/v1/picture/" + encodeURIComponent(p.id), {headers:{Authorization:"Bearer "+token}})
        .then(r => r.ok ? r.blob() : Promise.reject()).then(blob => {
          if (!button.isConnected) return;
          const img = new Image(36,36), url = URL.createObjectURL(blob);
          img.onload = img.onerror = () => URL.revokeObjectURL(url);
          img.style.objectFit = "contain"; img.src = url; button.prepend(img);
        }).catch(() => {});
    }
    button.onclick = () => { show(""); cmd("whisper",{picture:p.id}); };
    card.append(button);
  }
  position();
}
function usageCard(data = state.usage) {
  show("usage","");
  const select = document.createElement("select");
  for (const option of data?.options || []) select.add(new Option(option.label, option.key));
  if (data?.selected) select.value = data.selected;
  select.onchange = () => cmd("usage",{selected:select.value});
  if (select.length) card.append(select);
  const text = document.createElement("p");
  text.style.whiteSpace = "pre-line";
  text.textContent = data?.text || "正在读取本机回合记录…";
  const close = document.createElement("button");
  close.textContent = "收起";
  close.onclick = () => { cmd("usage-close"); show(""); };
  card.append(text,close);
  position();
}
function libraryCard() {
  show("library");
  const select = document.createElement("select"),
    groups = new Map();
  for (const [key, spec] of Object.entries(clips)) {
    const group = spec.group || "角色动作";
    if (!groups.has(group)) {
      const g = document.createElement("optgroup");
      g.label = group;
      groups.set(group, g);
      select.append(g);
    }
    groups.get(group).append(new Option(key, key));
  }
  select.setAttribute("aria-label", "选择角色动作");
  card.append(
    select,
    button("播放", () => {
      if (select.value) {
        cmd("play", { action: "clip:" + select.value });
        show("");
      }
    }),
    button("收起", () => show("")),
  );
  position();
}
async function selectArt(action) {
  const name = action?.startsWith("clip:") ? action.slice(5) : "";
  if (name === clipName) return;
  if (clipURL) {
    URL.revokeObjectURL(clipURL);
    clipURL = "";
  }
  clipName = "";
  if (name && clips[name]) {
    const response = await api("clip/" + encodeURIComponent(name));
    clipURL = URL.createObjectURL(await response.blob());
    clipName = name;
    clipStarted = performance.now();
    pet.style.backgroundImage = "url(" + clipURL + ")";
    pet.style.backgroundSize = clips[name].frames * 100 + "% 100%";
  } else if (atlas) {
    pet.style.backgroundImage = "url(" + atlas + ")";
    pet.style.backgroundSize = "800% " + heightRows * 100 + "%";
  }
}
function act(op) {
  if (op === "library") {
    menu.hidden = true;
    libraryCard();
    return;
  }
  menu.hidden = true;
  if (op === "gallery") galleryCard();
  else if (op === "usage") { usageCard(); cmd("usage"); }
  else if (op === "todos" || op === "history") listCard(op);
  else if (op === "home") home();
  else if (op === "detail") detail();
  else if (op === "compose") compose();
  else if (op === "play") cmd(op, { action: "向你挥手" });
  else cmd(op);
}
document.addEventListener("click", (e) => {
  const op = e.target.closest("[data-op]")?.dataset.op;
  if (op) act(op);
  else if (!menu.contains(e.target)) menu.hidden = true;
});
pet.oncontextmenu = (e) => {
  e.preventDefault();
  menu.hidden = false;
  menu.style.left = clamp(e.clientX, 0, innerWidth - menu.offsetWidth) + "px";
  menu.style.top = clamp(e.clientY, 0, innerHeight - menu.offsetHeight) + "px";
};
pet.onkeydown = (e) => {
  if (e.key === "Enter" || e.key.toLowerCase() === "t") compose();
  if (e.key.toLowerCase() === "s") cmd(state.asleep ? "wake" : "sleep");
  if (e.key.toLowerCase() === "d") cmd("todos");
};
pet.onpointerdown = (e) => {
  if (e.button !== 0) return;
  cancelAnimationFrame(flight);
  flight = 0;
  pet.setPointerCapture(e.pointerId);
  const now = performance.now();
  grab = {
    x,
    y,
    sx: e.clientX,
    sy: e.clientY,
    trail: [[now, e.clientX, e.clientY]],
    moved: false,
    sling: now - lastTap < 320,
  };
  lastTap = now;
};
pet.onpointermove = (e) => {
  if (!grab) return;
  const dx = e.clientX - grab.sx,
    dy = e.clientY - grab.sy;
  grab.moved ||= Math.hypot(dx, dy) > 4;
  if (!grab.moved) return;
  x = grab.x + dx;
  y = grab.y + dy;
  const t = performance.now();
  const last = grab.trail.at(-1);
  if (last[1] !== e.clientX || last[2] !== e.clientY) {
    if (t - last[0] > 230) grab.trail = [];
    grab.trail.push([t, e.clientX, e.clientY]);
    grab.trail = grab.trail.filter((p) => t - p[0] <= 750);
  }
  position();
};
function launch(a, b) {
  cancelAnimationFrame(flight);
  vx = a;
  vy = b;
  let last = performance.now();
  function step(t) {
    const dt = Math.min(0.035, (t - last) / 1000);
    last = t;
    const r = state.rebound ?? 0.78;
    vy += (state.gravity ?? 1400) * dt;
    vx += (effects.tilt ? tilt : 0) * dt;
    x += vx * dt;
    y += vy * dt;
    const w = stage.clientWidth - anchor.offsetWidth,
      h = stage.clientHeight - anchor.offsetHeight;
    if ((x <= 0 && vx < 0) || (x >= w && vx > 0)) vx *= -r;
    if (y <= 0 && vy < 0) vy *= -r;
    if (y >= h && vy > 0) {
      vy = vy < 40 ? 0 : -vy * r;
      vx *= Math.exp(-(state.friction ?? 2.5) * dt);
      if (effects.buzz && navigator.vibrate && Math.abs(vy) > 130)
        navigator.vibrate(12);
    }
    position();
    if (y >= h - 0.5 && Math.abs(vx) < 8 && vy === 0) {
      flight = 0;
      return;
    }
    flight = requestAnimationFrame(step);
  }
  flight = requestAnimationFrame(step);
}
pet.onpointerup = (e) => {
  const g = grab;
  grab = null;
  if (!g) return;
  if (!g.moved) {
    compose();
    return;
  }
  const last = g.trail.at(-1), now = performance.now(), power = state.throwForce ?? 1;
  if (g.sling && Math.hypot(g.sx-e.clientX, g.sy-e.clientY) > 16) {
    launch((g.sx-e.clientX)*13*power, (g.sy-e.clientY)*13*power);
    return;
  }
  if (!power || now-last[0] >= 180) return;
  if (last[1] !== e.clientX || last[2] !== e.clientY) g.trail.push([now,e.clientX,e.clientY]);
  const first = g.trail[0], end = g.trail.at(-1);
  const dist = (a,b) => Math.hypot(a[1]-b[1],a[2]-b[2]);
  const path = g.trail.slice(1).reduce((sum, p, i) => sum+dist(g.trail[i],p),0);
  const span = Math.max(...g.trail.map(p => dist(p,first)));
  const speed = 1000*path/Math.max(40,end[0]-first[0]);
  if (g.trail.length >= 4 && span >= 18 && path >= 60 && dist(first,end) < path*0.68 && speed >= 180) {
    launch((Math.random()<0.5 ? -1 : 1)*Math.min(3300,1650+speed*0.8)*power,
           -(540+Math.random()*400)*power);
    return;
  }
  const a = g.trail.find(p => end[0]-p[0] <= 170), dt = (end[0]-a[0])/1000;
  const distance = dist(end,a);
  if (dt >= 0.015 && distance >= 12 && distance/dt >= 270) {
    const gain = Math.min(3500,Math.max(750,distance/dt*1.55))*power/distance;
    launch((end[1]-a[1])*gain,(end[2]-a[2])*gain);
  }
};
pet.onpointercancel = () => {
  grab = null;
};
async function poll() {
  if (document.hidden || requesting) return;
  requesting = true;
  try {
    state = await (await api("state")).json();
    $("#status").textContent =
      {
        idle: "空闲",
        working: "执行中",
        thinking: "思考中",
        review: "整理中",
        success: "已完成",
        error: "出错",
        "waiting-for-approval": "等待审批",
      }[state.state] || "空闲";
    if (pack !== state.pack && state.pack) {
      const blob = await (await api("sprite")).blob(),
        url = URL.createObjectURL(blob),
        img = new Image();
      img.src = url;
      await img.decode();
      heightRows = img.height / 208;
      pet.style.backgroundSize = "800% " + heightRows * 100 + "%";
      pet.style.backgroundImage = "url(" + url + ")";
      if (atlas) URL.revokeObjectURL(atlas);
      atlas = url;
      pack = state.pack;
      clips = await (await api("clips")).json();
      clipName = "";
    }
    await selectArt(state.action);
    row = Math.max(0, rows.indexOf(state.action || "idle"));
    if (mode === "detail") detail();
    if (mode === "usage" && document.activeElement?.tagName !== "SELECT") usageCard();
    const version = state.bubbleId ?? state.bubble;
    if (version !== lastBubble) {
      lastBubble = version;
      clearTimeout(bubbleTimer);
      if (!["compose", "history", "todos", "library", "usage", "gallery", "detail"].includes(mode)) {
        show(state.bubble ? "speech" : "", state.bubble);
        if (state.bubble && state.duration > 0)
          bubbleTimer = setTimeout(() => {
            if (mode === "speech") show("");
          }, state.duration * 1000);
      }
    }
  } catch (e) {
    $("#status").textContent = e.message;
  } finally {
    requesting = false;
  }
}
setInterval(() => {
  if (document.hidden || !atlas) return;
  if (clipName && clips[clipName]) {
    const { frames, fps } = clips[clipName];
    const i =
      Math.floor(((performance.now() - clipStarted) * (fps || 8)) / 1000) %
      frames;
    pet.style.backgroundPosition =
      (frames > 1 ? (100 * i) / (frames - 1) : 0) + "% 0%";
    return;
  }
  frame = (frame + 1) % counts[row];
  pet.style.backgroundPosition =
    (frame / 7) * 100 + "% " + (row / (heightRows - 1)) * 100 + "%";
}, 170);
setInterval(poll, 750);
window.addEventListener("resize", position);
home();
poll();
const effects = { tilt: false, shake: false, buzz: false };
if (navigator.maxTouchPoints > 0) {
  const panel = $("#motion");
  panel.hidden = false;
  const sensor = $("#sensor");
  sensor.hidden = !("DeviceMotionEvent" in window);
  for (const key of Object.keys(effects)) {
    const box = $("#" + key);
    effects[key] = localStorage.getItem("pet-effect-" + key) === "1";
    box.checked = effects[key];
    box.onchange = () => {
      effects[key] = box.checked;
      localStorage.setItem("pet-effect-" + key, box.checked ? "1" : "0");
    };
  }
  sensor.onclick = async () => {
    try {
      if (
        typeof DeviceMotionEvent.requestPermission === "function" &&
        (await DeviceMotionEvent.requestPermission()) !== "granted"
      )
        return;
      let lastShake = 0;
      window.addEventListener("devicemotion", (e) => {
        const g = e.accelerationIncludingGravity || {},
          a = e.acceleration || {};
        tilt = clamp((g.x || 0) * 70, -700, 700);
        if (
          effects.shake &&
          !grab &&
          performance.now() - lastShake > 750 &&
          Math.hypot(a.x || 0, a.y || 0, a.z || 0) > 19
        ) {
          lastShake = performance.now();
          launch((a.x || 1) * 32, -Math.abs(a.y || 10) * 35);
        }
      });
      sensor.hidden = true;
    } catch {
      sensor.textContent = "传感器不可用";
    }
  };
}
