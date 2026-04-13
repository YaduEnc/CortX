import { useState, useEffect, useRef } from "react";
import { motion, useScroll, useTransform, useInView, AnimatePresence } from "framer-motion";
import { useSpring, animated, useTrail, config as springConfig } from "@react-spring/web";
import { Link, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { DeviceExploded } from "./DeviceExploded";
import { KnowledgeGraph } from "./KnowledgeGraph";


const globalCSS = `
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;900&display=swap');
  *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
  html { scroll-behavior: smooth; }
  body { background: #000; color: #fff; font-family: 'Inter', sans-serif; overflow-x: hidden; }
  a { text-decoration: none; }
  input:focus { outline: none; }
  
  @media (max-width: 768px) {
    .feature-card {
      grid-column: span 1 !important;
    }
  }
`;

const technologyLinks = [
  { label: "Architecture", path: "/architecture" },
  { label: "Security", path: "/security" },
  { label: "Open Source", path: "/open-source" },
  { label: "Whisper v3", path: "/whisper-v3" },
];

const companyLinks = [
  { label: "About", path: "/about" },
  { label: "Privacy Policy", path: "/privacy-policy" },
  { label: "Terms of Service", path: "/terms-of-service" },
  { label: "Contact", path: "/contact" },
];

type DocSection = {
  heading: string;
  body: string;
  bullets?: string[];
};

type DocPageContent = {
  eyebrow: string;
  title: string;
  subtitle: string;
  lead: string;
  sections: DocSection[];
};

const docPages: Record<string, DocPageContent> = {
  "/architecture": {
    eyebrow: "Technology",
    title: "Architecture",
    subtitle: "From spoken capture to structured memory, the system is designed as a deterministic pipeline rather than a black box.",
    lead: "SecondMind links hardware capture, mobile relay, backend processing, and memory retrieval into one operational stack. Every layer has one job: capture reliably, structure accurately, and return useful context fast.",
    sections: [
      {
        heading: "Capture layer",
        body: "The wearable records short audio windows through the onboard microphone stack and streams them through BLE to the mobile app. The device is optimized for low-friction capture rather than on-device inference.",
        bullets: [
          "Low-latency BLE relay to the companion app",
          "Authenticated device-to-app pairing",
          "Short capture windows designed for continuous use",
        ],
      },
      {
        heading: "Transport and ingestion",
        body: "The app relays capture packets to the CortX API over authenticated channels. The ingestion layer timestamps, normalizes, and stores raw audio references before downstream AI jobs begin.",
        bullets: [
          "Device identity attached to every upload",
          "Session-aware capture tracking",
          "Separation between transport, storage, and AI jobs",
        ],
      },
      {
        heading: "AI structuring pipeline",
        body: "Transcripts move through extraction workers that classify ideas, tasks, reminders, decisions, entities, and action intents. Structured outputs are persisted separately from the raw transcript so retrieval can operate on meaning, not just text search.",
        bullets: [
          "Transcript generation",
          "Structured memory extraction",
          "Action detection and drafting",
          "Daily summaries and derived views",
        ],
      },
      {
        heading: "Retrieval surface",
        body: "The app answers user queries by reading structured memory tables and relevant transcript evidence together. The result is a memory system that can answer, summarize, and trigger action instead of acting like a passive archive.",
      },
    ],
  },
  "/security": {
    eyebrow: "Technology",
    title: "Security",
    subtitle: "Security is treated as an infrastructure concern, not a marketing feature.",
    lead: "The system is being built around private capture, authenticated device flows, and backend-controlled privileged access. The practical goal is simple: no service keys in client code, explicit ownership boundaries, and traceable processing.",
    sections: [
      {
        heading: "Device and app boundaries",
        body: "Devices authenticate with backend-issued credentials. The companion app operates as an authenticated client but does not carry privileged backend secrets needed for administrative storage or system-level writes.",
        bullets: [
          "Pairing and device auth are explicit",
          "Privileged access is backend-only",
          "User-scoped data paths stay separated from device registration",
        ],
      },
      {
        heading: "Data handling",
        body: "Audio, transcripts, and derived memory objects are persisted as separate layers so access policies and retention can be controlled with more granularity. This also limits broad, unnecessary access to raw data during retrieval.",
        bullets: [
          "Raw capture references kept distinct from structured memory",
          "User-scoped memory tables",
          "Pipeline job visibility and retry status tracked server-side",
        ],
      },
      {
        heading: "Operational posture",
        body: "The backend is designed around private buckets, server-mediated privileged operations, and observability on pipeline states such as receiving, transcribing, structuring, and failure recovery.",
      },
    ],
  },
  "/open-source": {
    eyebrow: "Technology",
    title: "Open Source",
    subtitle: "SecondMind is built on an open systems stack even where the product experience itself remains tightly integrated.",
    lead: "The current platform uses a mix of open-source foundations and product-specific orchestration. The philosophy is to avoid hidden dependencies where a proven open stack can do the job.",
    sections: [
      {
        heading: "Core building blocks",
        body: "The product stack already relies on open components across firmware, mobile, frontend, backend, and AI infrastructure.",
        bullets: [
          "ESP32 firmware for device capture",
          "Flutter for cross-platform mobile",
          "React and Three.js for the web experience",
          "FastAPI workers and service orchestration",
          "Whisper-based speech transcription",
        ],
      },
      {
        heading: "Why this matters",
        body: "An open stack improves inspection, iteration speed, and replaceability. It reduces vendor lock-in at the infrastructure layer while still allowing the product layer to evolve quickly.",
      },
      {
        heading: "Roadmap",
        body: "As the system matures, the open-source boundary should become clearer: commodity infrastructure stays open and portable, while tightly coupled orchestration and product intelligence can remain product-owned where that creates leverage.",
      },
    ],
  },
  "/whisper-v3": {
    eyebrow: "Technology",
    title: "Whisper v3",
    subtitle: "Speech-to-text is not the product by itself, but it is the quality gate for everything built on top of memory.",
    lead: "SecondMind uses Whisper-class transcription as the first semantic step after capture. The transcript layer must be stable enough to support tasks, ideas, decisions, entities, and later retrieval without collapsing under noisy speech.",
    sections: [
      {
        heading: "Role in the pipeline",
        body: "Whisper v3 class models convert captured speech into timestamped text before extraction jobs run. This layer is designed to preserve natural speech rather than forcing users into rigid command syntax.",
      },
      {
        heading: "Why it matters",
        body: "If transcript quality fails, every downstream memory object degrades with it. That is why the speech layer is treated as infrastructure: accuracy, multilingual tolerance, and robustness matter more than flashy output.",
        bullets: [
          "Natural language capture instead of command mode",
          "Strong baseline for multilingual and accented speech",
          "Better downstream extraction quality",
        ],
      },
      {
        heading: "What comes after speech",
        body: "The transcript is only the input. SecondMind then structures it into memory objects, action drafts, summaries, and queryable context. The value is in the transformation, not just the transcript dump.",
      },
    ],
  },
  "/about": {
    eyebrow: "Company",
    title: "About",
    subtitle: "SecondMind is building a memory operating system for people who think faster than traditional tools can capture.",
    lead: "The company thesis is direct: voice notes, transcripts, and note apps still leave too much cognitive work on the user. The system should capture reality as you speak, structure it automatically, and return useful answers later.",
    sections: [
      {
        heading: "What we are building",
        body: "SecondMind combines hardware capture, mobile relay, AI structuring, and memory retrieval into a single product. The result is closer to cognitive infrastructure than to a note-taking app.",
      },
      {
        heading: "Who it is for",
        body: "The first strong fit is people whose thinking happens in motion: founders, operators, researchers, builders, and students who produce raw insight faster than they can organize it manually.",
      },
      {
        heading: "Product direction",
        body: "The product is moving toward a full memory layer: tasks, decisions, ideas, people, follow-ups, daily summaries, and action-ready communication - all linked to the context that produced them.",
      },
    ],
  },
  "/privacy-policy": {
    eyebrow: "Company",
    title: "Privacy Policy",
    subtitle: "This page explains, at a product level, what information the system handles and why.",
    lead: "SecondMind processes audio captures, transcript text, structured memory objects, and account-level metadata needed to run the service. The system is intended to minimize privileged client-side access and keep sensitive operations on the backend.",
    sections: [
      {
        heading: "Information handled",
        body: "The platform may process account identity, paired device identifiers, uploaded audio, transcripts, structured memory outputs, action drafts, and operational metadata such as timestamps and job status.",
      },
      {
        heading: "Why data is used",
        body: "Data is used to authenticate devices, relay captures, transcribe speech, extract structured memory, answer user queries, generate summaries, and surface action-oriented results inside the app.",
      },
      {
        heading: "Storage and retention",
        body: "Storage policy is being designed around private storage, backend-only privileged access, and explicit user-scoped data ownership. Retention and deletion policies should be reviewed before broad public rollout.",
      },
      {
        heading: "User control",
        body: "Users should be able to manage account-level data, paired devices, and derived memory records through the app and backend controls as the platform matures.",
      },
    ],
  },
  "/terms-of-service": {
    eyebrow: "Company",
    title: "Terms of Service",
    subtitle: "These terms describe the operating rules for accessing the current product experience.",
    lead: "SecondMind is an evolving product. By using the service, users agree to use the system lawfully, protect their account credentials, and understand that features, limits, and availability may change as the platform develops.",
    sections: [
      {
        heading: "Access and accounts",
        body: "Users are responsible for maintaining control over their account and device credentials. Access may be suspended or revoked if the service is abused, attacked, or used in ways that threaten platform stability or user safety.",
      },
      {
        heading: "Acceptable use",
        body: "The platform may not be used for unlawful surveillance, impersonation, credential abuse, or any behavior that interferes with the service or other users.",
      },
      {
        heading: "Product evolution",
        body: "Because the platform is under active development, capabilities may change, features may be added or removed, and availability is not guaranteed at all times.",
      },
      {
        heading: "Liability boundary",
        body: "Users should not treat generated summaries, drafts, or structured outputs as guaranteed factual records without review. The system is intended to assist memory and action, not replace judgment.",
      },
    ],
  },
  "/contact": {
    eyebrow: "Company",
    title: "Contact",
    subtitle: "For pilots, partnerships, research, and early access, use the product entry points already built into the site.",
    lead: "SecondMind is currently best reached through the early-access flow. That keeps inbound requests attached to product intent instead of scattering them across disconnected channels.",
    sections: [
      {
        heading: "Early access",
        body: "If you want to test the system, use the request access flow on the homepage. Include your role, use case, and what you want the memory layer to solve.",
      },
      {
        heading: "Partnerships and pilots",
        body: "Hardware pilots, founder workflows, research collaborations, and product design partnerships are easier to evaluate when the request includes the environment, scale, and expected capture pattern.",
      },
      {
        heading: "Security or privacy issues",
        body: "If you need to report a security or privacy concern, use the same contact path and mark the request clearly so it can be handled separately from general access requests.",
      },
    ],
  },
};

function Nav() {
  const [scrolled, setScrolled] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();
  const isHome = location.pathname === "/";

  useEffect(() => {
    const fn = () => setScrolled(window.scrollY > 40);
    window.addEventListener("scroll", fn);
    return () => window.removeEventListener("scroll", fn);
  }, []);

  const scrollToSection = (id: string) => {
    if (!isHome) {
      navigate("/");
      window.setTimeout(() => {
        document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
      }, 80);
      return;
    }
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
  };

  const navSpring = useSpring({
    background: scrolled ? "rgba(0,0,0,0.85)" : "rgba(0,0,0,0)",
    borderBottom: scrolled
      ? "1px solid rgba(255,255,255,0.08)"
      : "1px solid rgba(255,255,255,0)",
    config: springConfig.gentle,
  });

  return (
    <animated.nav
      style={{
        ...navSpring,
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        zIndex: 100,
        padding: scrolled ? "1rem 2.5rem" : "1.2rem 2.5rem",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        backdropFilter: scrolled ? "blur(20px)" : "none",
        transition: "padding 0.3s",
      }}
    >
      <motion.div
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.6 }}
        style={{ display: "flex", alignItems: "center", gap: 12, cursor: "pointer" }}
        onClick={() => {
          if (!isHome) {
            navigate("/");
            return;
          }
          window.scrollTo({ top: 0, behavior: "smooth" });
        }}
      >
        <img 
          src="/logo.png" 
          alt="SecondMind Logo" 
          style={{ height: 28, width: "auto", objectFit: "contain" }} 
        />
        <span
          style={{
            fontWeight: 800,
            fontSize: 20,
            letterSpacing: "-0.04em",
            color: "#fff",
          }}
        >
          SecondMind
        </span>
      </motion.div>

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.3 }}
        style={{ display: "flex", gap: 32, alignItems: "center" }}
      >
        {[
          { name: "How it works", id: "how-it-works" },
          { name: "Features", id: "features" },
          { name: "Vision", id: "vision" }
        ].map((l) => (
          <button
            key={l.id}
            style={{
              color: "rgba(255,255,255,0.5)",
              fontSize: 13,
              fontWeight: 500,
              background: "transparent",
              border: "none",
              cursor: "pointer",
              transition: "color 0.2s, transform 0.2s",
            }}
            onClick={() => scrollToSection(l.id)}
            onMouseEnter={(e) => {
              (e.target as HTMLElement).style.color = "#fff";
              (e.target as HTMLElement).style.transform = "translateY(-1px)";
            }}
            onMouseLeave={(e) => {
              (e.target as HTMLElement).style.color = "rgba(255,255,255,0.5)";
              (e.target as HTMLElement).style.transform = "translateY(0)";
            }}
          >
            {l.name}
          </button>
        ))}
        <motion.button
          whileHover={{ scale: 1.05, boxShadow: "0 0 20px rgba(255,255,255,0.1)" }}
          whileTap={{ scale: 0.95 }}
          style={{
            background: "#fff",
            color: "#000",
            border: "none",
            borderRadius: 8,
            padding: "10px 24px",
            fontSize: 13,
            fontWeight: 700,
            cursor: "pointer",
            letterSpacing: "-0.01em",
          }}
          onClick={() => scrollToSection("cta")}
        >
          Get access
        </motion.button>
      </motion.div>
    </animated.nav>
  );
}

const CHARACTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789@#$%&*+=-";

function DecryptText({ text }: { text: string }) {
  const [displayedText, setDisplayedText] = useState(text);

  useEffect(() => {
    let iteration = 0;
    const interval = setInterval(() => {
      setDisplayedText((prev) =>
        prev
          .split("")
          .map((_, index) => {
            if (index < iteration) return text[index];
            return CHARACTERS[Math.floor(Math.random() * CHARACTERS.length)];
          })
          .join("")
      );

      if (iteration >= text.length) clearInterval(interval);
      iteration += 1 / 2; // Speed of decipher
    }, 40);

    return () => clearInterval(interval);
  }, [text]);

  return <>{displayedText}</>;
}

function HomePage({
  mousePos,
}: {
  mousePos: { x: number; y: number };
}) {
  return (
    <div style={{ background: "#000", minHeight: "100vh", position: "relative", color: "#fff", overflowX: "clip" }}>
      <KnowledgeGraph />
      <div
        style={{
          position: "fixed",
          inset: 0,
          zIndex: 0,
          pointerEvents: "none",
          background: `radial-gradient(circle at ${mousePos.x}px ${mousePos.y}px, rgba(255,255,255,0.03) 0%, transparent 40%)`
        }}
      />

      <div style={{ position: "relative", zIndex: 1 }}>
        <Nav />
        <Hero />
        <div id="how-it-works">
          <ProblemSection />
          <PipelineSection />
          <DeviceExploded />
        </div>
        <div id="features">
          <FeaturesSection />
        </div>
        <div id="vision">
          <VisionSection />
        </div>
        <div id="cta">
          <CTA />
        </div>
        <Footer />
      </div>
    </div>
  );
}

