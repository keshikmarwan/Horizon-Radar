'use client';

import { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { EffectComposer } from 'three/examples/jsm/postprocessing/EffectComposer.js';
import { RenderPass } from 'three/examples/jsm/postprocessing/RenderPass.js';
import { UnrealBloomPass } from 'three/examples/jsm/postprocessing/UnrealBloomPass.js';
import { OutputPass } from 'three/examples/jsm/postprocessing/OutputPass.js';

type FitLoaderPhase = 'booting' | 'running' | 'finishing';
type FitPerformanceMode = 'cinematic' | 'balanced';

type NodeData = {
  pos: THREE.Vector3;
  color: THREE.Color;
  size: number;
  reveal: number;
  phase: number;
};

type EdgeData = {
  a: number;
  b: number;
  strength: number;
  phase: number;
  reveal: number;
  control: THREE.Vector3;
};

type SparkData = {
  edgeIndex: number;
  t: number;
  speed: number;
};

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function smoothstep(min: number, max: number, x: number): number {
  const t = clamp((x - min) / (max - min), 0, 1);
  return t * t * (3 - 2 * t);
}

function hash(seed: number): number {
  const x = Math.sin(seed * 127.1) * 43758.5453123;
  return x - Math.floor(x);
}

function bezierPoint(p0: THREE.Vector3, p1: THREE.Vector3, p2: THREE.Vector3, t: number, out: THREE.Vector3) {
  const it = 1 - t;
  out.set(
    it * it * p0.x + 2 * it * t * p1.x + t * t * p2.x,
    it * it * p0.y + 2 * it * t * p1.y + t * t * p2.y,
    it * it * p0.z + 2 * it * t * p1.z + t * t * p2.z
  );
}

export function FitConstellationLoader({ phase = 'running' }: { phase?: FitLoaderPhase }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const phaseRef = useRef<FitLoaderPhase>(phase);

  useEffect(() => {
    phaseRef.current = phase;
  }, [phase]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const renderer = new THREE.WebGLRenderer({
      canvas,
      antialias: true,
      alpha: false,
      powerPreference: 'high-performance',
    });
    renderer.setPixelRatio(clamp(window.devicePixelRatio || 1, 1, 2));
    renderer.setClearColor(0x000000, 1);
    renderer.outputColorSpace = THREE.SRGBColorSpace;

    const scene = new THREE.Scene();
    scene.fog = new THREE.FogExp2(0x000000, 0.00145);

    const camera = new THREE.PerspectiveCamera(58, 1, 0.1, 2000);
    camera.position.set(0, 14, 132);

    const composer = new EffectComposer(renderer);
    composer.addPass(new RenderPass(scene, camera));
    const bloomPass = new UnrealBloomPass(new THREE.Vector2(1, 1), 1.28, 0.46, 0.68);
    composer.addPass(bloomPass);
    composer.addPass(new OutputPass());

    const palette = [
      new THREE.Color(0x7dc8ff),
      new THREE.Color(0x4ea8ff),
      new THREE.Color(0xb8ddff),
      new THREE.Color(0x8ecbff),
      new THREE.Color(0xe5f2ff),
    ];

    const starLayerNear = 2600;
    const starLayerFar = 5200;

    function createStarField(count: number, minR: number, maxR: number, size: number, opacity: number) {
      const arr = new Float32Array(count * 3);
      for (let i = 0; i < count; i += 1) {
        const r = THREE.MathUtils.randFloat(minR, maxR);
        const phi = Math.acos(THREE.MathUtils.randFloatSpread(2));
        const theta = THREE.MathUtils.randFloat(0, Math.PI * 2);
        arr[i * 3 + 0] = r * Math.sin(phi) * Math.cos(theta);
        arr[i * 3 + 1] = r * Math.sin(phi) * Math.sin(theta);
        arr[i * 3 + 2] = r * Math.cos(phi);
      }
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.BufferAttribute(arr, 3));
      const mat = new THREE.PointsMaterial({
        color: 0xffffff,
        size,
        sizeAttenuation: true,
        transparent: true,
        opacity,
        depthWrite: false,
        blending: THREE.AdditiveBlending,
      });
      return new THREE.Points(geo, mat);
    }

    const starsFar = createStarField(starLayerFar, 120, 460, 0.12, 0.4);
    const starsNear = createStarField(starLayerNear, 60, 260, 0.18, 0.72);
    scene.add(starsFar);
    scene.add(starsNear);

    const nebula = new THREE.Mesh(
      new THREE.SphereGeometry(520, 28, 28),
      new THREE.MeshBasicMaterial({
        color: 0x07111c,
        transparent: true,
        opacity: 0.08,
        side: THREE.BackSide,
        blending: THREE.AdditiveBlending,
        depthWrite: false,
      })
    );
    scene.add(nebula);

    const networkGroup = new THREE.Group();
    scene.add(networkGroup);

    const NODE_COUNT = 300;
    const nodes: NodeData[] = [];

    for (let i = 0; i < NODE_COUNT; i += 1) {
      const fi = i + 0.5;
      const phi = Math.acos(1 - (2 * fi) / NODE_COUNT);
      const theta = Math.PI * (1 + Math.sqrt(5)) * fi;

      const noiseR = 52 + 62 * Math.pow(hash(i * 1.31 + 7.2), 0.74);
      const layer = Math.sin(phi * 3.5 + theta * 0.2) * 8;
      const r = noiseR + layer;

      const pos = new THREE.Vector3(
        Math.cos(theta) * Math.sin(phi) * r,
        Math.sin(theta) * Math.sin(phi) * r,
        Math.cos(phi) * r
      );

      const base = palette[i % palette.length].clone();
      base.offsetHSL(THREE.MathUtils.randFloatSpread(0.03), THREE.MathUtils.randFloatSpread(0.08), THREE.MathUtils.randFloatSpread(0.08));

      nodes.push({
        pos,
        color: base,
        size: 0.55 + hash(i * 2.77) * 0.9,
        reveal: hash(i * 3.91),
        phase: hash(i * 9.13) * Math.PI * 2,
      });
    }

    const edgeSet = new Set<string>();
    const edges: EdgeData[] = [];

    const distances: number[] = new Array(NODE_COUNT);

    for (let i = 0; i < NODE_COUNT; i += 1) {
      for (let j = 0; j < NODE_COUNT; j += 1) {
        if (i === j) {
          distances[j] = Number.POSITIVE_INFINITY;
        } else {
          distances[j] = nodes[i].pos.distanceToSquared(nodes[j].pos);
        }
      }

      for (let k = 0; k < 5; k += 1) {
        let best = -1;
        let bestD = Number.POSITIVE_INFINITY;
        for (let j = 0; j < NODE_COUNT; j += 1) {
          if (distances[j] < bestD) {
            bestD = distances[j];
            best = j;
          }
        }
        if (best < 0) break;
        distances[best] = Number.POSITIVE_INFINITY;

        const a = Math.min(i, best);
        const b = Math.max(i, best);
        const key = `${a}-${b}`;
        if (edgeSet.has(key)) continue;
        edgeSet.add(key);

        const p0 = nodes[a].pos;
        const p2 = nodes[b].pos;
        const mid = new THREE.Vector3().addVectors(p0, p2).multiplyScalar(0.5);
        const dir = new THREE.Vector3().subVectors(p2, p0).normalize();
        const up = new THREE.Vector3(hash(a * 1.7 + b * 0.9) - 0.5, hash(a * 0.8 + b * 1.3) - 0.5, hash(a * 2.1 + b * 1.1) - 0.5).normalize();
        const perp = new THREE.Vector3().crossVectors(dir, up).normalize();
        const bend = 3 + 13 * hash(a * 11.3 + b * 7.7);
        const control = mid.addScaledVector(perp, bend);

        edges.push({
          a,
          b,
          strength: clamp(1 - Math.sqrt(bestD) / 45, 0.18, 1),
          phase: hash(a * 13.31 + b * 17.91) * Math.PI * 2,
          reveal: hash(a * 0.37 + b * 0.61),
          control,
        });
      }
    }

    for (let i = 0; i < NODE_COUNT * 0.18; i += 1) {
      const a = Math.floor(hash(i * 19.3 + 3.1) * NODE_COUNT);
      const b = Math.floor(hash(i * 31.7 + 7.4) * NODE_COUNT);
      if (a === b) continue;
      const low = Math.min(a, b);
      const high = Math.max(a, b);
      const key = `${low}-${high}`;
      if (edgeSet.has(key)) continue;
      edgeSet.add(key);

      const p0 = nodes[low].pos;
      const p2 = nodes[high].pos;
      const mid = new THREE.Vector3().addVectors(p0, p2).multiplyScalar(0.5);
      const normal = mid.clone().normalize();
      const bend = 7 + 18 * hash(i * 4.13 + 9.7);
      const control = mid.addScaledVector(normal, bend);

      edges.push({
        a: low,
        b: high,
        strength: 0.28 + 0.42 * hash(i * 8.41 + 5.9),
        phase: hash(i * 5.71 + 6.2) * Math.PI * 2,
        reveal: 0.6 + 0.38 * hash(i * 2.11 + 4.4),
        control,
      });
    }

    const nodePos = new Float32Array(NODE_COUNT * 3);
    const nodeCol = new Float32Array(NODE_COUNT * 3);
    const nodeSize = new Float32Array(NODE_COUNT);
    const nodeReveal = new Float32Array(NODE_COUNT);
    const nodePhase = new Float32Array(NODE_COUNT);
    const nodeTarget = new Float32Array(NODE_COUNT * 3);

    for (let i = 0; i < NODE_COUNT; i += 1) {
      const n = nodes[i];
      nodePos[i * 3 + 0] = n.pos.x;
      nodePos[i * 3 + 1] = n.pos.y;
      nodePos[i * 3 + 2] = n.pos.z;
      nodeCol[i * 3 + 0] = n.color.r;
      nodeCol[i * 3 + 1] = n.color.g;
      nodeCol[i * 3 + 2] = n.color.b;
      nodeSize[i] = n.size;
      nodeReveal[i] = n.reveal;
      nodePhase[i] = n.phase;

      // Target dot sphere (chat-like) used at fit completion.
      const tf = i + 0.5;
      const tPhi = Math.acos(1 - (2 * tf) / NODE_COUNT);
      const tTheta = Math.PI * (1 + Math.sqrt(5)) * tf;
      const tR = 17.5;
      nodeTarget[i * 3 + 0] = Math.cos(tTheta) * Math.sin(tPhi) * tR;
      nodeTarget[i * 3 + 1] = Math.sin(tTheta) * Math.sin(tPhi) * tR;
      nodeTarget[i * 3 + 2] = Math.cos(tPhi) * tR;
    }

    const nodeGeo = new THREE.BufferGeometry();
    nodeGeo.setAttribute('position', new THREE.BufferAttribute(nodePos, 3));
    nodeGeo.setAttribute('aColor', new THREE.BufferAttribute(nodeCol, 3));
    nodeGeo.setAttribute('aSize', new THREE.BufferAttribute(nodeSize, 1));
    nodeGeo.setAttribute('aReveal', new THREE.BufferAttribute(nodeReveal, 1));
    nodeGeo.setAttribute('aPhase', new THREE.BufferAttribute(nodePhase, 1));
    nodeGeo.setAttribute('aTarget', new THREE.BufferAttribute(nodeTarget, 3));

    const nodeMat = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      uniforms: {
        uTime: { value: 0 },
        uConnect: { value: 0 },
        uMorph: { value: 0 },
      },
      vertexShader: `
        attribute vec3 aColor;
        attribute float aSize;
        attribute float aReveal;
        attribute float aPhase;
        attribute vec3 aTarget;
        uniform float uTime;
        uniform float uConnect;
        uniform float uMorph;
        varying vec3 vColor;
        varying float vReveal;
        varying float vPulse;
        void main() {
          vColor = aColor;
          float reveal = smoothstep(aReveal - 0.1, aReveal + 0.1, uConnect);
          vReveal = reveal;
          vPulse = 0.55 + 0.45 * sin(uTime * 2.2 + aPhase);

          float collapse = smoothstep(0.0, 0.5, uMorph);
          float sphere = smoothstep(0.5, 1.0, uMorph);
          vec3 collapsed = mix(position, vec3(0.0), collapse);
          vec3 finalPos = mix(collapsed, aTarget, sphere);

          vec4 mv = modelViewMatrix * vec4(finalPos, 1.0);
          float morphScale = mix(1.0, 1.35, sphere);
          gl_PointSize = (aSize * (1.0 + vPulse * 0.45) + uConnect * 0.65) * morphScale * (880.0 / -mv.z);
          gl_Position = projectionMatrix * mv;
        }
      `,
      fragmentShader: `
        varying vec3 vColor;
        varying float vReveal;
        varying float vPulse;
        void main() {
          vec2 p = gl_PointCoord * 2.0 - 1.0;
          float d = dot(p,p);
          if (d > 1.0) discard;
          float core = 1.0 - smoothstep(0.0, 0.4, d);
          float glow = 1.0 - smoothstep(0.0, 1.0, d);
          float alpha = (core * 0.9 + glow * 0.4) * (0.2 + 0.8 * vReveal) * (0.72 + vPulse * 0.28);
          vec3 color = vColor * (1.0 + vPulse * 0.35);
          gl_FragColor = vec4(color, alpha);
        }
      `,
    });

    const nodesMesh = new THREE.Points(nodeGeo, nodeMat);
    networkGroup.add(nodesMesh);

    const linePositions: number[] = [];
    const lineColors: number[] = [];
    const lineProg: number[] = [];
    const linePhase: number[] = [];
    const lineStrength: number[] = [];
    const lineReveal: number[] = [];
    const lineZ: number[] = [];

    const tmp0 = new THREE.Vector3();
    const tmp1 = new THREE.Vector3();

    const SEGMENTS = 18;

    for (let i = 0; i < edges.length; i += 1) {
      const e = edges[i];
      const p0 = nodes[e.a].pos;
      const p1 = e.control;
      const p2 = nodes[e.b].pos;

      for (let s = 0; s < SEGMENTS; s += 1) {
        const t0 = s / SEGMENTS;
        const t1 = (s + 1) / SEGMENTS;
        bezierPoint(p0, p1, p2, t0, tmp0);
        bezierPoint(p0, p1, p2, t1, tmp1);

        const mx = (tmp0.x + tmp1.x) * 0.5;
        const my = (tmp0.y + tmp1.y) * 0.5;
        const mz = (tmp0.z + tmp1.z) * 0.5;

        const c = palette[(i + s) % palette.length];

        linePositions.push(tmp0.x, tmp0.y, tmp0.z, tmp1.x, tmp1.y, tmp1.z);
        lineColors.push(c.r, c.g, c.b, c.r, c.g, c.b);

        const prog = (t0 + t1) * 0.5;
        lineProg.push(prog, prog);
        linePhase.push(e.phase, e.phase);
        lineStrength.push(e.strength, e.strength);
        lineReveal.push(e.reveal, e.reveal);
        lineZ.push(mz, mz);
      }
    }

    const lineGeo = new THREE.BufferGeometry();
    lineGeo.setAttribute('position', new THREE.Float32BufferAttribute(linePositions, 3));
    lineGeo.setAttribute('aColor', new THREE.Float32BufferAttribute(lineColors, 3));
    lineGeo.setAttribute('aProg', new THREE.Float32BufferAttribute(lineProg, 1));
    lineGeo.setAttribute('aPhase', new THREE.Float32BufferAttribute(linePhase, 1));
    lineGeo.setAttribute('aStrength', new THREE.Float32BufferAttribute(lineStrength, 1));
    lineGeo.setAttribute('aReveal', new THREE.Float32BufferAttribute(lineReveal, 1));
    lineGeo.setAttribute('aZ', new THREE.Float32BufferAttribute(lineZ, 1));

    const lineMat = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
      uniforms: {
        uTime: { value: 0 },
        uConnect: { value: 0 },
        uScanA: { value: 0 },
        uScanB: { value: 0 },
        uGhost: { value: 0.04 },
        uLineFade: { value: 1 },
      },
      vertexShader: `
        attribute vec3 aColor;
        attribute float aProg;
        attribute float aPhase;
        attribute float aStrength;
        attribute float aReveal;
        attribute float aZ;
        varying vec3 vColor;
        varying float vProg;
        varying float vPhase;
        varying float vStrength;
        varying float vReveal;
        varying float vZ;
        void main() {
          vColor = aColor;
          vProg = aProg;
          vPhase = aPhase;
          vStrength = aStrength;
          vReveal = aReveal;
          vZ = aZ;
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: `
        uniform float uTime;
        uniform float uConnect;
        uniform float uScanA;
        uniform float uScanB;
        uniform float uGhost;
        uniform float uLineFade;
        varying vec3 vColor;
        varying float vProg;
        varying float vPhase;
        varying float vStrength;
        varying float vReveal;
        varying float vZ;
        void main() {
          float reveal = smoothstep(vReveal - 0.08, vReveal + 0.08, uConnect);
          float flow = 0.5 + 0.5 * sin(vProg * 14.0 - uTime * (3.0 + vStrength * 2.2) + vPhase);
          float beat = 0.5 + 0.5 * sin(uTime * 2.6 + vPhase * 1.3);
          float sA = exp(-pow(vZ - uScanA, 2.0) / (2.0 * 17.0 * 17.0));
          float sB = exp(-pow(vZ - uScanB, 2.0) / (2.0 * 23.0 * 23.0));
          float scan = sA + sB;

          float ghost = (1.0 - reveal) * uGhost * (0.55 + vStrength * 0.45);
          float alpha = (reveal * ((0.07 + vStrength * 0.13) + flow * 0.2 * vStrength + beat * 0.08 + scan * 0.22 * vStrength) + ghost) * uLineFade;
          vec3 color = vColor * (0.78 + flow * 0.38 + scan * 0.28);
          gl_FragColor = vec4(color, alpha);
        }
      `,
    });

    const linesMesh = new THREE.LineSegments(lineGeo, lineMat);
    networkGroup.add(linesMesh);

    const sparkCount = 260;
    const sparks: SparkData[] = [];
    const sparkPos = new Float32Array(sparkCount * 3);
    const sparkGeo = new THREE.BufferGeometry();
    sparkGeo.setAttribute('position', new THREE.BufferAttribute(sparkPos, 3));
    const sparkMat = new THREE.PointsMaterial({
      color: 0xddefff,
      size: 1.06,
      sizeAttenuation: true,
      transparent: true,
      opacity: 0.0,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    const sparkPoints = new THREE.Points(sparkGeo, sparkMat);
    networkGroup.add(sparkPoints);

    for (let i = 0; i < sparkCount; i += 1) {
      sparks.push({
        edgeIndex: Math.floor(hash(i * 3.21 + 11.7) * edges.length),
        t: hash(i * 4.17 + 3.9),
        speed: 0.16 + hash(i * 8.31 + 5.2) * 0.56,
      });
    }

    const clock = new THREE.Clock();
    let raf = 0;
    let lastFrameMs = performance.now();
    let fpsEma = 60;
    let perfMode: FitPerformanceMode = 'cinematic';
    let lowFpsStreak = 0;
    let goodFpsStreak = 0;

    const tmpSpark = new THREE.Vector3();
    let smoothConnect = 0;
    let smoothPhaseScale = 0.5;
    let smoothFinishBoost = 0;
    let smoothCamZ = camera.position.z;
    let smoothCamX = camera.position.x;
    let smoothCamY = camera.position.y;
    let smoothBloom = 1.2;
    let smoothMorph = 0;
    let phaseTracker: FitLoaderPhase = phaseRef.current;
    let phaseStart = 0;

    const resize = () => {
      const w = window.innerWidth;
      const h = window.innerHeight;
      renderer.setSize(w, h, false);
      composer.setSize(w, h);
      bloomPass.resolution.set(w, h);
      camera.aspect = w / h;
      camera.updateProjectionMatrix();
    };

    const animate = () => {
      const t = clock.getElapsedTime();
      const nowMs = performance.now();
      const dtMs = Math.max(8, nowMs - lastFrameMs);
      lastFrameMs = nowMs;
      const fps = 1000 / dtMs;
      fpsEma = fpsEma * 0.92 + fps * 0.08;
      const phaseNow = phaseRef.current;
      if (phaseNow !== phaseTracker) {
        phaseTracker = phaseNow;
        phaseStart = t;
      }
      const timeline = clamp(t / 15, 0, 1);

      const connectBase = smoothstep(0.22, 0.98, timeline);
      const phaseScaleTarget = phaseNow === 'booting' ? 0.46 : 1;
      const finishBoostTarget = phaseNow === 'finishing' ? 1 : 0;
      smoothPhaseScale = THREE.MathUtils.lerp(smoothPhaseScale, phaseScaleTarget, 0.055);
      smoothFinishBoost = THREE.MathUtils.lerp(smoothFinishBoost, finishBoostTarget, 0.07);

      const connectTarget = clamp(connectBase * smoothPhaseScale + smoothFinishBoost * 0.2, 0, 1);
      smoothConnect = THREE.MathUtils.lerp(smoothConnect, connectTarget, 0.06);

      // Auto performance mode: degrade only if FPS is consistently low.
      if (fpsEma < 41) {
        lowFpsStreak += 1;
        goodFpsStreak = 0;
      } else if (fpsEma > 53) {
        goodFpsStreak += 1;
        lowFpsStreak = Math.max(0, lowFpsStreak - 1);
      } else {
        lowFpsStreak = Math.max(0, lowFpsStreak - 1);
        goodFpsStreak = Math.max(0, goodFpsStreak - 1);
      }

      if (perfMode === 'cinematic' && lowFpsStreak > 36) {
        perfMode = 'balanced';
        renderer.setPixelRatio(1);
      } else if (perfMode === 'balanced' && goodFpsStreak > 120) {
        perfMode = 'cinematic';
        renderer.setPixelRatio(clamp(window.devicePixelRatio || 1, 1, 2));
      }

      const scanA = ((t * 60) % 290) - 145;
      const scanB = 145 - ((t * 44) % 290);

      lineMat.uniforms.uTime.value = t;
      lineMat.uniforms.uConnect.value = smoothConnect;
      lineMat.uniforms.uScanA.value = scanA;
      lineMat.uniforms.uScanB.value = scanB;
      const ghostWarmup = smoothstep(0.0, 0.22, timeline);
      const ghostRun = 1 - smoothstep(0.35, 0.92, smoothConnect);
      lineMat.uniforms.uGhost.value = 0.02 + ghostWarmup * 0.07 * ghostRun;

      nodeMat.uniforms.uTime.value = t;
      nodeMat.uniforms.uConnect.value = smoothConnect;

      let morphTarget = 0;
      if (phaseNow === 'finishing') {
        const ft = clamp((t - phaseStart) / 1.05, 0, 1);
        morphTarget = ft;
      }
      smoothMorph = THREE.MathUtils.lerp(smoothMorph, morphTarget, 0.08);
      nodeMat.uniforms.uMorph.value = smoothMorph;
      lineMat.uniforms.uLineFade.value = 1 - smoothstep(0.12, 0.85, smoothMorph);

      const sparkPosAttr = sparkGeo.getAttribute('position') as THREE.BufferAttribute;
      for (let i = 0; i < sparkCount; i += 1) {
        const s = sparks[i];
        const edge = edges[s.edgeIndex % edges.length];
        const p0 = nodes[edge.a].pos;
        const p1 = edge.control;
        const p2 = nodes[edge.b].pos;

        s.t += (0.0016 + s.speed * 0.0026) * (0.36 + smoothConnect * 1.55);
        if (s.t >= 1) {
          s.t -= 1;
          s.edgeIndex = Math.floor(Math.random() * edges.length);
        }

        bezierPoint(p0, p1, p2, s.t, tmpSpark);
        sparkPos[i * 3 + 0] = tmpSpark.x;
        sparkPos[i * 3 + 1] = tmpSpark.y;
        sparkPos[i * 3 + 2] = tmpSpark.z;
      }
      sparkPosAttr.needsUpdate = true;

      const sparkFade = 1 - smoothstep(0.18, 0.82, smoothMorph);
      const perfSparkScale = perfMode === 'balanced' ? 0.42 : 1;
      sparkMat.opacity = THREE.MathUtils.lerp(sparkMat.opacity, (0.05 + smoothConnect * 0.64) * sparkFade * perfSparkScale, 0.08);
      sparkMat.size = THREE.MathUtils.lerp(sparkMat.size, (0.7 + smoothConnect * 1.35) * (perfMode === 'balanced' ? 0.82 : 1), 0.08);

      const breathing = 0.5 + 0.5 * Math.sin(t * 0.9);
      networkGroup.rotation.y = Math.sin(t * 0.21) * 0.12;
      networkGroup.rotation.x = Math.sin(t * 0.17) * 0.08;
      networkGroup.rotation.z = Math.sin(t * 0.11) * 0.05;
      if (smoothMorph > 0.02) {
        networkGroup.rotation.y += smoothMorph * 0.42;
        networkGroup.rotation.x = THREE.MathUtils.lerp(networkGroup.rotation.x, 0.08, 0.1 * smoothMorph);
        networkGroup.rotation.z = THREE.MathUtils.lerp(networkGroup.rotation.z, 0, 0.1 * smoothMorph);
      }
      starsNear.rotation.y += 0.00048;
      starsFar.rotation.y += 0.00016;

      const camEase = smoothstep(0, 1, timeline);
      let z = 132 - camEase * 76;
      if (phaseNow === 'booting') z += 14;
      if (phaseNow === 'finishing') z -= 10;
      const camXTarget = Math.sin(t * 0.24) * (4 + smoothConnect * 4);
      const camYTarget = 14 - camEase * 6 + Math.cos(t * 0.33) * 1.2;
      const sphereCamX = Math.sin(t * 0.52) * 2.2;
      const sphereCamY = 8.4 + Math.cos(t * 0.48) * 0.9;
      const sphereCamZ = 72;
      smoothCamX = THREE.MathUtils.lerp(smoothCamX, THREE.MathUtils.lerp(camXTarget, sphereCamX, smoothMorph), 0.08);
      smoothCamY = THREE.MathUtils.lerp(smoothCamY, THREE.MathUtils.lerp(camYTarget, sphereCamY, smoothMorph), 0.08);
      smoothCamZ = THREE.MathUtils.lerp(smoothCamZ, THREE.MathUtils.lerp(z, sphereCamZ, smoothMorph), 0.08);
      camera.position.set(smoothCamX, smoothCamY, smoothCamZ);
      camera.lookAt(0, 0, 0);

      const perfBloomScale = perfMode === 'balanced' ? 0.68 : 1;
      const bloomTarget = (1.08 + 0.38 * breathing + smoothConnect * 0.52 + smoothFinishBoost * 0.35) * perfBloomScale;
      smoothBloom = THREE.MathUtils.lerp(smoothBloom, bloomTarget, 0.075);
      bloomPass.strength = smoothBloom;

      nebula.rotation.y -= 0.00042;
      composer.render();
      raf = window.requestAnimationFrame(animate);
    };

    resize();
    window.addEventListener('resize', resize);
    raf = window.requestAnimationFrame(animate);

    return () => {
      if (raf) window.cancelAnimationFrame(raf);
      window.removeEventListener('resize', resize);

      composer.dispose();

      nodeGeo.dispose();
      lineGeo.dispose();
      sparkGeo.dispose();
      starNearDispose();
      starFarDispose();

      nodeMat.dispose();
      lineMat.dispose();
      sparkMat.dispose();
      (nebula.geometry as THREE.BufferGeometry).dispose();
      (nebula.material as THREE.Material).dispose();

      renderer.dispose();
    };

    function starNearDispose() {
      starsNear.geometry.dispose();
      (starsNear.material as THREE.Material).dispose();
    }

    function starFarDispose() {
      starsFar.geometry.dispose();
      (starsFar.material as THREE.Material).dispose();
    }
  }, []);

  return <canvas ref={canvasRef} className="fit-constellation-canvas" aria-hidden="true" />;
}
