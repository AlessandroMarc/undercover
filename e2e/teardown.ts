import { rmSync } from "node:fs";
import { database } from "./database";

export default function teardown() {
  rmSync(database, { force: true });
}
