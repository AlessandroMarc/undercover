// Stands in for the agent's service in the end-to-end tests: it accepts each claim
// the backend asks it to resume, listing them at /api/resumed, and each dispatch
// or evaluation it asks it to start, listing them at /api/started.
import { createServer, type ServerResponse } from "node:http";
import { json } from "node:stream/consumers";

const resumed: string[] = [];
const started: { path: string; body: unknown }[] = [];
const STARTS = new Set(["/api/dispatches", "/api/evaluations"]);

function reply(response: ServerResponse, status: number, body: unknown) {
  response.writeHead(status, { "Content-Type": "application/json" });
  response.end(JSON.stringify(body));
}

createServer((request, response) => {
  const url = request.url ?? "";
  const resume = /^\/api\/claims\/([^/]+)\/resume$/.exec(url);
  if (request.method === "POST" && resume) {
    resumed.push(decodeURIComponent(resume[1]));
    reply(response, 202, { status: "accepted" });
  } else if (request.method === "POST" && STARTS.has(url)) {
    json(request).then(
      (body) => {
        started.push({ path: url, body });
        reply(response, 202, { status: "accepted" });
      },
      () => {
        reply(response, 422, { detail: "The body isn't JSON" });
      },
    );
  } else if (url === "/api/resumed") {
    reply(response, 200, resumed);
  } else if (url === "/api/started") {
    reply(response, 200, started);
  } else if (url === "/api/health") {
    reply(response, 200, { status: "ok" });
  } else {
    reply(response, 404, { detail: "Not found" });
  }
}).listen(Number(process.env.PORT), "127.0.0.1");
