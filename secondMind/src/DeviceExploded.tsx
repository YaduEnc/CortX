import React, { useRef, useMemo, useEffect } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Environment, RoundedBox, useTexture, Decal, MeshTransmissionMaterial } from "@react-three/drei";
import * as THREE from "three";
import { motion, useScroll, useTransform } from "framer-motion";

// Tool: Procedurally generates a microscopic noise texture for the Anodized Aluminum / Polycarbonate matte finish
function createNoiseNormalMap() {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 512;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  const imgData = ctx.createImageData(512, 512);
  for (let i = 0; i < imgData.data.length; i += 4) {
    imgData.data[i] = 127 + (Math.random() - 0.5) * 80;
    imgData.data[i+1] = 127 + (Math.random() - 0.5) * 80;
    imgData.data[i+2] = 255;
    imgData.data[i+3] = 255;
  }
  ctx.putImageData(imgData, 0, 0);
  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  return texture;
}

// Tool: Procedurally generates metallic copper traces for the PCB board normal map
function createPCBTraceMap() {
  const canvas = document.createElement("canvas");
  canvas.width = 1024;
  canvas.height = 1024;
  const ctx = canvas.getContext("2d");
  if (!ctx) return null;
  ctx.fillStyle = "#8080ff";
  ctx.fillRect(0,0,1024,1024);
  
  ctx.strokeStyle = "#ffb0b0";
  ctx.lineWidth = 6;
  ctx.lineJoin = "bevel";
  for (let i = 0; i < 250; i++) {
     ctx.beginPath();
     let x = Math.random() * 1024;
     let y = Math.random() * 1024;
     ctx.moveTo(x,y);
     for(let j = 0; j < 5; j++) {
        if (Math.random() > 0.5) x += (Math.random() > 0.5 ? 40 : -40);
        else y += (Math.random() > 0.5 ? 40 : -40);
        ctx.lineTo(x,y);
     }
     ctx.stroke();
  }
  const texture = new THREE.CanvasTexture(canvas);
  return texture;
}

