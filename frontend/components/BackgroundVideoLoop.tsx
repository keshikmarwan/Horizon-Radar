'use client';

import { useEffect, useMemo, useRef, useState } from 'react';

const BACKGROUND_PLAYLIST = [
  '/videos/gb-bg/hero1.mp4',
  '/videos/gb-bg/motion.mp4',
  '/videos/gb-bg/main1.mp4',
  '/videos/gb-bg/main2.mp4',
  '/videos/gb-bg/openplat.mp4',
  '/videos/gb-bg/touch3.mp4',
  '/videos/gb-bg/teaser.mp4',
];

export function BackgroundVideoLoop() {
  const [activeIndex, setActiveIndex] = useState(0);
  const [repeatCount, setRepeatCount] = useState(0);
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const source = useMemo(
    () => BACKGROUND_PLAYLIST[activeIndex] || BACKGROUND_PLAYLIST[0],
    [activeIndex],
  );

  useEffect(() => {
    if (!videoRef.current) return;
    // Slow down playback for a less hectic background cadence.
    videoRef.current.playbackRate = 0.78;
    void videoRef.current.play().catch(() => {});
  }, [source]);

  const onEnded = () => {
    const video = videoRef.current;
    if (!video) return;

    // Keep each clip for two cycles before moving to the next.
    if (repeatCount < 1) {
      setRepeatCount((prev) => prev + 1);
      video.currentTime = 0;
      void video.play().catch(() => {});
      return;
    }

    setRepeatCount(0);
    setActiveIndex((idx) => (idx + 1) % BACKGROUND_PLAYLIST.length);
  };

  const onError = () => {
    // Skip broken clips and continue playlist.
    setRepeatCount(0);
    setActiveIndex((idx) => (idx + 1) % BACKGROUND_PLAYLIST.length);
  };

  return (
    <div className="gb-bg-video-layer" aria-hidden="true">
      <video
        ref={videoRef}
        key={source}
        className="gb-bg-video"
        autoPlay
        muted
        playsInline
        preload="auto"
        onEnded={onEnded}
        onError={onError}
      >
        <source src={source} type="video/mp4" />
      </video>
      <div className="gb-bg-overlay" />
    </div>
  );
}
