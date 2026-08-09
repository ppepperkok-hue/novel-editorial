const TOKEN = process.env.N8N_AUTH_TOKEN;
const CDP = "http://127.0.0.1:9333";
const WF_ID = process.env.WF_ID;

const targets = await (await fetch(CDP + "/json")).json();
const page = targets.find((t) => t.type === "page");
if (!page) throw new Error("no page target");

const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise((res, rej) => {
  ws.onopen = res;
  ws.onerror = rej;
});

let nextId = 1;
const pending = new Map();
ws.onmessage = (ev) => {
  const msg = JSON.parse(ev.data);
  if (msg.id && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    msg.error ? reject(new Error(JSON.stringify(msg.error))) : resolve(msg.result);
  }
};

function send(method, params = {}) {
  const id = nextId++;
  ws.send(JSON.stringify({ id, method, params }));
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
}

await send("Network.enable");
await send("Network.setCookie", {
  name: "n8n-auth",
  value: TOKEN,
  domain: "localhost",
  path: "/",
  httpOnly: true,
});
await send("Page.enable");
await send("Page.navigate", { url: `http://localhost:5678/workflow/${WF_ID}` });
await new Promise((r) => setTimeout(r, 12000));

const evalResult = await send("Runtime.evaluate", {
  expression: `JSON.stringify({href: location.href, title: document.title, bodyText: document.body.innerText.slice(0, 5000)})`,
  returnByValue: true,
});
console.log(evalResult.result.value);

try {
  await send("Browser.close");
} catch {}
ws.close();
process.exit(0);
