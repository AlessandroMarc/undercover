// Stands in for the agent's service in the end-to-end tests: it accepts each
// dispatch, evaluation or round the backend asks it to start, listing them at
// /api/started, each review of the improver's proposals it passes on, listing
// them at /api/reviews, and each claim it asks to resume, listing them at
// /api/resumes.
import { createServer, type IncomingMessage } from "node:http";
import { json } from "node:stream/consumers";
import type { Started } from "./api";
import { reply } from "./stand_in.ts";

const started: Started[] = [];
const reviews: Started[] = [];
const resumes: string[] = [];
const STARTS = new Set(["/api/dispatches", "/api/evaluations", "/api/rounds"]);
const REVIEW = /^\/api\/rounds\/[^/]+\/proposals\/[^/]+\/review$/;
const RESUME = /^\/api\/claims\/([^/]+)\/resume$/;

createServer((request, response) => {
  const url = request.url ?? "";
  const accept = (into: Started[]) => {
    keep(request, url, into).then(
      () => {
        reply(response, 202, { status: "accepted" });
      },
      () => {
        reply(response, 422, { detail: "The body isn't JSON" });
      },
    );
  };
  const resume = RESUME.exec(url);
  if (request.method === "POST" && STARTS.has(url)) {
    accept(started);
  } else if (request.method === "POST" && REVIEW.test(url)) {
    accept(reviews);
  } else if (request.method === "POST" && resume) {
    resumes.push(decodeURIComponent(resume[1]));
    reply(response, 202, { status: "accepted" });
  } else if (url === "/api/resumes") {
    reply(response, 200, resumes);
  } else if (url === "/api/started") {
    reply(response, 200, started);
  } else if (url === "/api/reviews") {
    reply(response, 200, reviews);
  } else if (url === "/api/health") {
    reply(response, 200, { status: "ok" });
  } else {
    reply(response, 404, { detail: "Not found" });
  }
}).listen(Number(process.env.PORT), "127.0.0.1");

async function keep(request: IncomingMessage, path: string, into: Started[]) {
  into.push({ path, body: await json(request) });
}
