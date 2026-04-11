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
    background: scrolled ? "rgba(0,0,0,0.92)" : "rgba(0,0,0,0)",
    borderBottom: scrolled
      ? "1px solid rgba(255,255,255,0.1)"
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
        padding: "1rem 2.5rem",
        display: "flex",
        alignItems: "center",
        justifyContent: "space-between",
        backdropFilter: "blur(14px)",
      }}
    >
      <motion.div
        initial={{ opacity: 0, x: -20 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.6 }}
        style={{ display: "flex", alignItems: "center", gap: 10 }}
      >
    
        <span
          style={{
            fontWeight: 700,
            fontSize: 18,
            letterSpacing: "-0.03em",
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
        {["How it works", "Features", "Vision"].map((l) => (
          <a
            key={l}
            href="#"
            style={{
              color: "rgba(255,255,255,0.55)",
              fontSize: 14,
              fontWeight: 400,
              transition: "color 0.2s",
            }}
            onMouseEnter={(e) => ((e.target as HTMLElement).style.color = "#fff")}
            onMouseLeave={(e) =>
              ((e.target as HTMLElement).style.color = "rgba(255,255,255,0.55)")
            }
          >
            {l}
          </a>
        ))}
        <motion.button
          whileHover={{ scale: 1.04 }}
          whileTap={{ scale: 0.97 }}
          style={{
            background: "#fff",
            color: "#000",
            border: "none",
            borderRadius: 6,
            padding: "8px 20px",
            fontSize: 13,
            fontWeight: 600,
            cursor: "pointer",
            letterSpacing: "-0.01em",
          }}
        >
          Get early access
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
  const isInView = useInView(ref, { once: true, margin: "-80px" });

  const steps = [
    { label: "Capture", detail: "ESP32-S3 wearable. Tap-to-record via BLE microphone.", icon: "⬡" },
    { label: "Reconstruct", detail: "Raw audio → WAV (16kHz) pipeline.", icon: "⬢" },
    { label: "Transcribe", detail: "Whisper / Deepgram high-accuracy STT.", icon: "⬡" },
    { label: "Understand", detail: "LLM: task extraction, idea detection, summarization.", icon: "⬢" },
    { label: "Structure", detail: "Vector DB for semantic search and recall.", icon: "⬡" },
  ];

  const trail = useTrail(steps.length, {
    opacity: isInView ? 1 : 0,
    x: isInView ? 0 : 30,
    config: { tension: 180, friction: 22 },
  });

  return (
    <section
      ref={ref}
      style={{
        background: "#000",
        padding: "120px 2rem",
        borderTop: "1px solid rgba(255,255,255,0.06)",
      }}
    >
      <div style={{ maxWidth: 1000, margin: "0 auto" }}>
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6 }}
          style={{ marginBottom: 60, textAlign: "center" }}
        >
          <p style={{ fontSize: 11, letterSpacing: "0.15em", textTransform: "uppercase", color: "rgba(255,255,255,0.3)", marginBottom: 12 }}>
            The Cognitive Pipeline
          </p>
          <h2 style={{ fontSize: "clamp(28px, 4vw, 48px)", fontWeight: 800, letterSpacing: "-0.04em", color: "#fff" }}>
            Speech to Structure
          </h2>
        </motion.div>

        <div
          style={{
            display: "flex",
            alignItems: "stretch",
            gap: 0,
            position: "relative",
            overflowX: "auto",
            paddingBottom: 8,
          }}
        >
          {trail.map((style: any, i: number) => (
            <animated.div key={i} style={{ ...style, flex: "1 1 0", minWidth: 140 }}>
              <div
                style={{
                  position: "relative",
                  padding: "28px 20px",
                  background: i % 2 === 0 ? "#111" : "#0d0d0d",
                  border: "1px solid rgba(255,255,255,0.07)",
                  borderLeft: i > 0 ? "none" : "1px solid rgba(255,255,255,0.07)",
                  display: "flex",
                  flexDirection: "column",
                  gap: 12,
                  height: "100%",
                }}
              >
                <div style={{ fontSize: 11, color: "rgba(255,255,255,0.2)", fontWeight: 600, letterSpacing: "0.1em" }}>
                  0{i + 1}
                </div>
                <div style={{ fontSize: 20, color: "rgba(255,255,255,0.3)" }}>{steps[i].icon}</div>
                <p style={{ fontSize: 15, fontWeight: 700, color: "#fff", letterSpacing: "-0.02em" }}>
                  {steps[i].label}
                </p>
                <p style={{ fontSize: 12, color: "rgba(255,255,255,0.35)", lineHeight: 1.6 }}>
                  {steps[i].detail}
                </p>
                {i < steps.length - 1 && (
                  <div
                    style={{
                      position: "absolute",
                      right: -10,
                      top: "50%",
                      transform: "translateY(-50%)",
                      zIndex: 2,
                      width: 18,
                      height: 18,
                      background: "#000",
                      border: "1px solid rgba(255,255,255,0.12)",
                      borderRadius: 2,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: 10,
                      color: "rgba(255,255,255,0.4)",
                    }}
                  >
                    →
                  </div>
                )}
              </div>
            </animated.div>
          ))}
        </div>
      </div>
    </section>
  );
}