function DocumentPage({ content }: { content: DocPageContent }) {
  return (
    <div style={{ background: "#000", minHeight: "100vh", color: "#fff", position: "relative", overflowX: "clip" }}>
      <div
        style={{
          position: "fixed",
          inset: 0,
          pointerEvents: "none",
          background: "radial-gradient(circle at 15% 20%, rgba(98, 154, 255, 0.12) 0%, transparent 30%), radial-gradient(circle at 82% 12%, rgba(255,255,255,0.08) 0%, transparent 24%), linear-gradient(180deg, rgba(255,255,255,0.02) 0%, rgba(0,0,0,0) 24%)",
          zIndex: 0,
        }}
      />
      <div style={{ position: "relative", zIndex: 1 }}>
        <Nav />
        <main style={{ maxWidth: 1180, margin: "0 auto", padding: "140px 2.5rem 0" }}>
          <section style={{ padding: "0 0 64px", borderBottom: "1px solid rgba(255,255,255,0.08)" }}>
            <div style={{ display: "inline-flex", alignItems: "center", gap: 10, marginBottom: 20, padding: "8px 14px", border: "1px solid rgba(255,255,255,0.1)", borderRadius: 999, background: "rgba(255,255,255,0.03)" }}>
              <div style={{ width: 8, height: 8, borderRadius: "50%", background: "#7ba8ff", boxShadow: "0 0 18px rgba(123,168,255,0.65)" }} />
              <span style={{ fontSize: 11, letterSpacing: "0.14em", textTransform: "uppercase", color: "rgba(255,255,255,0.55)", fontWeight: 700 }}>{content.eyebrow}</span>
            </div>
            <h1 style={{ fontSize: "clamp(52px, 8vw, 108px)", lineHeight: 0.95, letterSpacing: "-0.055em", fontWeight: 900, maxWidth: 900 }}>{content.title}</h1>
            <p style={{ marginTop: 22, maxWidth: 760, fontSize: "clamp(18px, 2vw, 22px)", lineHeight: 1.5, color: "rgba(255,255,255,0.52)" }}>{content.subtitle}</p>
          </section>

          <section style={{ display: "grid", gridTemplateColumns: "minmax(0, 1.2fr) minmax(280px, 0.8fr)", gap: 56, padding: "56px 0 80px" }}>
            <div>
              <p style={{ fontSize: 18, lineHeight: 1.8, color: "rgba(255,255,255,0.76)", maxWidth: 760 }}>{content.lead}</p>
            </div>
            <div style={{ alignSelf: "start", padding: "22px 24px", borderRadius: 20, background: "linear-gradient(180deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.02) 100%)", border: "1px solid rgba(255,255,255,0.08)" }}>
              <div style={{ fontSize: 11, letterSpacing: "0.14em", textTransform: "uppercase", color: "rgba(255,255,255,0.35)", marginBottom: 14 }}>Document structure</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {content.sections.map((section, index) => (
                  <div key={section.heading} style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
                    <span style={{ color: "#7ba8ff", fontWeight: 700, fontSize: 13, minWidth: 20 }}>{String(index + 1).padStart(2, "0")}</span>
                    <span style={{ color: "rgba(255,255,255,0.72)", fontSize: 14, lineHeight: 1.5 }}>{section.heading}</span>
                  </div>
                ))}
              </div>
            </div>
          </section>

          <section style={{ display: "flex", flexDirection: "column", gap: 40, paddingBottom: 100 }}>
            {content.sections.map((section, index) => (
              <section key={section.heading} style={{ display: "grid", gridTemplateColumns: "180px minmax(0, 1fr)", gap: 36, paddingTop: 28, borderTop: index === 0 ? "1px solid rgba(255,255,255,0.08)" : "1px solid rgba(255,255,255,0.06)" }}>
                <div style={{ fontSize: 12, letterSpacing: "0.14em", textTransform: "uppercase", color: "rgba(255,255,255,0.28)", fontWeight: 700, paddingTop: 8 }}>
                  {section.heading}
                </div>
                <div>
                  <p style={{ fontSize: 17, lineHeight: 1.85, color: "rgba(255,255,255,0.8)", maxWidth: 800 }}>{section.body}</p>
                  {section.bullets && (
                    <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 18, marginTop: 28 }}>
                      {section.bullets.map((bullet) => (
                        <div key={bullet} style={{ padding: "18px 20px", borderRadius: 18, background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)" }}>
                          <div style={{ width: 30, height: 1, background: "rgba(123,168,255,0.8)", marginBottom: 14 }} />
                          <p style={{ fontSize: 15, lineHeight: 1.65, color: "rgba(255,255,255,0.72)" }}>{bullet}</p>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </section>
            ))}
          </section>

          <section style={{ marginBottom: 96, padding: "34px 0 0", borderTop: "1px solid rgba(255,255,255,0.08)", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 24, flexWrap: "wrap" }}>
            <div>
              <div style={{ fontSize: 11, letterSpacing: "0.14em", textTransform: "uppercase", color: "rgba(255,255,255,0.35)", marginBottom: 10 }}>Next step</div>
              <p style={{ fontSize: 18, lineHeight: 1.6, color: "rgba(255,255,255,0.78)", maxWidth: 620 }}>Go back to the landing page and request access if you want to see the full hardware, app, and memory stack in action.</p>
            </div>
            <Link to="/" style={{ display: "inline-flex", alignItems: "center", justifyContent: "center", padding: "15px 28px", borderRadius: 12, background: "#fff", color: "#000", fontWeight: 700, fontSize: 14, letterSpacing: "-0.01em" }}>
              Return to homepage
            </Link>
          </section>
        </main>
        <Footer />
      </div>
    </div>
  );
}

function Hero() {
  const ref = useRef(null);
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start start", "end start"] });
  
  const bgY = useTransform(scrollYProgress, [0, 1], ["0%", "35%"]);
  const bgOpacity = useTransform(scrollYProgress, [0, 0.7], [1, 0]);
  const contentY = useTransform(scrollYProgress, [0, 1], ["0%", "20%"]);
  const contentOpacity = useTransform(scrollYProgress, [0, 0.7], [1, 0]);

  const words = ["Think.", "Capture.", "Structure.", "Synthesize."];
  const [activeWord, setActiveWord] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setActiveWord((p) => (p + 1) % words.length), 2500);
    return () => clearInterval(t);
  }, []);

  return (
    <section
      ref={ref}
      style={{
        minHeight: "100vh",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        position: "relative",
        overflow: "hidden",
        background: "#000",
        paddingTop: "60px"
      }}
    >
      {/* Dynamic Data Streams */}
      <motion.div style={{ position: "absolute", inset: 0, zIndex: 0, opacity: bgOpacity, pointerEvents: "none" }}>
        {/* Vertical processing lines */}
        {[...Array(6)].map((_, i) => (
          <motion.div
            key={`line-${i}`}
            initial={{ y: "-100%" }}
            animate={{ y: "100%" }}
            transition={{ repeat: Infinity, duration: 8 + i * 2, ease: "linear", delay: i * 1.5 }}
            style={{
              position: "absolute",
              left: `${15 + i * 14}%`,
              width: 1,
              height: "100vh",
              background: "linear-gradient(to bottom, transparent, rgba(255,255,255,0.1), transparent)",
            }}
          />
        ))}
      </motion.div>

      {/* Floating UI Data Cards (Parallax) */}
      <motion.div style={{ position: "absolute", inset: 0, zIndex: 1, y: bgY, pointerEvents: "none", opacity: 0.6 }}>
        {/* Card 1: JSON Data */}
        <motion.div
          animate={{ y: [0, -20, 0], rotate: [0, 2, 0] }}
          transition={{ repeat: Infinity, duration: 6, ease: "easeInOut" }}
          style={{ position: "absolute", top: "25%", left: "10%", background: "rgba(20,20,20,0.8)", border: "1px solid rgba(255,255,255,0.05)", borderRadius: 12, padding: 16, backdropFilter: "blur(10px)", width: 200 }}
        >
          <div style={{ fontSize: 9, color: "rgba(255,255,255,0.3)", fontFamily: "monospace", marginBottom: 8 }}>incoming_stream.json</div>
          <div style={{ fontSize: 10, color: "#4CAF50", fontFamily: "monospace" }}>
            &#123; "intent": "schedule", <br/> "entities": ["investor", "friday"] &#125;
          </div>
        </motion.div>

        {/* Card 2: Audio Waveform */}
        <motion.div
          animate={{ y: [0, 30, 0], rotate: [0, -2, 0] }}
          transition={{ repeat: Infinity, duration: 8, ease: "easeInOut", delay: 1 }}
          style={{ position: "absolute", bottom: "30%", right: "12%", background: "rgba(20,20,20,0.8)", border: "1px solid rgba(255,255,255,0.05)", borderRadius: 12, padding: 16, backdropFilter: "blur(10px)", display: "flex", gap: 4, alignItems: "flex-end", height: 60 }}
        >
          {[...Array(12)].map((_, i) => (
             <motion.div key={i} animate={{ height: ["20%", "100%", "20%"] }} transition={{ repeat: Infinity, duration: 1 + Math.random(), delay: Math.random() }} style={{ width: 4, background: "rgba(255,255,255,0.4)", borderRadius: 2 }} />
          ))}
        </motion.div>
      </motion.div>

      {/* Base Grid & Glow */}
      <div style={{ position: "absolute", inset: 0, backgroundImage: "radial-gradient(ellipse at 50% 50%, rgba(255,255,255,0.07) 0%, transparent 60%)", pointerEvents: "none", zIndex: 0 }} />

      {/* Hero Content */}
      <motion.div
        style={{ position: "relative", zIndex: 2, textAlign: "center", maxWidth: 840, padding: "0 2rem", y: contentY, opacity: contentOpacity }}
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
      >
        <div style={{ display: "inline-block", background: "rgba(255,255,255,0.05)", padding: "6px 14px", borderRadius: 100, border: "1px solid rgba(255,255,255,0.1)", marginBottom: 24 }}>
          <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", color: "#fff", textTransform: "uppercase" }}>CortX Engine v1.0 Online</span>
        </div>

        <h1 style={{ fontSize: "clamp(48px, 8vw, 100px)", fontWeight: 900, lineHeight: 1.05, letterSpacing: "-0.04em", marginBottom: 20, color: "#fff" }}>
          <div style={{ height: "1.1em", display: "flex", justifyContent: "center", alignItems: "center" }}>
            <AnimatePresence mode="wait">
              <motion.span
                key={activeWord}
                initial={{ opacity: 0, filter: "blur(10px)" }}
                animate={{ opacity: 1, filter: "blur(0px)" }}
                exit={{ opacity: 0, filter: "blur(10px)" }}
                transition={{ duration: 0.4 }}
              >
                <DecryptText text={words[activeWord]} />
              </motion.span>
            </AnimatePresence>
          </div>
          <span style={{ display: "block", color: "rgba(255,255,255,0.2)", fontSize: "0.4em", fontWeight: 400, letterSpacing: "-0.01em", marginTop: 12 }}>
             Unstructured chaos into structured intelligence.
          </span>
        </h1>

        <p style={{ fontSize: "clamp(16px, 2vw, 18px)", color: "rgba(255,255,255,0.45)", lineHeight: 1.6, maxWidth: 580, margin: "0 auto 48px", fontWeight: 400 }}>
          A hardware-integrated ecosystem that captures your ideas seamlessly and transforms them into an actionable, instantly severable knowledge graph.
        </p>

        <div style={{ display: "flex", gap: 16, justifyContent: "center", flexWrap: "wrap" }}>
          <motion.button
            onClick={() => document.getElementById("cta")?.scrollIntoView({ behavior: "smooth" })}
            whileHover={{ scale: 1.04, boxShadow: "0 0 40px rgba(255,255,255,0.2)" }}
            whileTap={{ scale: 0.97 }}
            style={{ background: "#fff", color: "#000", border: "none", borderRadius: 12, padding: "16px 36px", fontSize: 15, fontWeight: 700, cursor: "pointer", letterSpacing: "-0.01em" }}
          >
            Request early access
          </motion.button>
          
          <motion.button
            onClick={() => document.getElementById("how-it-works")?.scrollIntoView({ behavior: "smooth" })}
            whileHover={{ scale: 1.04, background: "rgba(255,255,255,0.05)" }}
            style={{ background: "transparent", color: "#fff", border: "1px solid rgba(255,255,255,0.2)", borderRadius: 12, padding: "16px 36px", fontSize: 15, fontWeight: 500, cursor: "pointer", transition: "background 0.2s" }}
          >
            Explore pipeline
          </motion.button>
        </div>
      </motion.div>

      {/* Mouse scroll indicator */}
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.5 }} style={{ position: "absolute", bottom: 40, left: "50%", transform: "translateX(-50%)", display: "flex", flexDirection: "column", alignItems: "center", gap: 12 }}>
        <p style={{ fontSize: 10, letterSpacing: "0.2em", textTransform: "uppercase", color: "rgba(255,255,255,0.3)" }}>Scroll to explore</p>
        <motion.div animate={{ y: [0, 10, 0], opacity: [0.3, 1, 0.3] }} transition={{ repeat: Infinity, duration: 2, ease: "easeInOut" }} style={{ width: 1, height: 32, background: "linear-gradient(to bottom, #fff, transparent)" }} />
      </motion.div>
    </section>
  );
}


