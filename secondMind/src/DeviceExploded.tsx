import React, { useRef } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Environment, ScrollControls, useScroll, RoundedBox, Cylinder, Scroll, useTexture, Decal } from "@react-three/drei";
import * as THREE from "three";

function DetailedDeviceModel() {
  const scroll = useScroll();
  const group = useRef<THREE.Group>(null);
  
  const shellRef = useRef<THREE.Mesh>(null);
  const pcbRef = useRef<THREE.Group>(null);
  const batteryRef = useRef<THREE.Group>(null);
  const ledRef = useRef<THREE.MeshStandardMaterial>(null);

  // Load logo texture for the shell decal
  const logoTexture = useTexture("/logo.png");

  useFrame((state) => {
    if (!group.current) return;
    const t = scroll.offset; // ranges from 0 to 1 natively, reverses smoothly when scrolling up!

    // Pulse the LED indicator gently
    if (ledRef.current) {
      ledRef.current.emissiveIntensity = 1.5 + Math.sin(state.clock.elapsedTime * 4) * 0.5;
    }

    // Scroll Phase calculations (Normalized 0 to 1 for distinct sections)
    const explodePhase = Math.min(1, Math.max(0, (t - 0.1) / 0.2));        // 0.1 -> 0.3
    const inspectPcbPhase = Math.min(1, Math.max(0, (t - 0.4) / 0.2));    // 0.4 -> 0.6
    const inspectBatPhase = Math.min(1, Math.max(0, (t - 0.7) / 0.2));    // 0.7 -> 0.9

    // Global rotation logic
    // Starts angled, spins to flat, then rotates slightly for inspection
    group.current.rotation.y = THREE.MathUtils.lerp(0.6, Math.PI * 2, explodePhase) - THREE.MathUtils.lerp(0, 0.4, inspectPcbPhase) + THREE.MathUtils.lerp(0, 0.8, inspectBatPhase);
    group.current.rotation.x = THREE.MathUtils.lerp(0.2, 0, explodePhase);

    // 1. Shell Animation
    if (shellRef.current) {
       shellRef.current.position.z = THREE.MathUtils.lerp(0.2, 3.5, explodePhase);
       // Fade out shell to see internals better
       (shellRef.current.material as THREE.Material).opacity = THREE.MathUtils.lerp(1, 0.05, explodePhase);
    }

    // 2. PCB (ESP32 Board) Animation
    if (pcbRef.current) {
       // Float forward
       pcbRef.current.position.z = THREE.MathUtils.lerp(0, 1.0, explodePhase) + THREE.MathUtils.lerp(0, 1.5, inspectPcbPhase);
       // Slide left to make room for text during PCB inspect phase
       pcbRef.current.position.x = THREE.MathUtils.lerp(0, -1.2, inspectPcbPhase);
    }

    // 3. Battery Animation
    if (batteryRef.current) {
       // Push back initially
       batteryRef.current.position.z = THREE.MathUtils.lerp(-0.2, -1.5, explodePhase);
       // Bring forward and slide right during Battery phase
       batteryRef.current.position.z = THREE.MathUtils.lerp(-1.5, 2.0, inspectBatPhase);
       batteryRef.current.position.x = THREE.MathUtils.lerp(0, 1.2, inspectBatPhase);
       batteryRef.current.rotation.y = THREE.MathUtils.lerp(0, -0.5, inspectBatPhase);
    }
  });

  return (
    <group ref={group} dispose={null}>
      
      {/* ================= OUTER SHELL (Accurate to hardware) ================= */}
      <RoundedBox ref={shellRef} args={[1.8, 3.8, 0.35]} radius={0.15} smoothness={4} position={[0, 0, 0.2]}>
        <meshPhysicalMaterial color="#050505" roughness={0.4} metalness={0.7} clearcoat={0.3} transparent depthWrite={false} />
        
        {/* Top Necklace/Lanyard Loop */}
        <mesh position={[0, 1.95, 0]}>
          <boxGeometry args={[0.3, 0.2, 0.15]} />
          <meshStandardMaterial color="#111" />
        </mesh>

        {/* Side Button */}
        <mesh position={[0.92, 0.5, 0]}>
          <boxGeometry args={[0.08, 0.6, 0.15]} />
          <meshStandardMaterial color="#111" roughness={0.6} />
        </mesh>

        {/* Pinhole Mic / Camera top left */}
        <mesh position={[-0.6, 1.5, 0.18]} rotation={[Math.PI/2, 0, 0]}>
          <cylinderGeometry args={[0.04, 0.04, 0.1, 16]} />
          <meshBasicMaterial color="#000" />
        </mesh>

        {/* Status Indicator LED */}
        <mesh position={[-0.6, 1.3, 0.18]} rotation={[Math.PI/2, 0, 0]}>
          <cylinderGeometry args={[0.015, 0.015, 0.1, 16]} />
          <meshStandardMaterial ref={ledRef} color="#fff" emissive="#4CAF50" emissiveIntensity={1} />
        </mesh>

        {/* Glowing Logo Decal */}
        <Decal position={[0, 0.2, 0.18]} rotation={[0, 0, 0]} scale={0.45}>
          <meshStandardMaterial 
            map={logoTexture} 
            transparent 
            opacity={0.9} 
            emissive="#fff" 
            emissiveMap={logoTexture} 
            emissiveIntensity={1.2} 
            depthTest={true} 
            polygonOffset 
            polygonOffsetFactor={-1} 
          />
        </Decal>
      </RoundedBox>

      {/* ================= INTERNAL PCB (ESP32-S3 Logic Board) ================= */}
      <group ref={pcbRef} position={[0, 0, 0]}>
        {/* Main Board */}
        <RoundedBox args={[1.6, 3.4, 0.04]} radius={0.05}>
          <meshStandardMaterial color="#0A2813" roughness={0.9} metalness={0.2} />
        </RoundedBox>

        {/* ESP-S3 Metal Shielding */}
        <RoundedBox args={[0.6, 0.8, 0.08]} radius={0.02} position={[0, 0.6, 0.04]}>
          <meshStandardMaterial color="#a0a0a0" roughness={0.3} metalness={0.9} />
        </RoundedBox>

        {/* Silicon Chip visible on board */}
        <mesh position={[0, -0.4, 0.03]}>
           <boxGeometry args={[0.4, 0.4, 0.04]} />
           <meshStandardMaterial color="#111" roughness={0.4} metalness={0.8} />
        </mesh>

        {/* Gold Pins for S3 Module */}
        {[...Array(10)].map((_, i) => (
          <mesh key={`pinL-${i}`} position={[-0.32, 0.28 + i * 0.07, 0.04]}>
            <boxGeometry args={[0.06, 0.02, 0.02]} />
            <meshStandardMaterial color="#d4af37" metalness={1} roughness={0.2} />
          </mesh>
        ))}
        {[...Array(10)].map((_, i) => (
          <mesh key={`pinR-${i}`} position={[0.32, 0.28 + i * 0.07, 0.04]}>
            <boxGeometry args={[0.06, 0.02, 0.02]} />
            <meshStandardMaterial color="#d4af37" metalness={1} roughness={0.2} />
          </mesh>
        ))}

        {/* High-end Dual MEMS Mics on PCB */}
        <mesh position={[-0.5, 1.4, 0.04]}>
           <boxGeometry args={[0.1, 0.1, 0.06]} />
           <meshStandardMaterial color="#d4af37" metalness={1} roughness={0.1} />
           {/* Pinhole */}
           <mesh position={[0, 0, 0.031]}>
              <circleGeometry args={[0.02, 16]} />
              <meshBasicMaterial color="#000" />
           </mesh>
        </mesh>
        <mesh position={[0.5, 1.4, 0.04]}>
           <boxGeometry args={[0.1, 0.1, 0.06]} />
           <meshStandardMaterial color="#d4af37" metalness={1} roughness={0.1} />
           <mesh position={[0, 0, 0.031]}>
              <circleGeometry args={[0.02, 16]} />
              <meshBasicMaterial color="#000" />
           </mesh>
        </mesh>
        
        {/* Antenna Trace Logic (Gold) */}
        <mesh position={[0, 1.5, 0.021]}>
           <planeGeometry args={[0.8, 0.15]} />
           <meshStandardMaterial map={createAntennaTexture()} transparent />
        </mesh>
      </group>

      {/* ================= HIGH-DENSITY LIPO BATTERY ================= */}
      <group ref={batteryRef} position={[0, 0, -0.15]}>
        {/* Silver Pouch representing modern flat LiPo battery */}
        <RoundedBox args={[1.5, 2.6, 0.2]} radius={0.02}>
          <meshStandardMaterial color="#dcdcdc" roughness={0.6} metalness={0.4} />
        </RoundedBox>
        {/* Battery Label/Tape */}
        <mesh position={[0, 0, 0.101]}>
          <planeGeometry args={[1.2, 1.8]} />
          <meshStandardMaterial color="#1a1a1a" />
        </mesh>
        {/* Connector wires to PCB */}
        <mesh position={[0, 1.35, 0]}>
          <boxGeometry args={[0.1, 0.2, 0.05]} />
          <meshStandardMaterial color="#ffbd59" />
        </mesh>
      </group>

    </group>
  );
}

