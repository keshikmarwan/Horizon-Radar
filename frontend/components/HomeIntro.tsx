'use client';

import Image from 'next/image';
import { useMemo, useState } from 'react';

const INTRO_PLAYLIST = [
  '/videos/Intro.mp4',
  '/videos/intro2.mp4',
  '/videos/intro3.mp4',
  '/videos/intro4.mp4',
  '/videos/intro5.mp4',
];

export function HomeIntro() {
  const [isVisible, setIsVisible] = useState(true);
  const [activeIndex, setActiveIndex] = useState(0);

  const activeVideo = useMemo(() => INTRO_PLAYLIST[activeIndex] || INTRO_PLAYLIST[0], [activeIndex]);

  const onEnded = () => {
    setActiveIndex((prev) => (prev + 1) % INTRO_PLAYLIST.length);
  };

  if (!isVisible) return null;

  return (
    <div className="intro-overlay">
      <video
        key={activeVideo}
        className="intro-video"
        autoPlay
        muted
        playsInline
        onEnded={onEnded}
      >
        <source src={activeVideo} type="video/mp4" />
      </video>

      <div className="intro-mask" />

      <div className="intro-content">
        <Image src="/images/logo.png" alt="Horizon Radar Logo" width={110} height={110} className="intro-logo" />
        <h1 className="intro-title">Horizon Radar</h1>
        <p className="intro-subtitle">Intelligence for Horizon Europe calls</p>
        <div className="intro-actions">
          <button onClick={() => setIsVisible(false)}>Accedi alla home</button>
        </div>
      </div>
    </div>
  );
}
