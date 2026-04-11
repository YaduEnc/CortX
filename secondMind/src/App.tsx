import { useState, useEffect, useRef } from "react";
import { motion, useScroll, useTransform, useInView, AnimatePresence } from "framer-motion";
import { useSpring, animated, useTrail, config as springConfig } from "@react-spring/web";


const globalCSS = `
  @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;900&display=swap');
  *, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }
  html { scroll-behavior: smooth; }
  body { background: #000; color: #fff; font-family: 'Inter', sans-serif; overflow-x: hidden; }
  a { text-decoration: none; }
  input:focus { outline: none; }
`;

function Nav() {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const fn = () => setScrolled(window.scrollY > 40);
    window.addEventListener("scroll", fn);
    return () => window.removeEventListener("scroll", fn);
  }, []);

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
        onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
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
          <a
            key={l.id}
            href={`#${l.id}`}
            style={{
              color: "rgba(255,255,255,0.5)",
              fontSize: 13,
              fontWeight: 500,
              transition: "color 0.2s, transform 0.2s",
            }}
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
          </a>
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
          onClick={() => document.getElementById("cta")?.scrollIntoView({ behavior: "smooth" })}
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
        background: "#0a0a0a",
        padding: "120px 2rem",
        borderTop: "1px solid rgba(255,255,255,0.06)",
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
        background: "#000",
        padding: "160px 2rem",
        borderTop: "1px solid rgba(255,255,255,0.06)",
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