function ProblemSection() {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-100px" });

  const problems = [
    { icon: "◎", who: "Students", what: "Lose key insights from lectures before they can become action." },
    { icon: "◈", who: "Developers", what: "Forget the logic behind critical technical decisions." },
    { icon: "◇", who: "Founders", what: "Lose high-potential ideas during daily operational chaos." },
  ];

  const trail = useTrail(problems.length, {
    opacity: isInView ? 1 : 0,
    y: isInView ? 0 : 40,
    config: springConfig.gentle,
  });

  return (
    <section
      ref={ref}
      style={{
        background: "transparent",
        padding: "120px 2rem",
      }}
    >
      <div style={{ maxWidth: 1000, margin: "0 auto" }}>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6 }}
          style={{ marginBottom: 72 }}
        >
          <p
            style={{
              fontSize: 11,
              letterSpacing: "0.15em",
              textTransform: "uppercase",
              color: "rgba(255,255,255,0.3)",
              marginBottom: 16,
            }}
          >
            The Problem
          </p>
          <h2
            style={{
              fontSize: "clamp(32px, 5vw, 56px)",
              fontWeight: 800,
              letterSpacing: "-0.04em",
              lineHeight: 1.1,
              maxWidth: 600,
              color: "#fff",
            }}
          >
            You think fast.
            <br />
            You forget faster.
          </h2>
        </motion.div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
            gap: 20,
          }}
        >
          {trail.map((style: any, i: number) => (
            <animated.div
              key={i}
              style={{
                ...style,
                background: "#111",
                border: "1px solid rgba(255,255,255,0.08)",
                borderRadius: 12,
                padding: 28,
              }}
            >
              <div style={{ fontSize: 22, marginBottom: 16, color: "rgba(255,255,255,0.4)" }}>
                {problems[i].icon}
              </div>
              <p style={{ fontSize: 13, fontWeight: 600, color: "#fff", marginBottom: 8, letterSpacing: "-0.01em" }}>
                {problems[i].who}
              </p>
              <p style={{ fontSize: 14, color: "rgba(255,255,255,0.45)", lineHeight: 1.65 }}>
                {problems[i].what}
              </p>
            </animated.div>
          ))}
        </div>
      </div>
    </section>
  );
}