function DetailedDeviceModel({ scrollRef }: { scrollRef: React.MutableRefObject<number> }) {
  const group = useRef<THREE.Group>(null);
  
  const shellRef = useRef<THREE.Group>(null);
  const pcbRef = useRef<THREE.Group>(null);
  const batteryRef = useRef<THREE.Group>(null);
  const ledRef = useRef<THREE.MeshStandardMaterial>(null);

  const logoTexture = useTexture("/logo.png");

  const noiseMap = useMemo(() => createNoiseNormalMap() as THREE.CanvasTexture, []);
  const pcbMap = useMemo(() => createPCBTraceMap() as THREE.CanvasTexture, []);

  useFrame((state) => {
    if (!group.current) return;
    
    // Fetch directly from the native DOM-bridged scroll tracker!
    const t = scrollRef.current;

    if (ledRef.current) {
      ledRef.current.emissiveIntensity = 1.0 + Math.sin(state.clock.elapsedTime * 6) * 0.8;
    }

    const explodePhase = Math.min(1, Math.max(0, (t - 0.1) / 0.2));
    const inspectPcbPhase = Math.min(1, Math.max(0, (t - 0.4) / 0.2));
    const inspectBatPhase = Math.min(1, Math.max(0, (t - 0.7) / 0.2));

    group.current.rotation.y = THREE.MathUtils.lerp(0.8, Math.PI * 2.1, explodePhase) - THREE.MathUtils.lerp(0, 0.4, inspectPcbPhase) + THREE.MathUtils.lerp(0, 0.8, inspectBatPhase);
    group.current.rotation.x = THREE.MathUtils.lerp(0.2, 0, explodePhase);

    if (shellRef.current) {
       shellRef.current.position.z = THREE.MathUtils.lerp(0, 3.5, explodePhase);
       shellRef.current.children.forEach(child => {
         if ((child as THREE.Mesh).material) {
             const mat = (child as THREE.Mesh).material as THREE.Material;
             if (mat.transparent) mat.opacity = THREE.MathUtils.lerp(1, 0.05, explodePhase);
         }
       });
    }

    if (pcbRef.current) {
       pcbRef.current.position.z = THREE.MathUtils.lerp(0, 1.0, explodePhase) + THREE.MathUtils.lerp(0, 1.5, inspectPcbPhase);
       pcbRef.current.position.x = THREE.MathUtils.lerp(0, -1.2, inspectPcbPhase);
    }

    if (batteryRef.current) {
       batteryRef.current.position.z = THREE.MathUtils.lerp(0, -1.5, explodePhase);
       batteryRef.current.position.z = THREE.MathUtils.lerp(-1.5, 2.0, inspectBatPhase);
       batteryRef.current.position.x = THREE.MathUtils.lerp(0, 1.2, inspectBatPhase);
       batteryRef.current.rotation.y = THREE.MathUtils.lerp(0, -0.6, inspectBatPhase);
    }
  });

  return (
    <group ref={group} dispose={null}>
      
      {/* ================= OUTER SHELL (Sealed 2-part chassis with real shadows) ================= */}
      <group ref={shellRef} position={[0, 0, 0.2]}>
        
        {/* Core filler to prevent the seam from being empty hollow space */}
        <mesh position={[0, 0, 0]}>
          <boxGeometry args={[1.75, 3.75, 0.17]} />
          <meshBasicMaterial color="#020202" />
        </mesh>

        <RoundedBox args={[1.8, 3.8, 0.17]} radius={0.15} smoothness={4} position={[0, 0, 0.086]}>
          <meshPhysicalMaterial 
            color="#080808" roughness={0.8} metalness={0.4} clearcoat={0.15} transparent opacity={1}
            normalMap={noiseMap} normalScale={new THREE.Vector2(0.3, 0.3)} depthWrite={false}
          />
          
          <Decal position={[0, 0.2, 0.086]} rotation={[0, 0, 0]} scale={0.45}>
            <meshStandardMaterial map={logoTexture} transparent opacity={1} emissive="#fff" emissiveMap={logoTexture} emissiveIntensity={2.5} depthTest={true} />
          </Decal>

          {/* Fixed Glass: Standard physical material prevents heavily glitchy refractive samples on certain GPUs */}
          <mesh position={[0, 0.2, 0.088]}>
             <planeGeometry args={[0.55, 0.55]} />
             <meshPhysicalMaterial 
               roughness={0.4} metalness={0.1} clearcoat={1.0} color="#ffffff" transparent opacity={0.1}
             />
          </mesh>

          {[-0.78, 0.78].map((x) => 
            [-1.78, 1.78].map((y) => (
              <mesh key={`screw-${x}-${y}`} position={[x, y, 0.085]} rotation={[Math.PI/2, 0, 0]}>
                <cylinderGeometry args={[0.025, 0.025, 0.02, 16]} />
                <meshStandardMaterial color="#222" metalness={0.9} roughness={0.2} />
                <mesh position={[0, 0.011, 0]}>
                   <circleGeometry args={[0.015, 6]} />
                   <meshBasicMaterial color="#050505" />
                </mesh>
              </mesh>
            ))
          )}
        </RoundedBox>

        <RoundedBox args={[1.8, 3.8, 0.17]} radius={0.15} smoothness={4} position={[0, 0, -0.086]}>
          <meshPhysicalMaterial 
            color="#080808" roughness={0.8} metalness={0.4} clearcoat={0.15} transparent opacity={1}
            normalMap={noiseMap} normalScale={new THREE.Vector2(0.3, 0.3)} depthWrite={false}
          />
        </RoundedBox>

        <mesh position={[0, 1.95, 0]}>
          <boxGeometry args={[0.3, 0.2, 0.15]} />
          <meshStandardMaterial color="#0A0A0A" />
        </mesh>

        <mesh position={[0.92, 0.5, 0]}>
           <boxGeometry args={[0.06, 0.6, 0.12]} />
           <meshStandardMaterial color="#111" roughness={0.2} metalness={0.9} clearcoat={1.0} />
        </mesh>

        <mesh position={[-0.6, 1.5, 0.18]} rotation={[Math.PI/2, 0, 0]}>
           <cylinderGeometry args={[0.03, 0.03, 0.1, 16]} />
           <meshBasicMaterial color="#000" />
        </mesh>
        <mesh position={[-0.6, 1.3, 0.18]} rotation={[Math.PI/2, 0, 0]}>
           <cylinderGeometry args={[0.015, 0.015, 0.1, 16]} />
           <meshStandardMaterial ref={ledRef} color="#fff" emissive="#4CAF50" emissiveIntensity={1} />
        </mesh>
      </group>

      {/* ================= INTERNAL PCB (ESP32-S3 Logic Board) ================= */}
      <group ref={pcbRef} position={[0, 0, 0]}>
        <RoundedBox args={[1.6, 3.4, 0.04]} radius={0.05}>
          <meshStandardMaterial color="#0B2615" roughness={0.7} metalness={0.4} normalMap={pcbMap} normalScale={new THREE.Vector2(1.2, 1.2)} />
        </RoundedBox>

        <RoundedBox args={[0.6, 0.8, 0.08]} radius={0.02} position={[0, 0.6, 0.04]}>
          <meshStandardMaterial color="#c0c0c0" roughness={0.3} metalness={0.9} clearcoat={0.5} />
        </RoundedBox>

        <mesh position={[0, -0.4, 0.03]}>
           <boxGeometry args={[0.4, 0.4, 0.04]} />
           <meshStandardMaterial color="#111" roughness={0.2} metalness={0.9} />
        </mesh>

        {[-0.5, 0.5].map(x => (
          <mesh key={`mic-${x}`} position={[x, 1.4, 0.04]}>
             <boxGeometry args={[0.12, 0.12, 0.06]} />
             <meshStandardMaterial color="#d4af37" metalness={1} roughness={0.2} clearcoat={1} />
             <mesh position={[0, 0, 0.031]}>
                <circleGeometry args={[0.02, 16]} />
                <meshBasicMaterial color="#000" />
             </mesh>
          </mesh>
        ))}
      </group>

      {/* ================= HIGH-DENSITY LIPO BATTERY ================= */}
      <group ref={batteryRef} position={[0, 0, -0.15]}>
        <RoundedBox args={[1.5, 2.6, 0.2]} radius={0.02}>
          <meshStandardMaterial color="#c0c0c0" roughness={0.4} metalness={0.8} />
        </RoundedBox>
        <mesh position={[0, 0, 0.101]}>
          <planeGeometry args={[1.2, 1.8]} />
          <meshStandardMaterial color="#111" roughness={0.8} />
        </mesh>
      </group>
    </group>
  );
}

