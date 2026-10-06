import { spawn } from "node:child_process";
import { randomUUID } from "node:crypto";
import { mkdtemp, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import path from "node:path";

// Le moteur Python vit à la racine du repo (ui/ est un sous-dossier).
const ROOT = process.env.REVIEW_ROOT ?? path.resolve(process.cwd(), "..");
const PYTHON = process.env.REVIEW_PYTHON ?? path.join(ROOT, ".venv", "bin", "python");
const TIMEOUT_MS = 300_000;

export const maxDuration = 300;

/**
 * POST multipart {file, exigence, dossier} → flux SSE :
 *   event: step    data: {"step","label","pct"}        (une ligne par étape du moteur)
 *   event: result  data: {...revue complète...}
 *   event: error   data: {"error","detail"}
 */
export async function POST(req: Request) {
  const form = await req.formData();
  const file = form.get("file");
  if (!(file instanceof File)) return sse([["error", { error: "Aucun fichier." }]]);
  if (!/\.(pdf|docx)$/i.test(file.name)) return sse([["error", { error: "PDF ou .docx uniquement." }]]);
  const exigence = form.get("exigence") === "max" ? "max" : "standard";
  const dossier = String(form.get("dossier") ?? "helianthe").replace(/[^a-z0-9_-]/gi, "") || "helianthe";
  const id = randomUUID().slice(0, 8);

  const dir = await mkdtemp(path.join(tmpdir(), "julaw-"));
  const pv = path.join(dir, path.basename(file.name));
  await writeFile(pv, Buffer.from(await file.arrayBuffer()));

  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      const send = (event: string, data: unknown) =>
        controller.enqueue(encoder.encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`));
      const child = spawn(PYTHON, [path.join(ROOT, "scripts", "review.py"), pv, "--exigence", exigence, "--dossier", dossier, "--id", id], { cwd: ROOT, env: process.env });
      let stdout = "", stderr = "", buf = "";
      const timer = setTimeout(() => child.kill(), TIMEOUT_MS);
      child.stdout.on("data", (d) => (stdout += d));
      child.stderr.on("data", (d) => {
        const text = String(d);
        stderr += text;
        buf += text;
        const lines = buf.split("\n");
        buf = lines.pop() ?? "";
        for (const line of lines) {
          if (line.startsWith('{"step"')) {
            try { send("step", JSON.parse(line)); } catch { /* ligne tronquée : ignorée */ }
          }
        }
      });
      child.on("error", (e) => { clearTimeout(timer); send("error", { error: e.message }); controller.close(); });
      child.on("close", async (code) => {
        clearTimeout(timer);
        await rm(dir, { recursive: true, force: true });
        if (code !== 0) {
          send("error", { error: "Le moteur a échoué.", detail: stderr.split("\n").filter((l) => l && !l.startsWith('{"step"')).slice(-6).join("\n") });
        } else {
          try { send("result", JSON.parse(stdout)); } catch { send("error", { error: "Réponse du moteur illisible.", detail: stdout.slice(-300) }); }
        }
        controller.close();
      });
    },
  });
  return new Response(stream, { headers: { "Content-Type": "text/event-stream", "Cache-Control": "no-cache", Connection: "keep-alive" } });
}

function sse(events: [string, unknown][]) {
  const body = events.map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`).join("");
  return new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } });
}