function PipelineSection() {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-100px" });

  const steps = [
    { 
      label: "Capture", 
      detail: "Hardware-accelerated audio ingestion.", 
      longDetail: "The ESP32-S3 wearable captures raw audio and handles local VAD (Voice Activity Detection), ensuring only meaningful speech is transmitted.",
      icon: "⬡" 
    },
    { 
      label: "Stream & Auth", 
      detail: "Zero-latency secure transmission.", 
      longDetail: "Audio packets are streamed via BLE 5.0 to your mobile device, authenticated, and relayed to the CortX API via secure WebSockets.",
      icon: "⬢" 
    },
    { 
      label: "Transcribe", 
      detail: "Whisper Large-v3 processing.", 
      longDetail: "GPU-accelerated inference converts speech to text in real-time, achieving near-perfect accuracy even in noisy environments.",
      icon: "⬡" 
    },
    { 
      label: "Distill & Map", 
      detail: "LLM-driven semantic routing.", 
      longDetail: "A local LLM analyzes intent, extracts action items, identifies named entities, and prepares the data for graph insertion.",
      icon: "⬢" 
    },
    { 
      label: "Synthesize", 
      detail: "Building the personal knowledge graph.", 
      longDetail: "Extracted concepts are embedded via Nomic-Embed and stored in Qdrant, linking new thoughts to your existing memory matrix.",
      icon: "⬡" 
    },
  ];

  const [activeStep, setActiveStep] = useState<number | null>(null);

  // Waveform constants
  const wavePoints = [10, 30, 15, 45, 20, 55, 10, 35, 25, 50, 20];

  return (
    <section
      ref={ref}
      style={{
        background: "transparent",
        padding: "160px 2rem",
        position: "relative",
        overflow: "hidden",
      }}
    >
      <div style={{ maxWidth: 1000, margin: "0 auto", position: "relative" }}>
        
        {/* Header */}
        <div style={{ textAlign: "center", marginBottom: 120 }}>
          <motion.p
            initial={{ opacity: 0 }}
            animate={isInView ? { opacity: 1 } : {}}
            transition={{ duration: 1 }}
            style={{ fontSize: 12, letterSpacing: "0.25em", textTransform: "uppercase", color: "rgba(255,255,255,0.4)", marginBottom: 20 }}
          >
            The Pipeline
          </motion.p>
          <motion.h2
            initial={{ opacity: 0, y: 20 }}
            animate={isInView ? { opacity: 1, y: 0 } : {}}
            transition={{ duration: 0.8, delay: 0.1 }}
            style={{ fontSize: "clamp(40px, 6vw, 72px)", fontWeight: 900, letterSpacing: "-0.04em", color: "#fff", lineHeight: 1.05 }}
          >
            Raw speech to
            <br />
            structured intellect.
          </motion.h2>
        </div>

        {/* Dynamic Waveform Header */}
        <div style={{ position: "relative", height: 80, marginBottom: -40, display: "flex", alignItems: "center", justifyContent: "center", gap: 6, zIndex: 0 }}>
          {wavePoints.map((h, i) => (
            <motion.div
              key={i}
              initial={{ height: 4 }}
              animate={isInView ? { height: [h, h * 0.4, h] } : {}}
              transition={{ repeat: Infinity, duration: 1.5 + i * 0.1, ease: "easeInOut" }}
              style={{
                width: 3,
                background: "linear-gradient(to bottom, transparent, #fff, transparent)",
                borderRadius: 2,
                opacity: 0.15,
              }}
            />
          ))}
        </div>

        {/* Vertical Timeline Layout */}
        <div style={{ position: "relative", marginTop: 80 }}>
          {/* Center Line */}
          <motion.div 
            initial={{ height: 0 }}
            animate={isInView ? { height: "100%" } : {}}
            transition={{ duration: 2, ease: "easeInOut" }}
            style={{ position: "absolute", left: "50%", top: 0, width: 1, background: "linear-gradient(to bottom, transparent, rgba(255,255,255,0.1) 10%, rgba(255,255,255,0.1) 90%, transparent)", transform: "translateX(-50%)", zIndex: 0 }}
          />

          {steps.map((step, i) => {
            const isLeft = i % 2 === 0;
            return (
              <div key={i} style={{ display: "flex", justifyContent: isLeft ? "flex-start" : "flex-end", width: "100%", marginBottom: i === steps.length - 1 ? 0 : 80, position: "relative" }}>
                
                {/* Center Node */}
                <motion.div 
                  initial={{ scale: 0, opacity: 0 }}
                  animate={isInView ? { scale: 1, opacity: 1 } : {}}
                  transition={{ delay: 0.5 + i * 0.2, duration: 0.5 }}
                  style={{ position: "absolute", left: "50%", top: "50%", transform: "translate(-50%, -50%)", width: 16, height: 16, borderRadius: "50%", background: "#000", border: activeStep === i ? "2px solid #fff" : "2px solid rgba(255,255,255,0.2)", zIndex: 1, display: "flex", alignItems: "center", justifyContent: "center", transition: "border 0.3s" }}
                >
                  <motion.div 
                    animate={activeStep === i ? { scale: [1, 1.5, 1], opacity: [1, 0.5, 1] } : {}} 
                    transition={{ repeat: Infinity, duration: 2 }}
                    style={{ width: 4, height: 4, borderRadius: "50%", background: activeStep === i ? "#fff" : "transparent" }}
                  />
                </motion.div>

                {/* Content Card */}
                <motion.div
                  initial={{ opacity: 0, x: isLeft ? 50 : -50 }}
                  animate={isInView ? { opacity: 1, x: 0 } : {}}
                  transition={{ delay: 0.4 + i * 0.15, duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
                  onMouseEnter={() => setActiveStep(i)}
                  onMouseLeave={() => setActiveStep(null)}
                  style={{
                    width: "calc(50% - 60px)",
                    background: activeStep === i ? "rgba(255,255,255,0.03)" : "rgba(255,255,255,0.01)",
                    border: activeStep === i ? "1px solid rgba(255,255,255,0.1)" : "1px solid rgba(255,255,255,0.03)",
                    padding: 40,
                    borderRadius: 16,
                    textAlign: isLeft ? "right" : "left",
                    cursor: "pointer",
                    transition: "all 0.4s cubic-bezier(0.16, 1, 0.3, 1)",
                    transform: activeStep === i ? (isLeft ? "translateX(-10px)" : "translateX(10px)") : "translateX(0)",
                  }}
                >
                  <div style={{ fontSize: 11, fontWeight: 700, color: "rgba(255,255,255,0.2)", marginBottom: 12, letterSpacing: "0.1em" }}>STEP 0{i+1}</div>
                  <h3 style={{ fontSize: 24, fontWeight: 700, color: "#fff", marginBottom: 12, letterSpacing: "-0.02em" }}>{step.label}</h3>
                  <p style={{ fontSize: 14, color: "rgba(255,255,255,0.6)", lineHeight: 1.5, marginBottom: activeStep === i ? 20 : 0, transition: "margin 0.3s" }}>{step.detail}</p>
                  
                  {/* Expandable Detail */}
                  <div style={{ overflow: "hidden", height: activeStep === i ? "auto" : 0, opacity: activeStep === i ? 1 : 0, transition: "all 0.3s" }}>
                    <div style={{ height: 1, background: "rgba(255,255,255,0.1)", marginBottom: 20 }} />
                    <p style={{ fontSize: 13, color: "rgba(255,255,255,0.4)", lineHeight: 1.6 }}>{step.longDetail}</p>
                  </div>
                </motion.div>
              </div>
            );
          })}
        </div>

      </div>
    </section>
  );
}

function FeaturesSection() {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-80px" });

  const features = [
    { title: "Knowledge Graphs", desc: "Connects thoughts over time. See how your ideas evolve and relate across different recordings.", icon: "⎈" },
    { title: "Smart Reminders", desc: "Detects tasks automatically. \"Finish the report by Thursday\" becomes a calendar entry.", icon: "⏱" },
    { title: "Daily Intelligence", desc: "A condensed executive summary of your messy talks and decisions, delivered every evening.", icon: "✧" },
    { title: "Semantic Search", desc: "Ask \"What did I discuss with the investor?\" and get an actual answer based on intent.", icon: "⌕" },
    { title: "Privacy First", desc: "No human review. Full AES-256 encryption in transit. Data deleted immediately after processing.", icon: "⚿" },
    { title: "Team Memory", desc: "Shared cognitive layers for meetings. Query insights across your entire team's captured audio.", icon: "⑂" },
  ];

  const trail = useTrail(features.length, {
    opacity: isInView ? 1 : 0,
    scale: isInView ? 1 : 0.95,
    config: { tension: 120, friction: 14 },
    delay: isInView ? 100 : 0,
  });

  return (
    <section
      ref={ref}
      style={{
        background: "transparent",
        padding: "160px 2rem",
        position: "relative",
      }}
    >
      <div style={{ maxWidth: 1100, margin: "0 auto" }}>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6 }}
          style={{ marginBottom: 80, textAlign: "center" }}
        >
          <p style={{ fontSize: 12, letterSpacing: "0.2em", textTransform: "uppercase", color: "rgba(255,255,255,0.4)", marginBottom: 16 }}>
            Core Capabilities
          </p>
          <h2 style={{ fontSize: "clamp(32px, 5vw, 56px)", fontWeight: 900, letterSpacing: "-0.04em", color: "#fff", maxWidth: 600, margin: "0 auto", lineHeight: 1.1 }}>
            Intelligence,
            <br />
            not just storage.
          </h2>
        </motion.div>

        {/* Masonry / Grid layout */}
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(320px, 1fr))",
            gap: 20,
            position: "relative",
          }}
        >
          {trail.map((style: any, i: number) => {
            const isFeatured = i === 0 || i === 3;
            return (
              <animated.div 
                key={i} 
                className="feature-card"
                style={{
                  ...style,
                  gridColumn: isFeatured ? "span 2" : "span 1",
                } as any}
              >
                <motion.div
                  whileHover={{ y: -5 }}
                  style={{ 
                    height: "100%",
                    padding: "32px 0", 
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "flex-start",
                    position: "relative",
                    borderTop: "1px solid rgba(255,255,255,0.1)",
                    transition: "all 0.3s ease",
                  }}
                >
                  <div>
                    <div
                      style={{
                        fontSize: 24,
                        color: "#fff",
                        marginBottom: 20,
                        display: "inline-flex",
                        alignItems: "center",
                        justifyContent: "center",
                      }}
                    >
                      {features[i].icon}
                    </div>
                    <h3 style={{ fontSize: 20, fontWeight: 600, color: "#fff", marginBottom: 12, letterSpacing: "-0.02em" }}>
                      {features[i].title}
                    </h3>
                  </div>
                  <p style={{ fontSize: 14, color: "rgba(255,255,255,0.45)", lineHeight: 1.6 }}>
                    {features[i].desc}
                  </p>
                </motion.div>
              </animated.div>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function VisionSection() {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-80px" });
  const [activePhase, setActivePhase] = useState(0);

  const phases = [
    { num: "01", phase: "Individuals", sub: "Cognitive Augmentation", desc: "A personal exoskeleton for your mind. Never lose a thought, command, or insight again." },
    { num: "02", phase: "Teams", sub: "Shared Memory", desc: "Instantly query insights across your entire team's conversational graph. Collective intelligence." },
    { num: "03", phase: "Organizations", sub: "Enterprise Intelligence", desc: "A foundational intelligence layer. Map institutional knowledge from the ground up." },
  ];

  return (
    <section ref={ref} style={{ background: "transparent", padding: "160px 2rem", position: "relative", overflow: "hidden" }}>
      <div style={{ maxWidth: 1100, margin: "0 auto", position: "relative", zIndex: 2 }}>
        
        {/* Header */}
        <div style={{ textAlign: "center", marginBottom: 80 }}>
          <motion.p initial={{ opacity: 0 }} animate={isInView ? { opacity: 1 } : {}} transition={{ duration: 1 }} style={{ fontSize: 12, letterSpacing: "0.2em", textTransform: "uppercase", color: "rgba(255,255,255,0.4)", marginBottom: 16 }}>
            The Master Plan
          </motion.p>
          <motion.h2 initial={{ opacity: 0, y: 20 }} animate={isInView ? { opacity: 1, y: 0 } : {}} transition={{ duration: 0.8 }} style={{ fontSize: "clamp(36px, 5vw, 64px)", fontWeight: 900, letterSpacing: "-0.04em", lineHeight: 1.05, color: "#fff" }}>
            Scaling cognitive <br />infrastructure.
          </motion.h2>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(400px, 1fr))", gap: 80, alignItems: "center" }}>
          
          {/* Dynamic Graphic UI */}
          <motion.div initial={{ opacity: 0, scale: 0.95 }} animate={isInView ? { opacity: 1, scale: 1 } : {}} transition={{ duration: 1 }} style={{ height: 420, background: "rgba(255,255,255,0.02)", border: "1px solid rgba(255,255,255,0.05)", borderRadius: 32, position: "relative", overflow: "hidden", display: "flex", justifyContent: "center", alignItems: "center" }}>
             {/* Subtle internal grid */}
             <div style={{ position: "absolute", inset: 0, backgroundImage: "radial-gradient(rgba(255,255,255,0.15) 1px, transparent 1px)", backgroundSize: "24px 24px", opacity: 0.3 }} />
             
             {/* Phase 1 Graphic: Single Node */}
             <motion.div animate={{ opacity: activePhase === 0 ? 1 : 0, scale: activePhase === 0 ? 1 : 0.8 }} transition={{ duration: 0.5 }} style={{ position: "absolute", inset: 0, display: "flex", justifyContent: "center", alignItems: "center", pointerEvents: "none" }}>
                <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 15, ease: "linear" }} style={{ width: 140, height: 140, border: "1px dashed rgba(255,255,255,0.3)", borderRadius: "50%", display: "flex", justifyContent: "center", alignItems: "center" }}>
                   <motion.div animate={{ scale: [1, 1.2, 1] }} transition={{ repeat: Infinity, duration: 2 }} style={{ width: 32, height: 32, background: "#fff", borderRadius: "50%", boxShadow: "0 0 60px rgba(255,255,255,0.6)" }} />
                </motion.div>
             </motion.div>

             {/* Phase 2 Graphic: Team Nodes */}
             <motion.div animate={{ opacity: activePhase === 1 ? 1 : 0, scale: activePhase === 1 ? 1 : 0.8 }} transition={{ duration: 0.5 }} style={{ position: "absolute", inset: 0, display: "flex", justifyContent: "center", alignItems: "center", pointerEvents: "none" }}>
                <div style={{ position: "relative", width: 200, height: 200 }}>
                  {[0, 1, 2].map((i) => (
                    <motion.div key={i} animate={{ y: [0, -15, 0] }} transition={{ repeat: Infinity, duration: 3, delay: i * 0.5 }} style={{ position: "absolute", top: i === 0 ? 0 : 120, left: i === 1 ? 0 : (i === 2 ? 140 : 70), width: 24, height: 24, background: "#fff", borderRadius: "50%", boxShadow: "0 0 30px rgba(255,255,255,0.4)" }} />
                  ))}
                  {/* Connecting core */}
                  <svg style={{ position: "absolute", inset: 0, width: "100%", height: "100%", opacity: 0.3 }}>
                    <line x1="82" y1="12" x2="12" y2="132" stroke="#fff" strokeWidth="2" strokeDasharray="4 4" />
                    <line x1="82" y1="12" x2="152" y2="132" stroke="#fff" strokeWidth="2" strokeDasharray="4 4" />
                    <line x1="12" y1="132" x2="152" y2="132" stroke="#fff" strokeWidth="2" strokeDasharray="4 4" />
                  </svg>
                </div>
             </motion.div>

             {/* Phase 3 Graphic: Neural Web */}
             <motion.div animate={{ opacity: activePhase === 2 ? 1 : 0, scale: activePhase === 2 ? 1 : 0.8 }} transition={{ duration: 0.5 }} style={{ position: "absolute", inset: 0, display: "flex", justifyContent: "center", alignItems: "center", flexWrap: "wrap", gap: 30, padding: 60, pointerEvents: "none" }}>
                {[...Array(16)].map((_, i) => (
                  <motion.div key={i} animate={{ opacity: [0.1, 0.8, 0.1], scale: [1, 1.5, 1] }} transition={{ repeat: Infinity, duration: 2, delay: (i * 13 % 7) * 0.2 }} style={{ width: 10, height: 10, background: "#fff", borderRadius: "50%", boxShadow: "0 0 10px rgba(255,255,255,0.8)" }} />
                ))}
             </motion.div>
          </motion.div>

          {/* Interactive Steps List */}
          <div style={{ display: "flex", flexDirection: "column" }}>
            {phases.map((ph, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, x: 20 }}
                animate={isInView ? { opacity: 1, x: 0 } : {}}
                transition={{ delay: i * 0.15 }}
                onClick={() => setActivePhase(i)}
                style={{
                  padding: "32px 0 32px 32px",
                  borderLeft: activePhase === i ? "2px solid #fff" : "2px solid rgba(255,255,255,0.08)",
                  cursor: "pointer",
                  transition: "all 0.4s cubic-bezier(0.16, 1, 0.3, 1)",
                  opacity: activePhase === i ? 1 : 0.4,
                  transform: activePhase === i ? "translateX(10px)" : "translateX(0)",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 8 }}>
                  <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: "0.1em", color: activePhase === i ? "#fff" : "rgba(255,255,255,0.5)" }}>{ph.num}</span>
                  <h3 style={{ fontSize: 26, fontWeight: 800, color: "#fff", letterSpacing: "-0.03em" }}>{ph.phase}</h3>
                </div>
                
                {/* Expandable content area */}
                <div style={{ overflow: "hidden", display: "grid", gridTemplateRows: activePhase === i ? "1fr" : "0fr", transition: "grid-template-rows 0.4s cubic-bezier(0.16, 1, 0.3, 1)" }}>
                  <div style={{ minHeight: 0 }}>
                    <div style={{ marginTop: 12 }}>
                      <p style={{ fontSize: 12, letterSpacing: "0.1em", textTransform: "uppercase", color: "#4CAF50", marginBottom: 12, fontWeight: 700 }}>{ph.sub}</p>
                      <p style={{ fontSize: 15, color: "rgba(255,255,255,0.6)", lineHeight: 1.6, maxWidth: 380 }}>{ph.desc}</p>
                    </div>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>

        </div>
      </div>
    </section>
  );
}

