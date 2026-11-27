// Test only our locally served stage in an empty, temporary Chromium profile.
import { spawn } from "node:child_process";
import { mkdtemp, readFile, rm } from "node:fs/promises";
import path from "node:path";
import { tmpdir } from "node:os";
const root = await mkdtemp(path.join(tmpdir(), "pet-web-"));
const run = spawn(
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  [
    "--headless",
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-background-networking",
    "--disable-sync",
    "--disable-component-update",
    "--disable-default-apps",
    "--disable-extensions",
    "--remote-debugging-port=0",
    "--remote-debugging-address=127.0.0.1",
    "--user-data-dir=" + root,
    "about:blank",
  ],
  { stdio: "ignore" },
);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
try {
  const secret = JSON.parse(await readFile(process.argv[2], "utf8"));
  let port;
  for (let i = 0; i < 80 && !port; i++) {
    try {
      port = (
        await readFile(path.join(root, "DevToolsActivePort"), "utf8")
      ).split("\n")[0];
    } catch {
      await sleep(100);
    }
  }
  const tabs = await (await fetch("http://127.0.0.1:" + port + "/json")).json();
  const ws = new WebSocket(
    tabs.find((t) => t.type === "page").webSocketDebuggerUrl,
  );
  await new Promise((r, j) => {
    ws.onopen = r;
    ws.onerror = j;
  });
  let seq = 0;
  const calls = new Map();
  ws.onmessage = (e) => {
    const a = JSON.parse(e.data);
    if (a.id) {
      calls.get(a.id)?.(a);
      calls.delete(a.id);
    }
  };
  const rpc = (method, params = {}) =>
    new Promise((r, j) => {
      const id = ++seq;
      calls.set(id, (a) => (a.error ? j(Error(a.error.message)) : r(a.result)));
      ws.send(JSON.stringify({ id, method, params }));
    });
  const evaluate = async (expression) => {
    const a = await rpc("Runtime.evaluate", {
      expression,
      returnByValue: true,
      awaitPromise: true,
    });
    if (a.exceptionDetails)
      throw Error(a.exceptionDetails.exception?.description);
    return a.result.value;
  };
  const until = async (expr) => {
    for (let i = 0; i < 70; i++) {
      if (await evaluate(expr)) return true;
      await sleep(100);
    }
    throw Error(
      "页面未到达预期状态 " +
        expr +
        " " +
        (await evaluate(
          "document.querySelector('#card')?.textContent?.slice(0,120)+' focus='+document.activeElement?.tagName",
        )),
    );
  };
  await rpc("Page.navigate", { url: secret.origin + "/#" + secret.token });
  await until(
    "document.querySelector('#pet')?.style.backgroundImage?.startsWith('url(')",
  );
  const bounds = await evaluate(
    "(()=>{let b=document.querySelector('#pet').getBoundingClientRect();return {x:b.x+b.width/2,y:b.y+b.height/2}})()",
  );
  for (let type of ["mouseMoved", "mousePressed", "mouseReleased"])
    await rpc("Input.dispatchMouseEvent", {
      ...bounds,
      type,
      button: "right",
      buttons: type === "mousePressed" ? 2 : 0,
      clickCount: 1,
    });
  await until("!document.querySelector('#menu').hidden");
  await evaluate("document.querySelector('[data-op=compose]').click()");
  await until("document.activeElement?.placeholder==='和卡提聊聊…'");
  await rpc("Input.insertText", { text: "你好，卡提。" });
  for (let type of ["keyDown", "keyUp"])
    await rpc("Input.dispatchKeyEvent", {
      type,
      key: "Enter",
      code: "Enter",
      text: type === "keyDown" ? "\r" : undefined,
      windowsVirtualKeyCode: 13,
      nativeVirtualKeyCode: 36,
    });
  await until(
    "document.querySelector('#card').textContent.includes('收到舞台消息')",
  );
  if (await evaluate("!!document.querySelector('#card .cameo')")) throw Error("普通聊天出现了配图");
  await evaluate("document.querySelector('[data-op=gallery]').click()");
  await until("document.querySelectorAll('#card button img').length===10");
  await evaluate("[...document.querySelectorAll('#card button')].find(b=>b.textContent.includes('弯眼微笑')).click()");
  await until("document.querySelector('#card .illustration img')?.naturalHeight > 100");
  await evaluate("document.querySelector('[data-op=todos]').click()");
  await until(
    "document.querySelector('#card').textContent.includes('测试待办')",
  );
  await evaluate("document.querySelector('[data-op=history]').click()");
  await until(
    "document.querySelector('#card').textContent.includes('舞台记录')",
  );
  await evaluate("document.querySelector('[data-op=library]').click()");
  await until("document.querySelector('#card select')?.options.length===109");
  await evaluate(
    "(()=>{document.querySelector('#card select').value='牵着线放风筝';document.querySelector('#card button').click()})()",
  );
  await until(
    "document.querySelector('#pet').style.backgroundSize.startsWith('2400%')",
  );
  await evaluate("document.querySelector('[data-op=home]').click()");
  const point = await evaluate("(()=>{const b=document.querySelector('#pet').getBoundingClientRect();return{x:b.x+b.width/2,y:b.y+b.height/2}})()");
  await rpc("Input.dispatchMouseEvent", {...point,type:"mousePressed",button:"left",buttons:1,clickCount:1});
  for (let i=1;i<=22;i++) {
    const theta = 2*Math.PI*i/22;
    await rpc("Input.dispatchMouseEvent",{type:"mouseMoved",button:"left",buttons:1,x:point.x+28*(Math.cos(theta)-1),y:point.y+28*Math.sin(theta)});
    await sleep(9);
  }
  await rpc("Input.dispatchMouseEvent", {...point,type:"mouseReleased",button:"left",buttons:0,clickCount:1});
  const rebound = await evaluate(`new Promise(resolve=>{
    const pet=document.querySelector("#pet");
    let last=pet.getBoundingClientRect().x, sign=0, edge=false;
    const start=performance.now();
    function observe(){const b=pet.getBoundingClientRect(),dx=b.x-last;last=b.x;
      if(!sign && Math.abs(dx)>2) sign=Math.sign(dx);
      if(Math.min(b.x,innerWidth-b.right)<25) edge=true;
      if(edge && sign*dx < -1) return resolve(true);
      if(performance.now()-start>3000) return resolve(false);
      requestAnimationFrame(observe);
    }requestAnimationFrame(observe);
  })`);
  if(!rebound) throw Error("浏览器舞台画圈后未观察到侧墙反弹");
  const checks = {
    sprite: true,
    ordinary_text_only: true,
    selected_gallery_illustration: true,
    circle_rebounds: rebound,
    full_character_library: true,
    right_click: true,
    focused_composer: true,
    enter_to_bubble: true,
    todo_list: true,
    history: true,
    fragment_removed: await evaluate("!location.hash"),
  };
  console.log(JSON.stringify(checks));
  ws.close();
} finally {
  run.kill("SIGTERM");
  await new Promise((r) => {
    if (run.exitCode !== null || run.signalCode) r();
    else run.once("exit", r);
  });
  await rm(root, { recursive: true, force: true, maxRetries: 8, retryDelay: 150 });
}
