import { readFile, stat } from "node:fs/promises";
import path from "node:path";
import { NextResponse } from "next/server";

const ROOT = process.env.REVIEW_ROOT ?? path.resolve(process.cwd(), "..");

/**
 * GET /api/doc?acte=<acte_id>&piece=final|V1|V2|mail:<nom> → une pièce d'un acte.
 * final : docs/actes/<acte>.pdf · V1/V2 : historiques/<acte>/V*.txt · mail : historiques/<acte>/mails/<nom>.eml
 * acte et nom ne peuvent pas contenir de séparateur de chemin : on ne sort jamais de ces deux dossiers.
 */
export async function GET(req: Request) {
  const params = new URL(req.url).searchParams;
  const acte = params.get("acte") ?? "";
  const piece = params.get("piece") ?? "";
  if (!acte || acte.length > 200 || /[\\/]|\.\./.test(acte)) return NextResponse.json({ error: "acte invalide" }, { status: 400 });

  let file: string, type: string;
  if (piece === "final") {
    file = path.join(ROOT, "docs", "actes", `${acte}.pdf`);
    type = "application/pdf";
  } else if (piece === "V1" || piece === "V2") {
    file = path.join(ROOT, "historiques", acte, `${piece}.txt`);
    type = "text/plain; charset=utf-8";
  } else if (/^mail:[0-9a-z_]{1,40}$/.test(piece)) {
    file = path.join(ROOT, "historiques", acte, "mails", `${piece.slice(5)}.eml`);
    type = "text/plain; charset=utf-8";
  } else {
    return NextResponse.json({ error: "pièce invalide" }, { status: 400 });
  }

  try {
    await stat(file);
  } catch {
    return NextResponse.json({ error: "pièce introuvable" }, { status: 404 });
  }
  const buf = await readFile(file);
  const body = piece.startsWith("mail:") ? readableMail(buf) : buf;
  return new Response(body, { headers: { "Content-Type": type, "Content-Disposition": "inline" } });
}

/** .eml → texte lisible : en-têtes utiles puis corps décodé (quoted-printable écrit par generate_history.py). */
function readableMail(raw: Buffer): string {
  const text = raw.toString("utf-8");
  const sep = text.indexOf("\n\n");
  const head = text.slice(0, sep).replace(/\r?\n[ \t]+/g, " "), body = text.slice(sep + 2); // en-têtes repliés sur plusieurs lignes
  const header = (name: string) => head.match(new RegExp(`^${name}: (.*)$`, "mi"))?.[1] ?? "";
  const qp = /quoted-printable/i.test(header("Content-Transfer-Encoding"));
  const decoded = qp
    ? Buffer.from(body.replace(/=\r?\n/g, "").replace(/=([0-9A-F]{2})/gi, (_, h) => String.fromCharCode(parseInt(h, 16))), "latin1").toString("utf-8")
    : body;
  return ["From", "To", "Date", "Subject"].map((h) => `${h}: ${decodeHeader(header(h))}`).join("\n") + "\n\n" + decoded;
}

/** Sujets encodés « =?utf-8?q?…?= » (accents) → texte. */
function decodeHeader(v: string): string {
  return v.replace(/=\?utf-8\?([qb])\?([^?]*)\?=/gi, (_, enc, s) =>
    enc.toLowerCase() === "b"
      ? Buffer.from(s, "base64").toString("utf-8")
      : Buffer.from(s.replace(/_/g, " ").replace(/=([0-9A-F]{2})/gi, (_m: string, h: string) => String.fromCharCode(parseInt(h, 16))), "latin1").toString("utf-8"));
}
