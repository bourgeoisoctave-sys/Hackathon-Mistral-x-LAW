import { spawn } from "node:child_process";
import path from "node:path";
import { NextResponse } from "next/server";

const ROOT = process.env.REVIEW_ROOT ?? path.resolve(process.cwd(), "..");
const PYTHON = process.env.REVIEW_PYTHON ?? path.join(ROOT, ".venv", "bin", "python");
const TIMEOUT_MS = 60_000;

/** POST {q} → {question, docs: [{id, name, score, where, excerpt, threads: [{label, href}]}]} (scripts/search.py) */
export async function POST(req: Request) {
  const { q } = (await req.json().catch(() => ({}))) as { q?: string };
  const question = String(q ?? "").trim().slice(0, 500);
  if (!question) return NextResponse.json({ error: "Question vide." }, { status: 400 });

  return new Promise<Response>((resolve) => {
    const child = spawn(PYTHON, [path.join(ROOT, "scripts", "search.py"), question], { cwd: ROOT, env: process.env });
    let stdout = "", stderr = "";
    const timer = setTimeout(() => child.kill(), TIMEOUT_MS);
    child.stdout.on("data", (d) => (stdout += d));
    child.stderr.on("data", (d) => (stderr += d));
    child.on("error", (e) => { clearTimeout(timer); resolve(NextResponse.json({ error: e.message }, { status: 500 })); });
    child.on("close", (code) => {
      clearTimeout(timer);
      if (code !== 0) {
        resolve(NextResponse.json({ error: "La recherche a échoué.", detail: stderr.split("\n").filter(Boolean).slice(-4).join("\n") }, { status: 500 }));
        return;
      }
      try { resolve(NextResponse.json(JSON.parse(stdout))); } catch { resolve(NextResponse.json({ error: "Réponse illisible." }, { status: 500 })); }
    });
  });
}
