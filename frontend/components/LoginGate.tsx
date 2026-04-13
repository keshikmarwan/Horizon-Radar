'use client';

import { FormEvent, useEffect, useRef, useState } from 'react';
import { signIn } from 'next-auth/react';

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
const FRAME_DURATIONS = [320, 300, 290, 290, 320, 520, 320, 290, 290, 300];

const LOGIN_BG_PLAYLIST = [
  '/videos/gb-bg/hero1.mp4',
  '/videos/gb-bg/motion.mp4',
  '/videos/gb-bg/main1.mp4',
  '/videos/gb-bg/main2.mp4',
  '/videos/gb-bg/openplat.mp4',
  '/videos/gb-bg/touch3.mp4',
  '/videos/gb-bg/teaser.mp4',
];

type Props = {
  children: React.ReactNode;
};

export function LoginGate({ children }: Props) {
  const [ready, setReady] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [frameIndex, setFrameIndex] = useState(0);
  const [layerA, setLayerA] = useState(LOGO_FRAMES[0]);
  const [layerB, setLayerB] = useState(LOGO_FRAMES[1]);
  const [showLayerA, setShowLayerA] = useState(true);
  const [logoKick, setLogoKick] = useState(false);

  const [bgVideoIndex, setBgVideoIndex] = useState(0);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const logoTimerRef = useRef<number | null>(null);

  const activeBgVideo = LOGIN_BG_PLAYLIST[bgVideoIndex] || LOGIN_BG_PLAYLIST[0];

  useEffect(() => {
    let mounted = true;
    const checkSession = async () => {
      try {
        const res = await fetch('/api/auth/session', { cache: 'no-store' });
        if (!mounted) return;
        if (!res.ok) {
          setAuthenticated(false);
          setReady(true);
          return;
        }
        const session = (await res.json()) as { user?: { email?: string } } | null;
        setAuthenticated(Boolean(session?.user?.email));
      } catch {
        setAuthenticated(false);
      } finally {
        if (mounted) setReady(true);
      }
    };
    void checkSession();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (!videoRef.current) return;
    videoRef.current.playbackRate = 0.84;
    void videoRef.current.play().catch(() => {});
  }, [activeBgVideo]);

  useEffect(() => {
    const ms = FRAME_DURATIONS[frameIndex] || 180;
    logoTimerRef.current = window.setTimeout(() => {
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
        window.setTimeout(() => setLogoKick(false), 160);
        return next;
      });
    }, ms);

    return () => {
      if (logoTimerRef.current) window.clearTimeout(logoTimerRef.current);
    };
  }, [frameIndex, showLayerA]);

  const onLoginVideoEnded = () => {
    setBgVideoIndex((idx) => (idx + 1) % LOGIN_BG_PLAYLIST.length);
  };

  const onSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    if (!username.trim() || !password) {
      setError('Inserisci username e password.');
      return;
    }

    setError('');
    setSubmitting(true);

    const result = await signIn('credentials', {
      username: username.trim(),
      password,
      redirect: false,
    });

    if (result?.ok) {
      setAuthenticated(true);
      setSubmitting(false);
      return;
    }

    setSubmitting(false);
    setError('Credenziali non valide.');
  };

  if (!ready) {
    return (
      <div className="login-screen login-screen--apple-video" aria-hidden="true">
        <video
          ref={videoRef}
          src={activeBgVideo}
          className="login-bg-video login-bg-video--apple"
          autoPlay
          muted
          playsInline
          preload="auto"
          onEnded={onLoginVideoEnded}
        />
        <div className="login-bg-mask login-bg-mask--apple" />
        <div className="login-shell login-shell--apple-account login-shell--loading">
          <div className="login-brand-panel login-brand-panel--single">
            <p className="login-kicker">Apple Account Style</p>
            <h1>Accedi</h1>
            <p className="small login-loading-copy">Loading...</p>
          </div>
        </div>
      </div>
    );
  }

  if (!authenticated) {
    return (
      <div className="login-screen login-screen--apple-video">
        <video
          ref={videoRef}
          src={activeBgVideo}
          className="login-bg-video login-bg-video--apple"
          autoPlay
          muted
          playsInline
          preload="auto"
          onEnded={onLoginVideoEnded}
        />
        <div className="login-bg-mask login-bg-mask--apple" />

        <section className="login-shell login-shell--apple-account login-shell--single" aria-label="Accesso account">
          <aside className="login-brand-panel login-brand-panel--single">
            <div className={logoKick ? 'login-logo-stage kick' : 'login-logo-stage'}>
              <div className="login-logo-halo" />
              <div className="login-logo-seq" aria-hidden="true">
                <img src={layerA} alt="" className={showLayerA ? 'logo-layer active' : 'logo-layer'} />
                <img src={layerB} alt="" className={!showLayerA ? 'logo-layer active' : 'logo-layer'} />
              </div>
            </div>
            <h1>Accedi al tuo account</h1>
            <p className="small login-tagline">Usa il tuo account per continuare su Horizon Radar.</p>

            <div className="login-form-wrap login-form-wrap--apple-account">
              <form className="login-form" onSubmit={onSubmit}>
                <label>
                  Username
                  <input
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    autoComplete="username"
                    placeholder="admin"
                    disabled={submitting}
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
                    placeholder="Password"
                    disabled={submitting}
                  />
                </label>

                {error ? <p className="small login-error">{error}</p> : null}

                <button type="submit" disabled={submitting}>
                  {submitting ? 'Accesso...' : 'Continua'}
                </button>
              </form>
            </div>
          </aside>
        </section>
      </div>
    );
  }

  return <>{children}</>;
}