function CTA() {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-100px" });

  const ctaSpring = useSpring({
    opacity: isInView ? 1 : 0,
    y: isInView ? 0 : 40,
    config: springConfig.slow,
  });

  return (
    <section
      ref={ref}
      style={{
        background: "transparent",
        padding: "140px 2rem",
        textAlign: "center",
        position: "relative",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          position: "absolute",
          top: "50%",
          left: "50%",
          transform: "translate(-50%, -50%)",
          width: 700,
          height: 400,
          borderRadius: "50%",
          background: "radial-gradient(ellipse, rgba(255,255,255,0.04) 0%, transparent 70%)",
          pointerEvents: "none",
        }}
      />
      <animated.div style={{ ...ctaSpring, position: "relative", zIndex: 2 }}>
        <p style={{ fontSize: 11, letterSpacing: "0.15em", textTransform: "uppercase", color: "rgba(255,255,255,0.3)", marginBottom: 24 }}>
          Get early access
        </p>
        <h2
          style={{
            fontSize: "clamp(40px, 7vw, 80px)",
            fontWeight: 900,
            letterSpacing: "-0.04em",
            lineHeight: 1,
            color: "#fff",
            marginBottom: 24,
          }}
        >
          Don't lose
          <br />
          another idea.
        </h2>
        <p style={{ fontSize: 16, color: "rgba(255,255,255,0.4)", marginBottom: 48, maxWidth: 420, margin: "0 auto 48px", lineHeight: 1.65 }}>
          Join the waitlist for SecondMind. Be among the first to turn your unstructured thinking into structured intelligence.
        </p>
        <div
          style={{
            display: "flex",
            gap: 10,
            justifyContent: "center",
            maxWidth: 540,
            margin: "0 auto",
            flexWrap: "wrap",
          }}
        >
          <input
            type="email"
            placeholder="your@email.com"
            style={{
              flex: 1,
              minWidth: 200,
              padding: "13px 18px",
              background: "rgba(255,255,255,0.05)",
              border: "1px solid rgba(255,255,255,0.12)",
              borderRadius: 8,
              color: "#fff",
              fontSize: 14,
              fontFamily: "inherit",
            }}
          />
          <motion.button
            whileHover={{ scale: 1.04, boxShadow: "0 0 28px rgba(255,255,255,0.15)" }}
            whileTap={{ scale: 0.97 }}
            style={{
              background: "#fff",
              color: "#000",
              border: "none",
              borderRadius: 8,
              padding: "13px 24px",
              fontSize: 14,
              fontWeight: 700,
              cursor: "pointer",
              whiteSpace: "nowrap",
            }}
          >
            Join waitlist
          </motion.button>
        </div>
        <div
          style={{
            display: "flex",
            gap: 12,
            justifyContent: "center",
            marginTop: 28,
            flexWrap: "wrap",
          }}
        >
          <p style={{ fontSize: 12, color: "rgba(255,255,255,0.3)", width: "100%", marginBottom: 8 }}>
            Or download the app
          </p>
          <motion.button
            onClick={() => {
              // Download APK from public folder
              const link = document.createElement("a");
              link.href = "/app-release.apk"; // Corrected filename
              link.download = "SecondMind.apk";
              document.body.appendChild(link);
              link.click();
              document.body.removeChild(link);
            }}
            whileHover={{ scale: 1.04, boxShadow: "0 0 20px rgba(76, 175, 80, 0.3)" }}
            whileTap={{ scale: 0.97 }}
            style={{
              background: "white",
              color: "black",
              border: "none",
              borderRadius: 8,
              padding: "11px 20px",
              fontSize: 13,
              fontWeight: 600,
              cursor: "pointer",
              whiteSpace: "nowrap",
              textDecoration: "none",
              display: "inline-flex",
              alignItems: "center",
              gap: 6,
            }}
          >
             📱 Download APK
          </motion.button>
        </div>
      </animated.div>
    </section>
  );
}

