import Image from "next/image";
import Link from "next/link";
import { ArrowRight, FileCheck2, Mail, MessageSquareQuote, Scale, ShieldCheck, Target } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Col, Logo, SiteHeader } from "@/components/site-header";

const FEATURES = [
  {
    icon: Target,
    title: "Your standards, not a generic model",
    text: "Thread learns from the firm's own work: its precedents and what partners actually corrected. The bar a junior is measured against is yours.",
  },
  {
    icon: FileCheck2,
    title: "Feedback that explains the why",
    text: "Every gap is tied to a precedent, a partner's review or a deal email. Juniors understand the reasoning behind the correction, not just the red mark.",
  },
  {
    icon: MessageSquareQuote,
    title: "Calibrated to the stakes",
    text: "A major deal is reviewed at maximum strictness, routine work at standard. Juniors learn where the bar moves, and why it moves.",
  },
];

const STEPS = [
  { n: "01", title: "The junior shares a first draft", text: "Any document the firm produces. Today: corporate acts and meeting minutes; tomorrow, the rest of the practice." },
  { n: "02", title: "Thread finds how the firm does it", text: "The closest precedents in your corpus, and what the partner corrected on them." },
  { n: "03", title: "The junior gets the corrected file, and the why", text: "Every change sourced. Score before and after. Something to learn from, not just something to fix." },
];

const INTEGRATIONS = ["iManage", "Allegro", "Gmail", "Outlook", "Meeting transcripts", "Mistral"];