// Quick helper to draw an abstract squiggly antenna trace
function createAntennaTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 64;
  const ctx = canvas.getContext("2d");
  if (ctx) {
    ctx.strokeStyle = "#d4af37";
    ctx.lineWidth = 12;
    ctx.beginPath();
    ctx.moveTo(10, 32);
    for (let i = 0; i < 6; i++) {
      ctx.lineTo(30 + i * 40, i % 2 === 0 ? 10 : 54);
    }
    ctx.stroke();
  }
  return new THREE.CanvasTexture(canvas);
}

export function DeviceExploded() {
  return (
    <section style={{ height: "400vh", position: "relative", background: "transparent", overflow: "visible", zIndex: 5 }}>
      {/* Sticky container tracking scroll natively */}
      <div style={{ position: "sticky", top: 0, height: "100vh", width: "100%", display: "flex", alignItems: "center" }}>
        
        {/* Glow backdrop tailored to the hardware */}
        <div style={{ position: "absolute", inset: 0, background: "radial-gradient(circle at 50% 50%, rgba(255,255,255,0.03) 0%, transparent 60%)", pointerEvents: "none" }} />

        <Canvas camera={{ position: [0, 0, 8.5], fov: 45 }} gl={{ antialias: true, alpha: true }}>
          <ambientLight intensity={0.4} />
          <spotLight position={[5, 10, 5]} intensity={3} angle={0.3} penumbra={1} distance={40} />
          <spotLight position={[-5, -10, 5]} intensity={1} angle={0.3} penumbra={1} />
          <Environment preset="city" />
          
          {/* ScrollControls captures scroll natively and provides offset to useFrame */}
          <ScrollControls pages={4} damping={0.15}>
            <DetailedDeviceModel />
            
            {/* HTML Overlays synchronized with the scroll phases */}
            <Scroll html style={{ width: "100%", height: "100%" }}>
              
              {/* PAGE 1: Intro */}
              <div style={{ position: "absolute", top: "20vh", width: "100%", textAlign: "center", pointerEvents: "none" }}>
                <p style={{ fontSize: 13, letterSpacing: "0.2em", textTransform: "uppercase", color: "#4CAF50", marginBottom: 12 }}>Wearable Intelligence</p>
                <h2 style={{ fontSize: "clamp(36px, 6vw, 76px)", fontWeight: 900, color: "#fff", letterSpacing: "-0.04em", lineHeight: 1 }}>Frictionless Capture.</h2>
              </div>

              {/* PAGE 2/3: Exploded View & S3 Core */}
              <div style={{ position: "absolute", top: "140vh", right: "10vw", width: "340px" }}>
                <div style={{ padding: "8px 16px", background: "rgba(255,255,255,0.05)", display: "inline-block", borderRadius: 100, border: "1px solid rgba(255,255,255,0.1)", marginBottom: 16 }}>
                   <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", color: "#fff" }}>ESP32-S3 ARCHITECTURE</span>
                </div>
                <h3 style={{ fontSize: 32, fontWeight: 800, color: "#fff", marginBottom: 16, letterSpacing: "-0.02em" }}>Edge Intelligence.</h3>
                <p style={{ color: "rgba(255,255,255,0.5)", fontSize: 15, lineHeight: 1.6 }}>By processing Voice Activity Detection (VAD) completely locally on the ESP32-S3 neural coprocessor, the device bypasses the latency of constant cloud pinging.</p>
              </div>

              {/* PAGE 3: Dual MEMS */}
              <div style={{ position: "absolute", top: "220vh", right: "10vw", width: "340px" }}>
                <h3 style={{ fontSize: 24, fontWeight: 800, color: "#fff", marginBottom: 12, letterSpacing: "-0.02em" }}>Acoustic Precision.</h3>
                <p style={{ color: "rgba(255,255,255,0.5)", fontSize: 15, lineHeight: 1.6 }}>Using an advanced dual-MEMS microphone array, ambient chaos is filtered out at the hardware level. Only perfectly clean semantic intent reaches the network layer.</p>
              </div>

              {/* PAGE 4: High Density Battery */}
              <div style={{ position: "absolute", top: "330vh", left: "10vw", width: "340px" }}>
                <div style={{ padding: "8px 16px", background: "rgba(76, 175, 80, 0.1)", display: "inline-block", borderRadius: 100, border: "1px solid rgba(76, 175, 80, 0.3)", marginBottom: 16 }}>
                   <span style={{ fontSize: 11, fontWeight: 700, letterSpacing: "0.1em", color: "#4CAF50" }}>ULTRA-LOW POWER</span>
                </div>
                <h3 style={{ fontSize: 32, fontWeight: 800, color: "#fff", marginBottom: 16, letterSpacing: "-0.02em" }}>Multi-Day Battery.</h3>
                <p style={{ color: "rgba(255,255,255,0.5)", fontSize: 15, lineHeight: 1.6 }}>Optimized sleep states combined with a high-density lithium-polymer cell means you can wear CortX endlessly without battery anxiety.</p>
              </div>

            </Scroll>
          </ScrollControls>
        </Canvas>
      </div>
    </section>
  );
}
