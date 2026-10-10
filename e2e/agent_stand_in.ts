// Stands in for the agent's AgentCore app in the end-to-end tests: it answers
// /ping, answers the health check, and takes every other payload the backend
// posts to /invocations, starting nothing and listing them at /api/started.
import { createServer } from "node:http";
import { json } from "node:stream/consumers";
import type { Payload } from "./api";
import { reply } from "./stand_in.ts";

const started: Payload[] = [];

createServer((request, response) => {
  const url = request.url ?? "";
  if (request.method === "POST" && url === "/invocations") {
    json(request).then(
      (payload) => {
        const taken = payload as Payload;
        if (taken.operation === "health") {
          reply(response, 200, { healthy: true });
          return;
        }
        started.push(taken);
        reply(response, 200, { accepted: true });
      },
      () => {
        reply(response, 400, { error: "Invalid JSON" });
      },
    );
  } else if (url === "/ping") {
    reply(response, 200, { status: "Healthy" });
  } else if (url === "/api/started") {
    reply(response, 200, started);
  } else {
    reply(response, 404, { error: "Not found" });
  }
}).listen(Number(process.env.PORT), "127.0.0.1");