function DeviceSection() {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-80px" });
  const { scrollYProgress } = useScroll({ target: ref, offset: ["start end", "end start"] });
  const yFast = useTransform(scrollYProgress, [0, 1], [40, -40]);
  const ySlow = useTransform(scrollYProgress, [0, 1], [20, -20]);
  const descOpacity = useTransform(scrollYProgress, [0, 0.3, 0.7, 1], [0, 1, 1, 0]);
  const descY = useTransform(scrollYProgress, [0, 0.3, 0.7, 1], [40, 0, 0, -40]);

  const nodes = [
    { angle: 0, label: "BLE", delay: 0.2, description: "Wireless streaming", detail: "Seamless Bluetooth Low Energy connection enables real-time audio streaming with minimal power consumption, perfect for all-day wear." },
    { angle: 72, label: "MIC", delay: 0.35, description: "MEMS microphone", detail: "High-quality noise-canceling microphone captures crystal-clear audio even in noisy environments." },
    { angle: 144, label: "TAP", delay: 0.5, description: "Tap interface", detail: "Detect multi-tap gestures for intuitive control without requiring a dedicated button." },
    { angle: 216, label: "PROC", delay: 0.65, description: "Processing", detail: "Dual-core processor handles audio encoding and device logic simultaneously with ultra-low latency." },
    { angle: 288, label: "ENC", delay: 0.8, description: "End-to-end encryption", detail: "Military-grade encryption ensures all audio data is protected throughout transmission and processing." },
  ];

  const [hoveredNode, setHoveredNode] = useState<number | null>(null);

  return (
    <section
      ref={ref}
      style={{
        background: "#0a0a0a",
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
        {/* Device Diagram */}
        <div style={{ position: "relative", height: 360, display: "flex", alignItems: "center", justifyContent: "center" }}>
          <motion.div style={{ position: "absolute", width: 320, height: 320, borderRadius: "50%", border: "1px solid rgba(255,255,255,0.04)", y: ySlow }} />
          <motion.div style={{ position: "absolute", width: 230, height: 230, borderRadius: "50%", border: "1px solid rgba(255,255,255,0.07)", y: yFast }} />
          <motion.div style={{ position: "absolute", width: 150, height: 150, borderRadius: "50%", border: "1px solid rgba(255,255,255,0.12)", y: ySlow }} />

          {/* Core */}
          <motion.div
            animate={isInView ? { scale: [0.9, 1.05, 1], opacity: [0, 1] } : {}}
            transition={{ duration: 1, ease: [0.22, 1, 0.36, 1] }}
            style={{
              width: 90,
              height: 90,
              borderRadius: "50%",
              background: "#111",
              border: "1px solid rgba(255,255,255,0.2)",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              flexDirection: "column",
              gap: 4,
              zIndex: 2,
            }}
          >
            <motion.div
              animate={{ scale: [1, 1.3, 1], opacity: [0.8, 0.4, 0.8] }}
              transition={{ repeat: Infinity, duration: 2.2, ease: "easeInOut" }}
              style={{ width: 10, height: 10, borderRadius: "50%", background: "#fff" }}
            />
            <p style={{ fontSize: 8, color: "rgba(255,255,255,0.3)", letterSpacing: "0.08em", textTransform: "uppercase" }}>
              ESP32-S3
            </p>
          </motion.div>

          {/* Orbital nodes */}
          {nodes.map(({ angle, label, delay }, i) => {
            const rad = (angle * Math.PI) / 180;
            const x = Math.cos(rad) * 110;
            const y = Math.sin(rad) * 110;
            return (
              <motion.div
                key={i}
                initial={{ opacity: 0, scale: 0 }}
                animate={isInView ? { opacity: 1, scale: 1 } : {}}
                transition={{ delay, duration: 0.5 }}
                onHoverStart={() => setHoveredNode(i)}
                onHoverEnd={() => setHoveredNode(null)}
                style={{
                  position: "absolute",
                  left: `calc(50% + ${x}px - 18px)`,
                  top: `calc(50% + ${y}px - 18px)`,
                  width: 36,
                  height: 36,
                  borderRadius: 6,
                  background: hoveredNode === i ? "rgba(255,255,255,0.1)" : "#111",
                  border: hoveredNode === i ? "1px solid rgba(255,255,255,0.4)" : "1px solid rgba(255,255,255,0.15)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 8,
                  color: hoveredNode === i ? "rgba(255,255,255,0.9)" : "rgba(255,255,255,0.5)",
                  fontWeight: 700,
                  letterSpacing: "0.05em",
                  zIndex: 2,
                  cursor: "pointer",
                  transition: "all 0.2s",
                }}
              >
                {label}
              </motion.div>
            );
          })}
        </div>

        {/* Copy with Parallax Descriptions */}
        <motion.div
          initial={{ opacity: 0, x: 30 }}
          animate={isInView ? { opacity: 1, x: 0 } : {}}
          transition={{ duration: 0.7 }}
        >
          <p style={{ fontSize: 11, letterSpacing: "0.15em", textTransform: "uppercase", color: "rgba(255,255,255,0.3)", marginBottom: 16 }}>
            The Device
          </p>
          <h2 style={{ fontSize: "clamp(24px, 3.5vw, 40px)", fontWeight: 800, letterSpacing: "-0.04em", lineHeight: 1.15, color: "#fff", marginBottom: 20 }}>
            Minimal input.
            <br />
            Maximum intelligence.
          </h2>
          <p style={{ fontSize: 15, color: "rgba(255,255,255,0.4)", lineHeight: 1.7, marginBottom: 28 }}>
            The ESP32-S3 wearable is designed for frictionless capture. A single tap starts recording. BLE streams audio to your phone. The device disappears — your thoughts don't.
          </p>

          {/* Parallax Feature Descriptions - Hover to reveal */}
          <div style={{ position: "relative", height: 60, marginBottom: 28 }}>
            <motion.div style={{ opacity: descOpacity, y: descY, position: "absolute", left: 0, right: 0, pointerEvents: "none" }}>
              {hoveredNode !== null && (
                <div>
                  <p style={{ fontSize: 12, letterSpacing: "0.1em", textTransform: "uppercase", color: "rgba(255,255,255,0.4)", marginBottom: 8 }}>
                    {nodes[hoveredNode].description}
                  </p>
                  <p style={{ fontSize: 13, color: "rgba(255,255,255,0.5)", lineHeight: 1.6 }}>
                    {nodes[hoveredNode].detail}
                  </p>
                </div>
              )}
            </motion.div>
          </div>

          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            {[
              ["Processor", "ESP32-S3 dual-core"],
              ["Connection", "Bluetooth Low Energy"],
              ["Input", "Tap-to-record"],
              ["Audio", "16kHz WAV capture"],
            ].map(([k, v]) => (
              <div
                key={k}
                style={{
                  display: "flex",
                  justifyContent: "space-between",
                  fontSize: 13,
                  paddingBottom: 10,
                  borderBottom: "1px solid rgba(255,255,255,0.06)",
                }}
              >
                <span style={{ color: "rgba(255,255,255,0.3)" }}>{k}</span>
                <span style={{ color: "#fff", fontWeight: 500 }}>{v}</span>
              </div>
            ))}
          </div>
        </motion.div>
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
              link.href = "/secondmind.apk"; // Place your APK file in the public folder
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
        
        <span style={{ fontWeight: 700, fontSize: 14, letterSpacing: "-0.02em", color: "#fff" }}>SecondMind</span>
      </div>
      <p style={{ fontSize: 12, color: "rgba(255,255,255,0.2)" }}>© 2025 SecondMind. All rights reserved.</p>
      <div style={{ display: "flex", gap: 24 }}>
        {["Privacy", "Terms", "Contact"].map((l) => (
          <a key={l} href="#" style={{ fontSize: 12, color: "rgba(255,255,255,0.3)" }}>
            {l}
          </a>
        ))}
      </div>
    </footer>
  );
}
export default function App() {
  useEffect(() => {
    const style = document.createElement("style");
    style.textContent = globalCSS;
    document.head.appendChild(style);
    return () => {
      document.head.removeChild(style);
    };
  }, []);

  return (
    <div style={{ background: "#000", minHeight: "100vh" }}>
      <Nav />
      <Hero />
      <ProblemSection />
      <PipelineSection />
      <DeviceSection />
      <FeaturesSection />
      <VisionSection />
      <CTA />
      <Footer />
    </div>
  );
}