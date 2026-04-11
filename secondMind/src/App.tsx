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
        style={{ display: "flex", alignItems: "center", gap: 10, cursor: "pointer" }}
        onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
      >
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

function Hero() {
  const ref = useRef(null);
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start start", "end start"],
  });
  const bgY = useTransform(scrollYProgress, [0, 1], ["0%", "35%"]);
  const bgOpacity = useTransform(scrollYProgress, [0, 0.7], [1, 0]);
  const contentY = useTransform(scrollYProgress, [0, 1], ["0%", "35%"]);
  const contentOpacity = useTransform(scrollYProgress, [0, 0.7], [1, 0]);
  const contentScale = useTransform(scrollYProgress, [0, 0.8], [1, 0.92]);

  const words = ["Think.", "Capture.", "Structure."];
  const [activeWord, setActiveWord] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setActiveWord((p) => (p + 1) % 3), 1800);
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
      }}
    >
      {/* Grid background */}
      <motion.div
        style={{
          position: "absolute",
          inset: 0,
          backgroundImage:
            "linear-gradient(rgba(255,255,255,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.03) 1px, transparent 1px)",
          backgroundSize: "60px 60px",
          y: bgY,
          opacity: bgOpacity,
        }}
      />
      {/* Radial glow */}
      <div
        style={{
          position: "absolute",
          top: "20%",
          left: "50%",
          transform: "translateX(-50%)",
          width: 600,
          height: 600,
          borderRadius: "50%",
          background:
            "radial-gradient(circle, rgba(255,255,255,0.06) 0%, transparent 70%)",
          pointerEvents: "none",
        }}
      />

      {/* Content */}
      <motion.div
        style={{
          position: "relative",
          zIndex: 2,
          textAlign: "center",
          maxWidth: 800,
          padding: "0 2rem",
          y: contentY,
          opacity: contentOpacity,
          scale: contentScale,
        }}
        initial={{ opacity: 0, y: 30 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1] }}
      >

        {/* Headline */}
        <h1
          style={{
            fontSize: "clamp(52px, 8vw, 96px)",
            fontWeight: 900,
            lineHeight: 1,
            letterSpacing: "-0.04em",
            marginBottom: 20,
            color: "#fff",
          }}
        >
          <AnimatePresence mode="wait">
            <motion.span
              key={activeWord}
              initial={{ opacity: 0, y: 20, filter: "blur(8px)" }}
              animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
              exit={{ opacity: 0, y: -20, filter: "blur(8px)" }}
              transition={{ duration: 0.5 }}
              style={{ display: "block" }}
            >
              {words[activeWord]}
            </motion.span>
          </AnimatePresence>
          <span
            style={{
              display: "block",
              color: "rgba(255,255,255,0.2)",
              fontSize: "0.55em",
              fontWeight: 300,
              letterSpacing: "-0.01em",
              marginTop: 8,
            }}
          >
            Your thoughts. Structured.
          </span>
        </h1>

        <p
          style={{
            fontSize: 18,
            color: "rgba(255,255,255,0.5)",
            lineHeight: 1.7,
            maxWidth: 560,
            margin: "0 auto 40px",
            fontWeight: 300,
          }}
        >
          A hardware-integrated ecosystem that captures unstructured thinking
          and transforms it into actionable intelligence — in real time.
        </p>

        <div
          style={{
            display: "flex",
            gap: 12,
            justifyContent: "center",
            flexWrap: "wrap",
          }}
        >
          <motion.button
            onClick={() => document.getElementById("cta")?.scrollIntoView({ behavior: "smooth" })}
            whileHover={{ scale: 1.04, boxShadow: "0 0 30px rgba(255,255,255,0.2)" }}
            whileTap={{ scale: 0.97 }}
            style={{
              background: "#fff",
              color: "#000",
              border: "none",
              borderRadius: 8,
              padding: "14px 32px",
              fontSize: 15,
              fontWeight: 700,
              cursor: "pointer",
              letterSpacing: "-0.02em",
            }}
          >
            Request early access →
          </motion.button>
          <motion.button
            onClick={() => document.getElementById("how-it-works")?.scrollIntoView({ behavior: "smooth" })}
            whileHover={{ scale: 1.04, background: "rgba(255,255,255,0.08)" }}
            style={{
              background: "transparent",
              color: "#fff",
              border: "1px solid rgba(255,255,255,0.2)",
              borderRadius: 8,
              padding: "14px 32px",
              fontSize: 15,
              fontWeight: 400,
              cursor: "pointer",
              letterSpacing: "-0.02em",
              transition: "background 0.2s",
            }}
          >
            How it works
          </motion.button>
        </div>
      </motion.div>

      {/* Scroll indicator */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1.5 }}
        style={{ position: "absolute", bottom: 32, left: "50%", transform: "translateX(-50%)" }}
      >
        <motion.div
          animate={{ y: [0, 8, 0] }}
          transition={{ repeat: Infinity, duration: 2, ease: "easeInOut" }}
          style={{
            width: 1,
            height: 40,
            background: "linear-gradient(to bottom, rgba(255,255,255,0.6), transparent)",
            margin: "0 auto",
          }}
        />
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
    { label: "Capture", detail: "ESP32-S3 wearable tags audio via BLE.", icon: "⬡" },
    { label: "Stream", detail: "Real-time Opus/WAV 16kHz pipeline.", icon: "⬢" },
    { label: "Transcribe", detail: "Whisper Large-v3 turbo-speed STT.", icon: "⬡" },
    { label: "Distill", detail: "LLM task & insight extraction.", icon: "⬢" },
    { label: "Connect", detail: "Semantic linking in Vector DB.", icon: "⬡" },
  ];

  const trail = useTrail(steps.length, {
    opacity: isInView ? 1 : 0,
    y: isInView ? 0 : 20,
    config: springConfig.stiff,
  });

  // Waveform animation
  const wavePoints = [10, 30, 15, 45, 20, 55, 10, 35, 25, 50, 20];

  return (
    <section
      ref={ref}
      style={{
        background: "#000",
        padding: "140px 2rem",
        borderTop: "1px solid rgba(255,255,255,0.06)",
        position: "relative",
        overflow: "hidden",
      }}
    >
      <div style={{ maxWidth: 1100, margin: "0 auto" }}>
        <div style={{ textAlign: "center", marginBottom: 80 }}>
          <motion.p
            initial={{ opacity: 0 }}
            animate={isInView ? { opacity: 1 } : {}}
            style={{ fontSize: 12, letterSpacing: "0.2em", textTransform: "uppercase", color: "rgba(255,255,255,0.4)", marginBottom: 16 }}
          >
            The Cognitive Engine
          </motion.p>
          <motion.h2
            initial={{ opacity: 0, scale: 0.95 }}
            animate={isInView ? { opacity: 1, scale: 1 } : {}}
            style={{ fontSize: "clamp(32px, 5vw, 64px)", fontWeight: 900, letterSpacing: "-0.04em", color: "#fff" }}
          >
            Speech to Structure.
          </motion.h2>
        </div>

        {/* Dynamic Waveform Visualization */}
        <div style={{ position: "relative", height: 120, marginBottom: 60, display: "flex", alignItems: "center", justifyContent: "center", gap: 6 }}>
          {wavePoints.map((h, i) => (
            <motion.div
              key={i}
              initial={{ height: 4 }}
              animate={isInView ? { height: [h, h * 0.6, h] } : {}}
              transition={{ repeat: Infinity, duration: 1 + i * 0.1, ease: "easeInOut" }}
              style={{
                width: 4,
                background: "linear-gradient(to bottom, transparent, #fff, transparent)",
                borderRadius: 2,
                opacity: 0.3,
              }}
            />
          ))}
          <div style={{ position: "absolute", width: "100%", height: "1px", background: "linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent)", top: "50%" }} />
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: 1 }}>
          {trail.map((style: any, i: number) => (
            <animated.div
              key={i}
              style={{
                ...style,
                background: "rgba(255,255,255,0.02)",
                border: "1px solid rgba(255,255,255,0.05)",
                padding: "40px 24px",
                position: "relative",
                transition: "background 0.3s",
              }}
              onMouseEnter={(e: any) => e.currentTarget.style.background = "rgba(255,255,255,0.05)"}
              onMouseLeave={(e: any) => e.currentTarget.style.background = "rgba(255,255,255,0.02)"}
            >
              <div style={{ fontSize: 10, fontWeight: 700, color: "rgba(255,255,255,0.2)", marginBottom: 20 }}>0{i+1}</div>
              <div style={{ fontSize: 24, marginBottom: 12, color: "#fff" }}>{steps[i].icon}</div>
              <h3 style={{ fontSize: 17, fontWeight: 700, color: "#fff", marginBottom: 8, letterSpacing: "-0.02em" }}>{steps[i].label}</h3>
              <p style={{ fontSize: 13, color: "rgba(255,255,255,0.4)", lineHeight: 1.6 }}>{steps[i].detail}</p>
              
              {i < steps.length - 1 && (
                <div style={{ position: "absolute", right: -12, top: "50%", transform: "translateY(-50%)", zIndex: 5, color: "rgba(255,255,255,0.1)", fontSize: 24 }}>
                   ›
                </div>
              )}
            </animated.div>
          ))}
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

          {/* Main Device Body (SVG) */}
          <motion.div
            animate={isInView ? { opacity: 1, scale: 1 } : { opacity: 0, scale: 0.9 }}
            transition={{ duration: 1.2, ease: [0.22, 1, 0.36, 1] }}
            style={{ width: 280, height: 280, position: "relative" }}
          >
            <svg viewBox="0 0 200 200" style={{ width: "100%", height: "100%", filter: "drop-shadow(0 0 30px rgba(255,255,255,0.05))" }}>
              <motion.rect 
                x="40" y="40" width="120" height="120" rx="20" 
                fill="none" stroke="rgba(255,255,255,0.15)" strokeWidth="0.5" 
                initial={{ pathLength: 0 }}
                animate={isInView ? { pathLength: 1 } : {}}
                transition={{ duration: 2 }}
              />
              <motion.circle 
                cx="100" cy="100" r="40" 
                fill="none" stroke="rgba(255,255,255,0.3)" strokeWidth="0.5" 
                initial={{ pathLength: 0 }}
                animate={isInView ? { pathLength: 1 } : {}}
                transition={{ duration: 2, delay: 0.5 }}
              />
              {/* Internal components logic */}
              <rect x="70" y="70" width="15" height="15" fill="rgba(255,255,255,0.05)" stroke="rgba(255,255,255,0.2)" strokeWidth="0.2" />
              <rect x="115" y="70" width="15" height="15" fill="rgba(255,255,255,0.05)" stroke="rgba(255,255,255,0.2)" strokeWidth="0.2" />
            </svg>

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
    { title: "Knowledge Graphs", desc: "Connects thoughts over time. See how your ideas evolve and relate.", tag: "Memory" },
    { title: "Smart Reminders", desc: "Detects tasks automatically. \"Finish the report by Thursday\" → calendar entry.", tag: "Action" },
    { title: "Daily Intelligence", desc: "A condensed summary of your messy talks and decisions every evening.", tag: "Insight" },
    { title: "Semantic Search", desc: "Ask \"What did I discuss with the investor?\" and get an actual answer.", tag: "Recall" },
    { title: "Privacy First", desc: "No human review. Full encryption in transit. Data deleted after processing.", tag: "Trust" },
    { title: "Team Memory", desc: "Shared cognitive layers for meetings. Insights across your entire team.", tag: "Collab" },
  ];

  const trail = useTrail(features.length, {
    opacity: isInView ? 1 : 0,
    y: isInView ? 0 : 30,
    config: { tension: 160, friction: 20 },
    delay: isInView ? 100 : 0,
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
          style={{ marginBottom: 60 }}
        >
          <p style={{ fontSize: 11, letterSpacing: "0.15em", textTransform: "uppercase", color: "rgba(255,255,255,0.3)", marginBottom: 12 }}>
            Features
          </p>
          <h2 style={{ fontSize: "clamp(28px, 4vw, 48px)", fontWeight: 800, letterSpacing: "-0.04em", color: "#fff", maxWidth: 500 }}>
            Intelligence, not just storage.
          </h2>
        </motion.div>

        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))",
            gap: 1,
            background: "rgba(255,255,255,0.06)",
            border: "1px solid rgba(255,255,255,0.06)",
          }}
        >
          {trail.map((style: any, i: number) => (
            <animated.div key={i} style={style}>
              <motion.div
                whileHover={{ background: "rgba(255,255,255,0.04)" }}
                style={{ padding: 28, background: "#0a0a0a", transition: "background 0.2s", cursor: "default" }}
              >
                <div
                  style={{
                    display: "inline-block",
                    fontSize: 10,
                    fontWeight: 600,
                    letterSpacing: "0.1em",
                    textTransform: "uppercase",
                    color: "rgba(255,255,255,0.35)",
                    border: "1px solid rgba(255,255,255,0.1)",
                    borderRadius: 4,
                    padding: "3px 8px",
                    marginBottom: 16,
                  }}
                >
                  {features[i].tag}
                </div>
                <p style={{ fontSize: 16, fontWeight: 700, color: "#fff", marginBottom: 8, letterSpacing: "-0.02em" }}>
                  {features[i].title}
                </p>
                <p style={{ fontSize: 13, color: "rgba(255,255,255,0.4)", lineHeight: 1.65 }}>
                  {features[i].desc}
                </p>
              </motion.div>
            </animated.div>
          ))}
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
        borderTop: "1px solid rgba(255,255,255,0.06)",
        padding: "32px 2.5rem",
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        flexWrap: "wrap",
        gap: 16,
      }}
    >
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontWeight: 800, fontSize: 16, letterSpacing: "-0.04em", color: "#fff" }}>SecondMind</span>
      </div>
      <p style={{ fontSize: 12, color: "rgba(255,255,255,0.2)" }}>© 2025 SecondMind. All rights reserved.</p>
      <div style={{ display: "flex", gap: 24 }}>
        {[
          { name: "Privacy", href: "#" },
          { name: "Terms", href: "#" },
          { name: "Contact", href: "#" }
        ].map((l) => (
          <a key={l.name} href={l.href} style={{ fontSize: 12, color: "rgba(255,255,255,0.3)", transition: "color 0.2s" }} onMouseEnter={(e) => (e.target as HTMLElement).style.color = "#fff"} onMouseLeave={(e) => (e.target as HTMLElement).style.color = "rgba(255,255,255,0.3)"}>
            {l.name}
          </a>
        ))}
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
