import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";

const ROOT = process.env.REVIEW_ROOT ?? path.resolve(process.cwd(), "..");

/** GET /api/download?id=<id> → le .docx corrigé écrit par scripts/review.py dans reviews/<id>.docx */
export async function GET(req: Request) {
  const id = new URL(req.url).searchParams.get("id") ?? "";
  if (!/^[a-z0-9-]{4,40}$/i.test(id)) return NextResponse.json({ error: "id invalide" }, { status: 400 });
  const file = path.join(ROOT, "reviews", `${id}.docx`);
  try {
    await stat(file);
  } catch {
    return NextResponse.json({ error: "fichier introuvable" }, { status: 404 });
  }
  const buf = await readFile(file);
  return new Response(buf, {
    headers: {
      "Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      "Content-Disposition": `attachment; filename="PV-corrige-${id}.docx"`,
    },
  });
}
