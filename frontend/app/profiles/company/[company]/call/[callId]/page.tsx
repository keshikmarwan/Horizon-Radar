'use client';

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { ChangeEvent, useEffect, useMemo, useState } from 'react';
import { CompanyCallStatus, CrmStore, readCrmStore, writeCrmStore } from '@/lib/crm-store';

const STATUSES: CompanyCallStatus[] = [
  'DI_INTERESSE_CONTATTO',
  'NEL_CONSORZIO',
  'PRESENTATA',
  'FINANZIATA',
];

export default function CompanyCallDetailPage() {
  const params = useParams<{ company: string; callId: string }>();
  const router = useRouter();
  const companyParam = (params.company || '').toLowerCase();
  const callId = params.callId || '';

  const [store, setStore] = useState<CrmStore>({ tags: [], contacts: [], companyTagIds: {}, companyCalls: {} });
  const [isHydrated, setIsHydrated] = useState(false);
  const [newComment, setNewComment] = useState('');

  useEffect(() => {
    setStore(readCrmStore());
    setIsHydrated(true);
  }, []);

  useEffect(() => {
    if (!isHydrated) return;
    writeCrmStore(store);
  }, [store, isHydrated]);

  const call = useMemo(
    () => (store.companyCalls[companyParam] || []).find((c) => c.id === callId) || null,
    [store.companyCalls, companyParam, callId],
  );

  const contact = useMemo(
    () => store.contacts.find((c) => c.id === call?.contactId) || null,
    [store.contacts, call?.contactId],
  );

  const updateCall = (updater: (current: NonNullable<typeof call>) => NonNullable<typeof call>) => {
    if (!call) return;
    setStore((prev) => ({
      ...prev,
      companyCalls: {
        ...prev.companyCalls,
        [companyParam]: (prev.companyCalls[companyParam] || []).map((c) => (c.id === callId ? updater(c) : c)),
      },
    }));
  };

  const addComment = () => {
    const clean = newComment.trim();
    if (!clean || !call) return;
    updateCall((current) => ({ ...current, comments: [...current.comments, clean] }));
    setNewComment('');
  };

  const removeComment = (index: number) => {
    if (!call) return;
    updateCall((current) => ({
      ...current,
      comments: current.comments.filter((_, idx) => idx !== index),
    }));
  };

  const onUploadAttachment = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || !call) return;

    const dataUrl = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ''));
      reader.onerror = () => reject(new Error('file-read-error'));
      reader.readAsDataURL(file);
    });

    updateCall((current) => ({
      ...current,
      attachments: [
        ...current.attachments,
        {
          id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
          name: file.name,
          contentType: file.type || 'application/octet-stream',
          size: file.size,
          dataUrl,
          uploadedAt: new Date().toISOString(),
        },
      ],
    }));
    event.target.value = '';
  };

  const removeAttachment = (attachmentId: string) => {
    if (!call) return;
    updateCall((current) => ({
      ...current,
      attachments: current.attachments.filter((a) => a.id !== attachmentId),
    }));
  };

  const deleteCall = () => {
    if (!call) return;
    const ok = window.confirm(`Eliminare la call "${call.title}"?`);
    if (!ok) return;
    setStore((prev) => ({
      ...prev,
      companyCalls: {
        ...prev.companyCalls,
        [companyParam]: (prev.companyCalls[companyParam] || []).filter((c) => c.id !== callId),
      },
    }));
    router.push(`/profiles/company/${companyParam}`);
  };

  if (!call) {
    return (
      <section>
        <h1>Call non trovata</h1>
        <Link href={`/profiles/company/${companyParam}`}>Torna alla scheda azienda</Link>
      </section>
    );
  }

  return (
    <section>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h1>{call.title}</h1>
        <Link href={`/profiles/company/${companyParam}`}>Torna alla scheda azienda</Link>
      </div>

      <div className="card">
        <p><strong>Stato:</strong></p>
        <select value={call.status} onChange={(e) => updateCall((current) => ({ ...current, status: e.target.value as CompanyCallStatus }))}>
          {STATUSES.map((status) => (
            <option key={status} value={status}>{status}</option>
          ))}
        </select>
        <p style={{ marginTop: '0.8rem' }}><strong>Persona associata:</strong> {contact ? `${contact.firstName} ${contact.lastName}` : 'N/A'}</p>
        <p><strong>Note:</strong></p>
        <textarea
          rows={5}
          style={{ width: '100%' }}
          value={call.notes}
          onChange={(e) => updateCall((current) => ({ ...current, notes: e.target.value }))}
        />
        <div className="row" style={{ marginTop: '0.8rem' }}>
          <button className="btn-danger" onClick={deleteCall}>Elimina call</button>
        </div>
      </div>

      <div className="card">
        <h3>Commenti</h3>
        <div className="row">
          <input
            placeholder="Nuovo commento"
            value={newComment}
            onChange={(e) => setNewComment(e.target.value)}
            style={{ minWidth: 320 }}
          />
          <button onClick={addComment}>Aggiungi commento</button>
        </div>
        <div style={{ marginTop: '0.8rem' }}>
          {call.comments.length === 0 ? <p className="small">Nessun commento.</p> : null}
          {call.comments.map((comment, index) => (
            <div key={`${index}-${comment}`} className="card">
              <p>{comment}</p>
              <button className="btn-danger" onClick={() => removeComment(index)}>Elimina commento</button>
            </div>
          ))}
        </div>
      </div>

      <div className="card">
        <h3>File allegati</h3>
        <div className="row">
          <input type="file" onChange={(e) => { void onUploadAttachment(e); }} />
        </div>
        <div style={{ marginTop: '0.8rem' }}>
          {call.attachments.length === 0 ? <p className="small">Nessun file allegato.</p> : null}
          {call.attachments.map((attachment) => (
            <div key={attachment.id} className="card">
              <p><strong>{attachment.name}</strong></p>
              <p className="small">{attachment.contentType} - {Math.round(attachment.size / 1024)} KB</p>
              <div className="row">
                <a className="link-btn" href={attachment.dataUrl} download={attachment.name}>Scarica</a>
                <button className="btn-danger" onClick={() => removeAttachment(attachment.id)}>Elimina file</button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
