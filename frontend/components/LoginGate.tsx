'use client';

import { FormEvent, useEffect, useRef, useState } from 'react';

const AUTH_STORAGE_KEY = 'horizon-radar-auth-v1';
const AUTH_USER = 'admin';
const AUTH_PASSWORD = 'admin123';
const LOGO_FRAMES = [
  '/images/logo-seq/1.png',
  '/images/logo-seq/2.png',
  '/images/logo-seq/3.png',
  '/images/logo-seq/4.png',
  '/images/logo-seq/5.png',
  '/images/logo-seq/6.png',
  '/images/logo-seq/5.png',
  '/images/logo-seq/4.png',
  '/images/logo-seq/3.png',
  '/images/logo-seq/2.png',
];
const BURST_FRAMES = [
  '/images/logo-seq/1.png',
  '/images/logo-seq/2.png',
  '/images/logo-seq/3.png',
  '/images/logo-seq/4.png',
  '/images/logo-seq/5.png',
  '/images/logo-seq/6.png',
];

const FRAME_DURATIONS = [320, 300, 290, 290, 320, 520, 320, 290, 290, 300];

type Props = {
  children: React.ReactNode;
};

export function LoginGate({ children }: Props) {
  const [ready, setReady] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  const [frameIndex, setFrameIndex] = useState(0);
  const [layerA, setLayerA] = useState(LOGO_FRAMES[0]);
  const [layerB, setLayerB] = useState(LOGO_FRAMES[1]);
  const [showLayerA, setShowLayerA] = useState(true);
  const [logoKick, setLogoKick] = useState(false);
  const [isUnlocking, setIsUnlocking] = useState(false);
  const timeoutRef = useRef<number | null>(null);

  useEffect(() => {
    const value = window.localStorage.getItem(AUTH_STORAGE_KEY);
    setAuthenticated(value === 'ok');
    setReady(true);
  }, []);

  useEffect(() => {
    if (isUnlocking) return;

    const schedule = () => {
      const ms = FRAME_DURATIONS[frameIndex] || 140;
      timeoutRef.current = window.setTimeout(() => {
        setFrameIndex((prev) => {
          const next = (prev + 1) % LOGO_FRAMES.length;
          const nextFrame = LOGO_FRAMES[next];
          if (showLayerA) {
            setLayerB(nextFrame);
            setShowLayerA(false);
          } else {
            setLayerA(nextFrame);
            setShowLayerA(true);
          }
          setLogoKick(true);
          window.setTimeout(() => setLogoKick(false), 180);
          return next;
        });
      }, ms);
    };

    schedule();

    return () => {
      if (timeoutRef.current) {
        window.clearTimeout(timeoutRef.current);
      }
    };
  }, [frameIndex, showLayerA, isUnlocking]);

  useEffect(() => {
    if (!isUnlocking) return;

    const sequence = [...BURST_FRAMES, ...BURST_FRAMES, ...BURST_FRAMES];
    let idx = 0;

    const intervalId = window.setInterval(() => {
      const frame = sequence[idx];
      setShowLayerA((prev) => {
        if (prev) {
          setLayerB(frame);
        } else {
          setLayerA(frame);
        }
        return !prev;
      });
      setLogoKick(true);
      window.setTimeout(() => setLogoKick(false), 110);
      idx += 1;

      if (idx >= sequence.length) {
        window.clearInterval(intervalId);
        window.localStorage.setItem(AUTH_STORAGE_KEY, 'ok');
        setAuthenticated(true);
        setIsUnlocking(false);
      }
    }, 85);

    return () => window.clearInterval(intervalId);
  }, [isUnlocking]);

  const onSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (username.trim() === AUTH_USER && password === AUTH_PASSWORD) {
      setError('');
      setIsUnlocking(true);
      return;
    }

    setError('Credenziali non valide. Usa admin / admin123.');
  };

  if (!ready) {
    return (
      <div className="login-screen" aria-hidden="true">
        <video className="login-bg-video" autoPlay muted loop playsInline preload="auto">
          <source src="/videos/gb-bg/motion.mp4" type="video/mp4" />
        </video>
        <div className="login-bg-mask" />
        <div className="login-shell login-shell--loading">
          <div className="login-brand-panel login-brand-panel--single">
            <div className={logoKick ? 'login-logo-stage kick' : 'login-logo-stage'}>
              <div className="login-logo-halo" />
              <div className="login-logo-seq">
                <img src={layerA} alt="" className={showLayerA ? 'logo-layer active' : 'logo-layer'} />
                <img src={layerB} alt="" className={!showLayerA ? 'logo-layer active' : 'logo-layer'} />
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (!authenticated) {
    return (
      <div className="login-screen">
        <video className="login-bg-video" autoPlay muted loop playsInline preload="auto">
          <source src="/videos/gb-bg/motion.mp4" type="video/mp4" />
        </video>
        <div className="login-bg-mask" />

        <div className="login-shell login-shell--single">
          <aside className="login-brand-panel login-brand-panel--single">
            <div className={logoKick ? 'login-logo-stage kick' : 'login-logo-stage'}>
              <div className="login-logo-halo" />
              <div className="login-logo-seq" aria-hidden="true">
                <img src={layerA} alt="" className={showLayerA ? 'logo-layer active' : 'logo-layer'} />
                <img src={layerB} alt="" className={!showLayerA ? 'logo-layer active' : 'logo-layer'} />
              </div>
            </div>

            <h1>Accesso Riservato</h1>
            <p className="small">Autenticazione amministrativa richiesta per l&apos;accesso alla piattaforma.</p>

            <form className="login-form" onSubmit={onSubmit}>
              <label>
                Username
                <input
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  placeholder="admin"
                  disabled={isUnlocking}
                />
              </label>
              <label>
                Password
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  spellCheck={false}
                  placeholder="admin123"
                  disabled={isUnlocking}
                />
              </label>
              {error ? <p className="small login-error">{error}</p> : null}
              <button type="submit" disabled={isUnlocking}>
                {isUnlocking ? 'Accesso...' : 'Accedi'}
              </button>
            </form>
          </aside>
        </div>
      </div>
    );
  }

  return <>{children}</>;
}
