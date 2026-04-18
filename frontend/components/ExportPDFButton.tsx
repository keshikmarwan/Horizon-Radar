'use client';

import { useState } from 'react';
import { apiPostBlob } from '@/lib/api';
import type { HorizonMatcherExportPdfPayload, HorizonMatcherProfilePayload } from '@/lib/types';

type ExportPDFButtonProps = {
  clusterId: string;
  profile: HorizonMatcherProfilePayload;
  callIds?: string[];
  disabled?: boolean;
  className?: string;
  label?: string;
  includeAllCallsDefault?: boolean;
  topNDefault?: number;
  username?: string;
  onLoadingChange?: (loading: boolean) => void;
  onMessage?: (message: string, level?: 'success' | 'error' | 'info') => void;
};

function guessFilename(clusterId: string): string {
  const ts = new Date().toISOString().replace(/[:.]/g, '-');
  return `Generative-Bionics-Horizon-Report-${clusterId}-${ts}.pdf`;
}

export function ExportPDFButton({
  clusterId,
  profile,
  callIds,
  disabled,
  className,
  label,
  includeAllCallsDefault = false,
  topNDefault = 15,
  username,
  onLoadingChange,
  onMessage,
}: ExportPDFButtonProps) {
  const [isExporting, setIsExporting] = useState(false);

  const triggerDownload = (blob: Blob, name: string) => {
    const href = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = href;
    anchor.download = name;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(href), 800);
  };

  const handleExport = async () => {
    if (isExporting || disabled) return;
    setIsExporting(true);
    onLoadingChange?.(true);
    onMessage?.('Generazione report PDF in corso…', 'info');

    try {
      const payload: HorizonMatcherExportPdfPayload = {
        clusterId,
        profile,
        callIds: callIds && callIds.length > 0 ? callIds : null,
        include_all_calls: includeAllCallsDefault,
        top_n: topNDefault,
        username,
      };

      const { blob, filename } = await apiPostBlob('/api/horizon-matcher/export-pdf', payload);
      const fileName = filename || guessFilename(clusterId);
      triggerDownload(blob, fileName);
      onMessage?.('Report generato con successo', 'success');
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      onMessage?.(`Errore export PDF: ${msg}`, 'error');
    } finally {
      setIsExporting(false);
      onLoadingChange?.(false);
    }
  };

  return (
    <button
      type="button"
      className={className || 'fit-btn-secondary'}
      onClick={() => { void handleExport(); }}
      disabled={Boolean(disabled) || isExporting}
      aria-busy={isExporting}
    >
      <span aria-hidden style={{ display: 'inline-flex', marginRight: 8 }}>
        <svg width="16" height="16" viewBox="0 0 20 20" fill="none">
          <path d="M10 2.5v9m0 0L6.5 8M10 11.5L13.5 8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"/>
          <path d="M3.5 12.5v2A2 2 0 0 0 5.5 16.5h9a2 2 0 0 0 2-2v-2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round"/>
        </svg>
      </span>
      {isExporting ? 'Generazione PDF…' : (label || 'Esporta Report PDF')}
    </button>
  );
}