function Footer() {
  return (
    <footer
      style={{
        background: "#000",
        borderTop: "1px solid rgba(255,255,255,0.08)",
        padding: "80px 2.5rem 40px",
        color: "#fff",
        position: "relative",
        overflow: "hidden"
      }}
    >
      <div style={{ maxWidth: 1100, margin: "0 auto", display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 60 }}>
        
        {/* Brand & Mission */}
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
            <img 
              src="/logo.png" 
              alt="SecondMind Logo" 
              style={{ height: 32, width: "auto", objectFit: "contain" }} 
            />
            <span style={{ fontWeight: 800, fontSize: 22, letterSpacing: "-0.04em", color: "#fff" }}>SecondMind</span>
          </div>
          <p style={{ fontSize: 13, color: "rgba(255,255,255,0.4)", lineHeight: 1.6, marginBottom: 24, paddingRight: 40 }}>
            Building the cognitive exoskeleton for the internet. Turning ephemeral thoughts into permanent intelligence.
          </p>
          <div style={{ alignItems: "center", gap: 10, padding: "8px 12px", background: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)", borderRadius: 100, display: "inline-flex" }}>
            <motion.div animate={{ scale: [1, 1.2, 1], opacity: [0.6, 1, 0.6] }} transition={{ repeat: Infinity, duration: 2 }} style={{ width: 8, height: 8, borderRadius: "50%", background: "#4CAF50", boxShadow: "0 0 10px rgba(76, 175, 80, 0.5)" }} />
            <span style={{ fontSize: 11, fontWeight: 600, color: "rgba(255,255,255,0.6)", letterSpacing: "0.05em", textTransform: "uppercase" }}>API Operational</span>
          </div>
        </div>

        {/* Tech & Legal Links */}
        <div style={{ display: "flex", gap: 60 }}>
          <div>
            <h4 style={{ fontSize: 12, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "rgba(255,255,255,0.3)", marginBottom: 20 }}>Technology</h4>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {technologyLinks.map((l) => (
                <Link key={l.path} to={l.path} style={{ fontSize: 13, color: "rgba(255,255,255,0.5)", transition: "color 0.2s" }} onMouseEnter={e => (e.target as HTMLElement).style.color = "#fff"} onMouseLeave={e => (e.target as HTMLElement).style.color = "rgba(255,255,255,0.5)"}>{l.label}</Link>
              ))}
            </div>
          </div>
          <div>
            <h4 style={{ fontSize: 12, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "rgba(255,255,255,0.3)", marginBottom: 20 }}>Company</h4>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {companyLinks.map((l) => (
                <Link key={l.path} to={l.path} style={{ fontSize: 13, color: "rgba(255,255,255,0.5)", transition: "color 0.2s" }} onMouseEnter={e => (e.target as HTMLElement).style.color = "#fff"} onMouseLeave={e => (e.target as HTMLElement).style.color = "rgba(255,255,255,0.5)"}>{l.label}</Link>
              ))}
            </div>
          </div>
        </div>

        {/* Social */}
        <div>
           <h4 style={{ fontSize: 12, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "rgba(255,255,255,0.3)", marginBottom: 20 }}>Connect</h4>
           <div style={{ display: "flex", gap: 16 }}>
             {[
               { name: "GitHub", icon: "⎇" },
               { name: "Discord", icon: "⍾" },
               { name: "X / Twitter", icon: "𝕏" }
             ].map(s => (
               <motion.a key={s.name} href="#" whileHover={{ y: -2, background: "rgba(255,255,255,0.1)" }} style={{ width: 40, height: 40, borderRadius: "50%", background: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.06)", display: "flex", alignItems: "center", justifyContent: "center", textDecoration: "none", color: "#fff", fontSize: 18 }}>
                 {s.icon}
               </motion.a>
             ))}
           </div>
        </div>
      </div>
      
      <div style={{ maxWidth: 1100, margin: "60px auto 0", paddingTop: 30, borderTop: "1px solid rgba(255,255,255,0.06)", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <p style={{ fontSize: 12, color: "rgba(255,255,255,0.3)" }}>© {new Date().getFullYear()} SecondMind. All rights reserved.</p>
        <p style={{ fontSize: 12, color: "rgba(255,255,255,0.3)" }}>Designed for cognitive amplification.</p>
      </div>
    </footer>
  );
}

export default function App() {
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });

  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      setMousePos({ x: e.clientX, y: e.clientY });
    };
    window.addEventListener("mousemove", handleMouseMove);
    
    const style = document.createElement("style");
    style.textContent = globalCSS;
    document.head.appendChild(style);
    
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      document.head.removeChild(style);
    };
  }, []);

  return (
    <Routes>
      <Route path="/" element={<HomePage mousePos={mousePos} />} />
      {Object.entries(docPages).map(([path, content]) => (
        <Route key={path} path={path} element={<DocumentPage content={content} />} />
      ))}
    </Routes>
  );
}