export function DeviceExploded() {
  const containerRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef(0);
  
  // Bridging DOM Scroll directly via Framer Motion
  const { scrollYProgress } = useScroll({
    target: containerRef,
    offset: ["start start", "end end"]
  });

  useEffect(() => {
    const unsub = scrollYProgress.on("change", (latest) => {
       scrollRef.current = latest;
    });
    return unsub;
  }, [scrollYProgress]);

  // Transform overlays securely based purely on the global scroll
  // Map tightly controlled exclusive windows to prevent any overlap

  // 1. INTRO: Active 0.0 -> 0.12
  const opacIntro = useTransform(scrollYProgress, [0, 0.05, 0.12], [1, 1, 0]);
  const yIntro = useTransform(scrollYProgress, [0, 0.12], ["0vh", "-15vh"]);

  // 2. CORE (ESP32): Active 0.15 -> 0.38
  const opacCore = useTransform(scrollYProgress, [0.15, 0.22, 0.33, 0.38], [0, 1, 1, 0]);
  const yCore = useTransform(scrollYProgress, [0.15, 0.38], ["15vh", "-15vh"]);

  // 3. MEMS (Audio): Active 0.42 -> 0.65
  const opacMems = useTransform(scrollYProgress, [0.42, 0.48, 0.58, 0.65], [0, 1, 1, 0]);
  const yMems = useTransform(scrollYProgress, [0.42, 0.65], ["15vh", "-15vh"]);

  // 4. BATTERY: Active 0.68 -> 1.0
  const opacBattery = useTransform(scrollYProgress, [0.68, 0.75, 0.95, 1.0], [0, 1, 1, 0]);
  const yBattery = useTransform(scrollYProgress, [0.68, 1.0], ["15vh", "-5vh"]);

  return (
    <section ref={containerRef} style={{ height: "400vh", position: "relative", zIndex: 5 }}>
      <div style={{ position: "sticky", top: 0, height: "100vh", width: "100%", display: "flex", alignItems: "center", overflow: "hidden" }}>
        
        {/* Glow backdrop tailored to the hardware */}
        <div style={{ position: "absolute", inset: 0, background: "radial-gradient(circle at 50% 50%, rgba(255,255,255,0.03) 0%, transparent 60%)", pointerEvents: "none", zIndex: 0 }} />

        {/* 100% Native Absolute DOM Overlays driven by Framer Motion. Fixes trapped iframe scroll! */}
        <div style={{ position: "absolute", inset: 0, zIndex: 10, pointerEvents: "none" }}>
            
            <motion.div style={{ opacity: opacIntro, y: yIntro, position: "absolute", top: "20vh", width: "100%", textAlign: "center" }}>
              <p style={{ fontSize: 13, letterSpacing: "0.2em", textTransform: "uppercase", color: "#4CAF50", marginBottom: 12 }}>Wearable Intelligence</p>
              <h2 style={{ fontSize: "clamp(36px, 6vw, 76px)", fontWeight: 900, color: "#fff", letterSpacing: "-0.04em", lineHeight: 1 }}>Frictionless Capture.</h2>
            </motion.div>

            <motion.div style={{ opacity: opacCore, y: yCore, position: "absolute", top: "40vh", right: "10vw", width: "340px" }}>
              <div style={{ padding: "8px 16px", background: "rgba(255,255,255,0.05)", display: "inline-block", borderRadius: 100, border: "1px solid rgba(255,255,255,0.1)", marginBottom: 16 }}>
                 <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", color: "#fff" }}>ESP32-S3 ARCHITECTURE</span>
              </div>
              <h3 style={{ fontSize: 32, fontWeight: 800, color: "#fff", marginBottom: 16, letterSpacing: "-0.02em" }}>Edge Intelligence.</h3>
              <p style={{ color: "rgba(255,255,255,0.5)", fontSize: 15, lineHeight: 1.6 }}>By processing Voice Activity Detection (VAD) completely locally on the ESP32-S3 neural coprocessor, the device bypasses the latency of constant cloud pinging.</p>
            </motion.div>

            <motion.div style={{ opacity: opacMems, y: yMems, position: "absolute", top: "45vh", right: "10vw", width: "340px" }}>
              <h3 style={{ fontSize: 24, fontWeight: 800, color: "#fff", marginBottom: 12, letterSpacing: "-0.02em" }}>Acoustic Precision.</h3>
              <p style={{ color: "rgba(255,255,255,0.5)", fontSize: 15, lineHeight: 1.6 }}>Using an advanced dual-MEMS microphone array, ambient chaos is filtered out at the hardware level. Only perfectly clean semantic intent reaches the network layer.</p>
            </motion.div>

            <motion.div style={{ opacity: opacBattery, y: yBattery, position: "absolute", top: "45vh", left: "10vw", width: "340px" }}>
              <div style={{ padding: "8px 16px", background: "rgba(76, 175, 80, 0.1)", display: "inline-block", borderRadius: 100, border: "1px solid rgba(76, 175, 80, 0.3)", marginBottom: 16 }}>
                 <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", color: "#4CAF50" }}>ULTRA-LOW POWER</span>
              </div>
              <h3 style={{ fontSize: 32, fontWeight: 800, color: "#fff", marginBottom: 16, letterSpacing: "-0.02em" }}>Multi-Day Battery.</h3>
              <p style={{ color: "rgba(255,255,255,0.5)", fontSize: 15, lineHeight: 1.6 }}>Optimized sleep states combined with a high-density lithium-polymer cell means you can wear CortX endlessly without battery anxiety.</p>
            </motion.div>

        </div>

        <Canvas camera={{ position: [0, 0, 8.5], fov: 45 }} gl={{ antialias: true, alpha: true }} style={{ zIndex: 5 }}>
          <ambientLight intensity={0.2} />
          <spotLight position={[-10, 10, -5]} intensity={3} angle={0.5} penumbra={1} color="#ffddcc" />
          <directionalLight position={[10, 5, -10]} intensity={6} color="#e0f0ff" />
          <directionalLight position={[-10, -5, 5]} intensity={2} color="#ffffff" />
          <Environment preset="studio" />
          
          {/* Injected the global scroll reference */}
          <DetailedDeviceModel scrollRef={scrollRef} />
        </Canvas>

      </div>
    </section>
  );
}
