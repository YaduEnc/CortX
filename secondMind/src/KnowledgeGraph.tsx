import React, { useRef, useMemo, useEffect } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import * as THREE from 'three';

const PARTICLE_COUNT = 400; // Halved for elegance and background subtlety
const MAX_DISTANCE = 1.3; // Shorter connection lines

function Network() {
  const pointsRef = useRef<THREE.Points>(null);
  const linesRef = useRef<THREE.LineSegments>(null);
  const { viewport } = useThree();

  const mouse = useRef({ x: -1000, y: -1000 }); // start offscreen

  // Global mouse tracker ignoring DOM pointer-events
  useEffect(() => {
    const handleMove = (e: MouseEvent) => {
      mouse.current.x = (e.clientX / window.innerWidth) * 2 - 1;
      mouse.current.y = -(e.clientY / window.innerHeight) * 2 + 1;
    };
    window.addEventListener("mousemove", handleMove);
    return () => window.removeEventListener("mousemove", handleMove);
  }, []);

  // Pre-generate chaos (positions and drift velocities)
  const [positions, velocities] = useMemo(() => {
    const pos = new Float32Array(PARTICLE_COUNT * 3);
    const vel = new Float32Array(PARTICLE_COUNT * 3);
    for (let i = 0; i < PARTICLE_COUNT; i++) {
       pos[i * 3] = (Math.random() - 0.5) * 20;
       pos[i * 3 + 1] = (Math.random() - 0.5) * 20;
       pos[i * 3 + 2] = (Math.random() - 0.5) * 15;

       // Tiny drift speed
       vel[i * 3] = (Math.random() - 0.5) * 0.01;
       vel[i * 3 + 1] = (Math.random() - 0.5) * 0.01;
       vel[i * 3 + 2] = (Math.random() - 0.5) * 0.01;
    }
    return [pos, vel];
  }, []);

  // Pre-allocate arrays
  const [linePositions, lineColors] = useMemo(() => {
    const maxSegments = 6000; // Lower max segments prevents solid clumps
    return [new Float32Array(maxSegments * 3), new Float32Array(maxSegments * 3)];
  }, []);

  useFrame(() => {
    if (!pointsRef.current || !linesRef.current) return;
    
    const p = pointsRef.current.geometry.attributes.position.array as Float32Array;
    
    // Project screen mouse to 3D world space loosely
    const mouseX = (mouse.current.x * viewport.width) / 2;
    const mouseY = (mouse.current.y * viewport.height) / 2;

    let vertexpos = 0;
    let colorpos = 0;
    let numConnected = 0;

    for (let i = 0; i < PARTICLE_COUNT; i++) {
        p[i*3] += velocities[i*3];
        p[i*3+1] += velocities[i*3+1];
        p[i*3+2] += velocities[i*3+2];

        // Soft bounce boundaries
        if (p[i*3] > 10 || p[i*3] < -10) velocities[i*3] *= -1;
        if (p[i*3+1] > 10 || p[i*3+1] < -10) velocities[i*3+1] *= -1;
        if (p[i*3+2] > 8 || p[i*3+2] < -8) velocities[i*3+2] *= -1;

        // Interaction: Gentle Magnetism
        const dx = mouseX - p[i*3];
        const dy = mouseY - p[i*3+1];
        const dz = 0 - p[i*3+2];
        const distToMouse = Math.sqrt(dx*dx + dy*dy + dz*dz);
        
        if (distToMouse < 4.0) {
            // DRASTICALLY reduced pull so it doesn't form a solid unreadable block
            p[i*3] += dx * 0.0005;
            p[i*3+1] += dy * 0.0005;
            p[i*3+2] += dz * 0.0002;
        }

        for (let j = i + 1; j < PARTICLE_COUNT; j++) {
            const dxLine = p[i*3] - p[j*3];
            const dyLine = p[i*3+1] - p[j*3+1];
            const dzLine = p[i*3+2] - p[j*3+2];
            const dist = Math.sqrt(dxLine*dxLine + dyLine*dyLine + dzLine*dzLine);

            if (dist < MAX_DISTANCE) {
                const isNearMouse = (distToMouse < 3.0);
                
                // Dim intensity
                const intensity = (1.0 - (dist / MAX_DISTANCE));
                
                linePositions[vertexpos++] = p[i*3];
                linePositions[vertexpos++] = p[i*3+1];
                linePositions[vertexpos++] = p[i*3+2];

                linePositions[vertexpos++] = p[j*3];
                linePositions[vertexpos++] = p[j*3+1];
                linePositions[vertexpos++] = p[j*3+2];

                // Extremely subtle coloring to preserve readability
                // Base connections are virtually invisible. Mouse ones glow slightly green.
                const r = isNearMouse ? intensity * 0.1 : intensity * 0.02;
                const g = isNearMouse ? intensity * 0.4 : intensity * 0.05;
                const b = isNearMouse ? intensity * 0.15 : intensity * 0.02;

                lineColors[colorpos++] = r; lineColors[colorpos++] = g; lineColors[colorpos++] = b;
                lineColors[colorpos++] = r; lineColors[colorpos++] = g; lineColors[colorpos++] = b;

                numConnected++;
            }
            if (numConnected >= 5999) break; // Hard stop
        }
    }

    pointsRef.current.geometry.attributes.position.needsUpdate = true;
    linesRef.current.geometry.attributes.position.needsUpdate = true;
    linesRef.current.geometry.attributes.color.needsUpdate = true;
    linesRef.current.geometry.setDrawRange(0, numConnected * 2);

    // Super slow rotation
    pointsRef.current.rotation.y += 0.0002;
    pointsRef.current.rotation.x += 0.0001;
    linesRef.current.rotation.y += 0.0002;
    linesRef.current.rotation.x += 0.0001;
  });

  return (
    <group>
      <points ref={pointsRef}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" count={PARTICLE_COUNT} array={positions} itemSize={3} />
        </bufferGeometry>
        {/* Made nodes much dimmer so they don't block text */}
        <pointsMaterial color="#ffffff" size={0.03} transparent opacity={0.3} blending={THREE.AdditiveBlending} depthWrite={false} />
      </points>
      <lineSegments ref={linesRef}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" count={6000} array={linePositions} itemSize={3} usage={THREE.DynamicDrawUsage} />
          <bufferAttribute attach="attributes-color" count={6000} array={lineColors} itemSize={3} usage={THREE.DynamicDrawUsage} />
        </bufferGeometry>
        {/* Line completely transparent out of the box, relies purely on additive vertex color */}
        <lineBasicMaterial vertexColors transparent opacity={0.6} blending={THREE.AdditiveBlending} depthWrite={false} />
      </lineSegments>
    </group>
  );
}

export function KnowledgeGraph() {
  return (
    <div style={{ position: "fixed", inset: 0, zIndex: 0, pointerEvents: "none" }}>
       <Canvas camera={{ position: [0, 0, 7.5], fov: 60 }} gl={{ alpha: true, antialias: false }}>
          <Network />
       </Canvas>
    </div>
  );
}
