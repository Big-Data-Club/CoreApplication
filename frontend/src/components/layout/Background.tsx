'use client';

import React, { useRef, useEffect } from 'react';

interface Pointer {
  x: number | null;
  y: number | null;
  down: boolean;
}

class Particle {
  x: number;
  y: number;
  vx: number;
  vy: number;
  size: number;
  hue: number;

  constructor(x: number, y: number, vx: number, vy: number, size: number, hue: number) {
    this.x = x;
    this.y = y;
    this.vx = vx;
    this.vy = vy;
    this.size = size;
    this.hue = hue;
  }

  draw(ctx: CanvasRenderingContext2D) {
    ctx.beginPath();
    ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
    ctx.fillStyle = `hsla(${this.hue}, 70%, 60%, 0.95)`;
    ctx.shadowColor = `hsla(${this.hue}, 80%, 65%, 0.85)`;
    ctx.shadowBlur = Math.max(6, this.size * 2);
    ctx.fill();
    ctx.shadowBlur = 0;
  }

  update(width: number, height: number) {
    this.x += this.vx;
    this.y += this.vy;

    if (this.x <= 0 || this.x >= width) {
      this.vx *= -1;
      this.x = Math.max(0, Math.min(width, this.x));
    }
    if (this.y <= 0 || this.y >= height) {
      this.vy *= -1;
      this.y = Math.max(0, Math.min(height, this.y));
    }

    this.vx *= 0.999;
    this.vy *= 0.999;
  }
}

const Background: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const particlesRef = useRef<Particle[]>([]);
  const pointerRef = useRef<Pointer>({ x: null, y: null, down: false });
  const rafRef = useRef<number | null>(null);
  const resizeTimerRef = useRef<number | null>(null);

  const config = {
    baseHue: 210, 
    hueVariation: 30,
    particleDensity: 4500,
    minSize: 0.8,
    maxSize: 3,
    maxSpeed: 0.7,
    connectDistanceRatio: 0.09,
    repulseRadiusRatio: 0.12,
  } as const;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d', { alpha: true });
    if (!ctx) return;

    let dpr = Math.max(1, window.devicePixelRatio || 1);
    let width = 0;
    let height = 0;

    function setSize() {
      dpr = Math.max(1, window.devicePixelRatio || 1);
      const w = Math.max(window.innerWidth, 300);
      const h = Math.max(window.innerHeight, 300);
      width = w;
      height = h;
      canvas!.style.width = `${w}px`;
      canvas!.style.height = `${h}px`;
      canvas!.width = Math.round(w * dpr);
      canvas!.height = Math.round(h * dpr);
      ctx!.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function initParticles() {
      const area = width * height;
      const targetCount = Math.max(10, Math.round(area / config.particleDensity));
      const arr: Particle[] = [];
      for (let i = 0; i < targetCount; i++) {
        const size = Math.random() * (config.maxSize - config.minSize) + config.minSize;
        const x = Math.random() * width;
        const y = Math.random() * height;
        const vx = (Math.random() - 0.5) * config.maxSpeed;
        const vy = (Math.random() - 0.5) * config.maxSpeed;
        const hue = config.baseHue + (Math.random() - 0.5) * config.hueVariation;
        arr.push(new Particle(x, y, vx, vy, size, hue));
      }
      particlesRef.current = arr;
    }

    function clearCanvas() {
      ctx!.clearRect(0, 0, width, height);
    }

    function animate() {
      const particles = particlesRef.current;
      if (!ctx) return;

      clearCanvas();

      ctx.globalCompositeOperation = 'source-over';

      for (let i = 0; i < particles.length; i++) {
        const p = particles[i];

        const px = pointerRef.current.x;
        const py = pointerRef.current.y;
        if (px !== null && py !== null) {
          const dx = p.x - px;
          const dy = p.y - py;
          const dist = Math.sqrt(dx * dx + dy * dy);
          const repulseRadius = Math.min(width, height) * config.repulseRadiusRatio;
          if (dist < repulseRadius) {
            const force = (1 - dist / repulseRadius) * 1; // strength
            const ux = dx / (dist || 1);
            const uy = dy / (dist || 1);
            p.vx = (p.vx + ux * force) * 0.62;
            p.vy = (p.vy + uy * force) * 0.62;
          }
        }

        p.update(width, height);
        p.draw(ctx);
      }

      ctx.lineWidth = 1.2;
      ctx.globalCompositeOperation = 'source-over';
      const connectDist = Math.min(width, height) * config.connectDistanceRatio;
      const connectDistSq = connectDist * connectDist;

      const parts = particlesRef.current;
      for (let a = 0; a < parts.length; a++) {
        for (let b = a + 1; b < parts.length; b++) {
          const dx = parts[a].x - parts[b].x;
          const dy = parts[a].y - parts[b].y;
          const distSq = dx * dx + dy * dy;
          if (distSq < connectDistSq) {
            const alpha = 1 - distSq / connectDistSq;
            const hue = (parts[a].hue + parts[b].hue) / 2;
            ctx.strokeStyle = `hsla(${hue}, 80%, 70%, ${0.18 * alpha})`;
            ctx.beginPath();
            ctx.moveTo(parts[a].x, parts[a].y);
            ctx.lineTo(parts[b].x, parts[b].y);
            ctx.stroke();
          }
        }
      }

      const px = pointerRef.current.x;
      const py = pointerRef.current.y;
      if (px !== null && py !== null) {
        for (let i = 0; i < parts.length; i++) {
          const dx = parts[i].x - px;
          const dy = parts[i].y - py;
          const distSq = dx * dx + dy * dy;
          const grabDist = Math.min(width, height) * 0.25;
          if (distSq < grabDist * grabDist) {
            const alpha = 1 - Math.sqrt(distSq) / grabDist;
            ctx.strokeStyle = `hsla(${parts[i].hue}, 90%, 70%, ${0.52 * alpha})`;
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(px, py);
            ctx.lineTo(parts[i].x, parts[i].y);
            ctx.stroke();
          }
        }
      }

      rafRef.current = requestAnimationFrame(animate);
    }

    function onPointerMove(e: PointerEvent) {
      pointerRef.current.x = e.clientX;
      pointerRef.current.y = e.clientY;
    }
    function onPointerLeave() {
      pointerRef.current.x = null;
      pointerRef.current.y = null;
    }

    function onResize() {
      if (resizeTimerRef.current) {
        window.clearTimeout(resizeTimerRef.current);
      }
      resizeTimerRef.current = window.setTimeout(() => {
        setSize();
        initParticles();
      }, 120);
    }

    // initialize
    setSize();
    initParticles();
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerdown', () => (pointerRef.current.down = true));
    window.addEventListener('pointerup', () => (pointerRef.current.down = false));
    window.addEventListener('pointerleave', onPointerLeave);
    window.addEventListener('resize', onResize);

    // start loop
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(animate);

    // cleanup
    return () => {
      if (rafRef.current) cancelAnimationFrame(rafRef.current);
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerdown', () => (pointerRef.current.down = true));
      window.removeEventListener('pointerup', () => (pointerRef.current.down = false));
      window.removeEventListener('pointerleave', onPointerLeave);
      window.removeEventListener('resize', onResize);
      if (resizeTimerRef.current) window.clearTimeout(resizeTimerRef.current);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="fixed inset-0 w-full h-full -z-10 pointer-events-none bg-transparent"
      aria-hidden
    />
  );
};

export default Background;