function DeviceSection() {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-100px" });
  
  const nodes = [
    { label: "BLE 5.0", detail: "Ultra-low power audio streaming.", x: 20, y: 30 },
    { label: "Dual MEMS", detail: "Beamforming noise cancellation.", x: 80, y: 25 },
    { label: "Tap Surface", detail: "Capacitive touch command logic.", x: 50, y: 80 },
    { label: "S3 Core", detail: "240MHz AI-accelerated compute.", x: 15, y: 70 },
  ];

  const [activeNode, setActiveNode] = useState(0);

  return (
    <section
      ref={ref}
      style={{
        background: "#0a0a0a",
        padding: "160px 2rem",
        borderTop: "1px solid rgba(255,255,255,0.06)",
        overflow: "hidden",
      }}
    >
      <div style={{ maxWidth: 1100, margin: "0 auto", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 80, alignItems: "center" }}>
        
        {/* Hardware Visual */}
        <div style={{ position: "relative", height: 500, background: "radial-gradient(circle at 50% 50%, rgba(255,255,255,0.03) 0%, transparent 70%)", borderRadius: 24, border: "1px solid rgba(255,255,255,0.03)", display: "flex", alignItems: "center", justifyContent: "center" }}>
          
          {/* Blueprint Grid */}
          <div style={{ position: "absolute", inset: 0, opacity: 0.1, backgroundImage: "radial-gradient(rgba(255,255,255,0.2) 1px, transparent 1px)", backgroundSize: "20px 20px" }} />

          {/* Main Device Body (Image) */}
          <motion.div
            animate={isInView ? { opacity: 1, scale: 1 } : { opacity: 0, scale: 0.9 }}
            transition={{ duration: 1.2, ease: [0.22, 1, 0.36, 1] }}
            style={{ width: 200, height: 400, position: "relative", display: "flex", justifyContent: "center", alignItems: "center" }}
          >
            <img 
              src="/deviceimage.jpeg" 
              alt="CortX Wearable" 
              style={{ width: "100%", height: "100%", objectFit: "contain", filter: "invert(1) drop-shadow(0 0 30px rgba(255,255,255,0.1))", mixBlendMode: "screen", opacity: 0.9 }} 
            />

            {/* Hotspots */}
            {nodes.map((node, i) => (
              <motion.div
                key={i}
                onClick={() => setActiveNode(i)}
                style={{
                  position: "absolute",
                  left: `${node.x}%`,
                  top: `${node.y}%`,
                  width: 12,
                  height: 12,
                  background: activeNode === i ? "#fff" : "transparent",
                  border: "1px solid #fff",
                  borderRadius: "50%",
                  cursor: "pointer",
                  zIndex: 10,
                }}
              >
                <motion.div
                  animate={{ scale: [1, 2.5, 1], opacity: [0.5, 0, 0.5] }}
                  transition={{ repeat: Infinity, duration: 2 }}
                  style={{ position: "absolute", inset: -1, border: "1px solid #fff", borderRadius: "50%" }}
                />
              </motion.div>
            ))}
          </motion.div>
        </div>

        {/* Copy */}
        <div style={{ textAlign: "left" }}>
          <motion.p
            initial={{ opacity: 0, x: 20 }}
            animate={isInView ? { opacity: 1, x: 0 } : {}}
            style={{ fontSize: 12, letterSpacing: "0.2em", textTransform: "uppercase", color: "rgba(255,255,255,0.4)", marginBottom: 16 }}
          >
            Tactile Intelligence
          </motion.p>
          <motion.h2
            initial={{ opacity: 0, x: 20 }}
            animate={isInView ? { opacity: 1, x: 0 } : {}}
            transition={{ delay: 0.1 }}
            style={{ fontSize: "clamp(32px, 4vw, 56px)", fontWeight: 900, letterSpacing: "-0.04em", color: "#fff", marginBottom: 32, lineHeight: 1 }}
          >
            Wearable<br />Compute.
          </motion.h2>

          <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
            {nodes.map((node, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0 }}
                animate={isInView ? { opacity: activeNode === i ? 1 : 0.3 } : {}}
                style={{ cursor: "pointer", transition: "opacity 0.3s" }}
                onClick={() => setActiveNode(i)}
              >
                <h4 style={{ fontSize: 18, fontWeight: 700, color: "#fff", marginBottom: 4, letterSpacing: "-0.02em" }}>{node.label}</h4>
                <p style={{ fontSize: 14, color: "rgba(255,255,255,0.5)", lineHeight: 1.6 }}>{node.detail}</p>
              </motion.div>
            ))}
          </div>
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
        background: "#0a0a0a",
        padding: "160px 2rem",
        borderTop: "1px solid rgba(255,255,255,0.06)",
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
                style={{
                  ...style,
                  gridColumn: isFeatured ? "span 2" : "span 1",
                  '@media (max-width: 768px)': {
                    gridColumn: "span 1",
                  }
                } as any}
              >
                <motion.div
                  whileHover={{ y: -5, boxShadow: "0 20px 40px rgba(0,0,0,0.5)" }}
                  style={{ 
                    height: "100%",
                    padding: 40, 
                    background: "rgba(255,255,255,0.02)", 
                    border: "1px solid rgba(255,255,255,0.05)",
                    borderRadius: 24,
                    transition: "all 0.3s ease",
                    display: "flex",
                    flexDirection: "column",
                    justifyContent: "space-between",
                    position: "relative",
                    overflow: "hidden"
                  }}
                >
                  {/* Subtle gradient glow inside card */}
                  <div style={{ position: "absolute", top: 0, left: 0, right: 0, height: "50%", background: "linear-gradient(180deg, rgba(255,255,255,0.03) 0%, transparent 100%)", pointerEvents: "none" }} />
                  
                  <div>
                    <div
                      style={{
                        fontSize: 28,
                        color: "#fff",
                        marginBottom: 24,
                        display: "inline-flex",
                        alignItems: "center",
                        justifyContent: "center",
                        width: 48,
                        height: 48,
                        background: "rgba(255,255,255,0.08)",
                        borderRadius: 12,
                        boxShadow: "inset 0 1px 0 rgba(255,255,255,0.1)"
                      }}
                    >
                      {features[i].icon}
                    </div>
                    <h3 style={{ fontSize: 22, fontWeight: 700, color: "#fff", marginBottom: 12, letterSpacing: "-0.02em" }}>
                      {features[i].title}
                    </h3>
                  </div>
                  <p style={{ fontSize: 15, color: "rgba(255,255,255,0.5)", lineHeight: 1.6, marginTop: "auto" }}>
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

  const phases = [
    { num: "01", phase: "Individuals", sub: "Students, developers, creators", desc: "Manage and amplify personal cognitive output in real time." },
    { num: "02", phase: "Teams", sub: "Meetings, collaboration", desc: "Shared memory and insights across every team conversation." },
    { num: "03", phase: "Organizations", sub: "Enterprise intelligence", desc: "Large-scale knowledge graphs and productivity analytics." },
  ];

  const leftSpring = useSpring({
    x: isInView ? 0 : -60,
    opacity: isInView ? 1 : 0,
    config: { tension: 120, friction: 20 },
  });

  return (
    <section
      ref={ref}
      style={{
        background: "#000",
        padding: "120px 2rem",
        borderTop: "1px solid rgba(255,255,255,0.06)",
        overflow: "hidden",
      }}
    >
      <div
        style={{
          maxWidth: 1000,
          margin: "0 auto",
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: 60,
          alignItems: "center",
        }}
      >
        <animated.div style={leftSpring}>
          <p style={{ fontSize: 11, letterSpacing: "0.15em", textTransform: "uppercase", color: "rgba(255,255,255,0.3)", marginBottom: 16 }}>
            Vision
          </p>
          <h2 style={{ fontSize: "clamp(28px, 4vw, 48px)", fontWeight: 800, letterSpacing: "-0.04em", lineHeight: 1.1, color: "#fff", marginBottom: 24 }}>
            Scaling human intelligence.
          </h2>
          <p style={{ fontSize: 15, color: "rgba(255,255,255,0.4)", lineHeight: 1.7 }}>
            SecondMind is built for the long arc — from personal cognitive augmentation to team-level shared memory to organization-wide intelligence infrastructure.
          </p>
        </animated.div>

        <div style={{ display: "flex", flexDirection: "column", gap: 0 }}>
          {phases.map((ph, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, x: 40 }}
              animate={isInView ? { opacity: 1, x: 0 } : {}}
              transition={{ delay: i * 0.15, duration: 0.6 }}
              style={{
                padding: "24px 0",
                borderBottom: i < 2 ? "1px solid rgba(255,255,255,0.08)" : "none",
                display: "flex",
                gap: 20,
                alignItems: "flex-start",
              }}
            >
              <span style={{ fontSize: 11, color: "rgba(255,255,255,0.2)", fontWeight: 700, letterSpacing: "0.1em", minWidth: 24, marginTop: 2 }}>
                {ph.num}
              </span>
              <div>
                <p style={{ fontSize: 16, fontWeight: 700, color: "#fff", marginBottom: 4, letterSpacing: "-0.02em" }}>{ph.phase}</p>
                <p style={{ fontSize: 11, color: "rgba(255,255,255,0.3)", letterSpacing: "0.05em", textTransform: "uppercase", marginBottom: 8 }}>{ph.sub}</p>
                <p style={{ fontSize: 13, color: "rgba(255,255,255,0.4)", lineHeight: 1.6 }}>{ph.desc}</p>
              </div>
            </motion.div>
          ))}
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
        background: "#000",
        padding: "140px 2rem",
        borderTop: "1px solid rgba(255,255,255,0.06)",
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
              {["Architecture", "Security", "Open Source", "Whisper v3"].map(l => (
                <a key={l} href="#" style={{ fontSize: 13, color: "rgba(255,255,255,0.5)", transition: "color 0.2s" }} onMouseEnter={e => (e.target as HTMLElement).style.color = "#fff"} onMouseLeave={e => (e.target as HTMLElement).style.color = "rgba(255,255,255,0.5)"}>{l}</a>
              ))}
            </div>
          </div>
          <div>
            <h4 style={{ fontSize: 12, fontWeight: 700, letterSpacing: "0.1em", textTransform: "uppercase", color: "rgba(255,255,255,0.3)", marginBottom: 20 }}>Company</h4>
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              {["About", "Privacy Policy", "Terms of Service", "Contact"].map(l => (
                <a key={l} href="#" style={{ fontSize: 13, color: "rgba(255,255,255,0.5)", transition: "color 0.2s" }} onMouseEnter={e => (e.target as HTMLElement).style.color = "#fff"} onMouseLeave={e => (e.target as HTMLElement).style.color = "rgba(255,255,255,0.5)"}>{l}</a>
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
    <div style={{ background: "#000", minHeight: "100vh", position: "relative", color: "#fff", overflowX: "hidden" }}>
      
      {/* Ambient Neural Background */}
      <div 
        style={{ 
          position: "fixed", 
          inset: 0, 
          zIndex: 0, 
          pointerEvents: "none",
          background: `radial-gradient(circle at ${mousePos.x}px ${mousePos.y}px, rgba(255,255,255,0.03) 0%, transparent 40%)`
        }} 
      />
      <div style={{ position: "fixed", inset: 0, zIndex: 0, opacity: 0.1, backgroundImage: "url('https://grainy-gradients.vercel.app/noise.svg')", pointerEvents: "none" }} />
      
      <div style={{ position: "relative", zIndex: 1 }}>
        <Nav />
        <Hero />
        <div id="how-it-works">
          <ProblemSection />
          <PipelineSection />
          <DeviceSection />
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
