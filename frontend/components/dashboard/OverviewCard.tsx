import type { ReactNode } from 'react';

type OverviewCardProps = {
  title: string;
  children: ReactNode;
};

export function OverviewCard({ title, children }: OverviewCardProps) {
  return (
    <article className="rd-opportunity-card">
      <h3>{title}</h3>
      {children}
    </article>
  );
}