export default function Landing() {
  return (
    <div className="min-h-svh bg-background text-foreground">
      <SiteHeader />

      <main>
        {/* Hero noir */}
        <section className="dots-dark bg-ink text-white">
          <div className="relative mx-auto w-full max-w-[1100px] border-x border-white/10 px-6 pb-28 pt-24 md:pt-32">
            <Image src="/thread-mark.svg" alt="" width={498} height={477} priority className="pointer-events-none absolute right-10 top-24 hidden w-[260px] lg:block" />
            <p className="eyebrow text-white/60">For law firms onboarding the next generation</p>
            <h1 className="mt-6 max-w-[700px] text-[42px] font-semibold leading-[1.1] md:text-[56px]">
              Onboard your junior with <span className="underline decoration-brand decoration-[5px] underline-offset-[10px]">what matters for you</span>.
            </h1>
            <p className="mt-6 text-[17px] italic text-white/60">Let&apos;s make your workforce ready for the AI-native reality.</p>
            <p className="mt-8 max-w-[600px] text-[17px] leading-[1.7] text-white/70">
              Thread turns your firm&apos;s own work, precedents, partner reviews and deal emails, into feedback a junior can learn from:
              what matters for you, why, and how to write it. Juniors ramp faster; partners review less.
            </p>
            <div className="mt-10 flex flex-wrap items-center gap-3">
              <Button className="h-11 rounded-lg bg-brand px-5 text-[15px] text-brand-foreground hover:bg-brand/85" nativeButton={false} render={<Link href="/app" />}>
                Open the demo workspace <ArrowRight className="size-4" />
              </Button>
              <Button variant="outline" className="h-11 rounded-lg border-white/25 bg-transparent px-5 text-[15px] font-normal text-white shadow-none hover:bg-white/10 hover:text-white" nativeButton={false} render={<a href="#how" />}>
                See how it works
              </Button>
            </div>
            <p className="mt-8 font-mono text-[12px] text-white/50">Demo: a junior's first draft scored 2/100 → 75/100 after Thread's sourced corrections</p>
          </div>
        </section>

        {/* Capture de l'app, à cheval sur le hero */}
        <section id="product" className="border-b">
          <Col className="px-6 pb-14">
            <div className="-mt-12 overflow-hidden rounded-md border bg-muted p-2">
              <Image
                src="/workspace-thread.png"
                alt="thread workspace: a junior's draft reviewed against the firm's precedents, with a score before and after, the closest precedents and a corrected file."
                width={1600} height={1000} priority className="rounded-sm border"
              />
            </div>
            <p className="mt-4 font-mono text-[12px] text-muted-foreground">
              Real output on the firm's own corpus: the junior's draft, the three closest precedents, and a corrected file where every change cites its source.</p>
          </Col>
        </section>

        {/* Trois bénéfices */}
        <section className="border-b">
          <Col className="px-6 py-20">
            <p className="eyebrow">Why it works</p>
            <div className="mt-8 grid gap-px overflow-hidden rounded-md border bg-border md:grid-cols-3">
              {FEATURES.map(({ icon: Icon, title, text }) => (
                <div key={title} className="bg-background p-7">
                  <span className="flex size-9 items-center justify-center rounded-sm bg-muted"><Icon className="size-4" /></span>
                  <h2 className="mt-5 text-[18px] font-semibold">{title}</h2>
                  <p className="mt-2 text-[15px] leading-relaxed text-muted-foreground">{text}</p>
                </div>
              ))}
            </div>
          </Col>
        </section>

        {/* How it works */}
        <section id="how" className="border-b bg-muted">
          <Col className="px-6 py-20">
            <p className="eyebrow">How it works</p>
            <h2 className="mt-4 text-[36px] font-semibold leading-[1.1]">From first draft to firm-grade, with the reasoning attached.</h2>
            <div className="mt-10 grid gap-5 md:grid-cols-3">
              {STEPS.map((s) => (
                <div key={s.n} className="rounded-md border bg-background p-6">
                  <span className="font-mono text-[12px] text-muted-foreground">{s.n}</span>
                  <h3 className="mt-3 text-[17px] font-semibold">{s.title}</h3>
                  <p className="mt-2 text-[15px] leading-relaxed text-muted-foreground">{s.text}</p>
                </div>
              ))}
            </div>
            <blockquote className="mt-12 max-w-[800px] border-l-2 border-brand pl-5 text-[20px] leading-relaxed">
              &ldquo;Sans suppression explicite du DPS, les associés existants (Antoine Vasseur, Camille Ferrand) pourraient souscrire en priorité, ce qui rendrait impossible l'entrée de Lumen Capital. Léa a mentionné dans son mail du 15 mars (v2) avoir 'isolé la résolution de suppression du DPS', mais elle n'apparaît pas dans le PV final.&rdquo;
              <footer className="mt-3 font-mono text-[12px] text-muted-foreground">Generated by Thread on a junior's first draft, from the partner's own reviews. Not a red mark in the margin.</footer>
            </blockquote>
          </Col>
        </section>

        {/* Intégrations + sécurité */}
        <section id="security" className="border-b">
          <Col className="grid gap-12 px-6 py-20 md:grid-cols-2">
            <div>
              <p className="eyebrow">Plugs into the firm&apos;s tools</p>
              <div className="mt-5 flex flex-wrap gap-2">
                {INTEGRATIONS.map((name) => (
                  <span key={name} className="rounded-md border px-3 py-1.5 font-mono text-[13px]">{name}</span>
                ))}
              </div>
            </div>
            <div>
              <p className="eyebrow">Built for confidential matters</p>
              <ul className="mt-5 grid gap-3 text-[15px] leading-relaxed text-muted-foreground">
                <li className="flex gap-3"><Scale className="mt-1 size-4 shrink-0 text-foreground" /> One workspace per matter; emails and calls never cross matters.</li>
                <li className="flex gap-3"><Mail className="mt-1 size-4 shrink-0 text-foreground" /> Every recommendation cites its source: file, page, email, or call timestamp.</li>
                <li className="flex gap-3"><ShieldCheck className="mt-1 size-4 shrink-0 text-foreground" /> Models by Mistral, a European provider; your document base stays yours.</li>
                <li className="flex gap-3"><Target className="mt-1 size-4 shrink-0 text-foreground" /> The partner stays the judge: Thread flags, explains and proposes; it never decides.</li>
              </ul>
            </div>
          </Col>
        </section>

        {/* CTA final noir */}
        <section className="dots-dark bg-ink text-white">
          <div className="mx-auto flex w-full max-w-[1100px] flex-wrap items-center justify-between gap-6 border-x border-white/10 px-6 py-16">
            <div>
              <p className="eyebrow text-white/60">Try it on the demo matter</p>
              <h2 className="mt-3 text-[32px] font-semibold leading-[1.1]">Onboard your junior with what matters for you.</h2>
              <p className="mt-2 text-[15px] italic text-white/60">Let&apos;s make your workforce ready for the AI-native reality.</p>
            </div>
            <Button className="h-11 rounded-lg bg-brand px-5 text-[15px] text-brand-foreground hover:bg-brand/85" nativeButton={false} render={<Link href="/app" />}>
              Open the workspace <ArrowRight className="size-4" />
            </Button>
          </div>
        </section>
      </main>

      <footer className="border-t">
        <Col className="flex flex-wrap items-center justify-between gap-4 px-6 py-8 font-mono text-[12px] text-muted-foreground">
          <Logo />
          <p>Hackathon prototype, October 2026. Not legal advice.</p>
        </Col>
      </footer>
    </div>
  );
}
