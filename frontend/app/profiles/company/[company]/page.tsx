'use client';

import Link from 'next/link';
import { useParams } from 'next/navigation';
import { useEffect, useMemo, useState } from 'react';
import {
  companyKey,
  CompanyCall,
  CompanyCallStatus,
  CrmContact,
  CrmStore,
  CrmTag,
  makeId,
  readCrmStore,
  writeCrmStore,
} from '@/lib/crm-store';

type CallForm = {
  title: string;
  status: CompanyCallStatus;
  notes: string;
  contactId: string;
};

type EditForm = {
  firstName: string;
  lastName: string;
  email: string;
  phone: string;
  role: string;
  notes: string;
};

const defaultCallForm: CallForm = {
  title: '',
  status: 'DI_INTERESSE_CONTATTO',
  notes: '',
  contactId: '',
};

const TAG_COLORS = ['#2a2a2a', '#3a3a3a', '#4a4a4a', '#5a5a5a', '#6a6a6a', '#7a7a7a', '#8a8a8a'];

export default function CompanyDetailPage() {
  const params = useParams<{ company: string }>();
  const companyParam = (params.company || '').toLowerCase();
  const [store, setStore] = useState<CrmStore>({ tags: [], contacts: [], companyTagIds: {}, companyCalls: {} });
  const [isHydrated, setIsHydrated] = useState(false);
  const [callForm, setCallForm] = useState<CallForm>(defaultCallForm);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<EditForm | null>(null);
  const [newTagLabel, setNewTagLabel] = useState('');
  const [newTagColor, setNewTagColor] = useState(TAG_COLORS[0]);
  const [personalTagContactId, setPersonalTagContactId] = useState<string | null>(null);
  const [personalTagLabel, setPersonalTagLabel] = useState('');
  const [personalTagColor, setPersonalTagColor] = useState('#5a5a5a');
  const companyTags = useMemo(() => store.tags.filter((t) => t.scope === 'company'), [store.tags]);
  const personalTags = useMemo(() => store.tags.filter((t) => t.scope === 'personal'), [store.tags]);

  useEffect(() => {
    setStore(readCrmStore());
    setIsHydrated(true);
  }, []);

  useEffect(() => {
    if (!isHydrated) return;
    writeCrmStore(store);
  }, [store, isHydrated]);

  const contacts = useMemo<CrmContact[]>(
    () => store.contacts.filter((c) => companyKey(c.company) === companyParam),
    [store.contacts, companyParam],
  );

  const companyName = contacts[0]?.company || companyParam || 'Azienda';
  const companyTagMap = useMemo(() => {
    const map = new Map<string, CrmTag>();
    const ids = store.companyTagIds[companyParam] || [];
    for (const tagId of ids) {
      const t = store.tags.find((x) => x.id === tagId);
      if (t) map.set(t.id, t);
    }
    return map;
  }, [companyParam, store.companyTagIds, store.tags]);

  const calls = store.companyCalls[companyParam] || [];
  const callDiInteresse = calls.filter((c) => c.status === 'DI_INTERESSE_CONTATTO');
  const callNelConsorzio = calls.filter((c) => c.status === 'NEL_CONSORZIO');
  const callPresentata = calls.filter((c) => c.status === 'PRESENTATA');
  const callFinanziata = calls.filter((c) => c.status === 'FINANZIATA');

  const addCall = () => {
    const title = callForm.title.trim();
    if (!title || !companyParam) return;
    const next: CompanyCall = {
      id: makeId('call'),
      title,
      status: callForm.status,
      notes: callForm.notes.trim(),
      contactId: callForm.contactId,
      comments: [],
      attachments: [],
      createdAt: new Date().toISOString(),
    };
    setStore((prev) => ({
      ...prev,
      companyCalls: {
        ...prev.companyCalls,
        [companyParam]: [next, ...(prev.companyCalls[companyParam] || [])],
      },
    }));
    setCallForm(defaultCallForm);
  };

  const moveCall = (callId: string, status: CompanyCallStatus) => {
    setStore((prev) => ({
      ...prev,
      companyCalls: {
        ...prev.companyCalls,
        [companyParam]: (prev.companyCalls[companyParam] || []).map((c) => (c.id === callId ? { ...c, status } : c)),
      },
    }));
  };

  const deleteCall = (callId: string) => {
    setStore((prev) => ({
      ...prev,
      companyCalls: {
        ...prev.companyCalls,
        [companyParam]: (prev.companyCalls[companyParam] || []).filter((c) => c.id !== callId),
      },
    }));
  };

  const addTag = () => {
    const label = newTagLabel.trim();
    if (!label) return;
    const existing = store.tags.find((t) => t.label.toLowerCase() === label.toLowerCase() && t.scope === 'company');
    if (!existing) {
      const next: CrmTag = { id: makeId('tag'), label, color: newTagColor, scope: 'company' };
      setStore((prev) => ({ ...prev, tags: [...prev.tags, next] }));
    }
    setNewTagLabel('');
  };

  const startPersonalTag = (contactId: string) => {
    setPersonalTagContactId(contactId);
    setPersonalTagLabel('');
    setPersonalTagColor('#5a5a5a');
  };

  const cancelPersonalTag = () => {
    setPersonalTagContactId(null);
    setPersonalTagLabel('');
    setPersonalTagColor('#5a5a5a');
  };

  const createAndAssignPersonalTag = (contactId: string) => {
    const clean = personalTagLabel.trim();
    if (!clean) return;

    setStore((prev) => {
      let tagId = prev.tags.find((t) => t.label.toLowerCase() === clean.toLowerCase())?.id;
      let nextTags = prev.tags;
      if (!tagId) {
        const created: CrmTag = { id: makeId('tag'), label: clean, color: personalTagColor, scope: 'personal' };
        tagId = created.id;
        nextTags = [...prev.tags, created];
      }

      return {
        ...prev,
        tags: nextTags,
        contacts: prev.contacts.map((c) => {
          if (c.id !== contactId) return c;
          if (c.subTagIds.includes(tagId!)) return c;
          return { ...c, subTagIds: [...c.subTagIds, tagId!] };
        }),
      };
    });
    cancelPersonalTag();
  };

  const toggleCompanyTag = (tagId: string) => {
    setStore((prev) => ({
      ...prev,
      companyTagIds: {
        ...prev.companyTagIds,
        [companyParam]: (prev.companyTagIds[companyParam] || []).includes(tagId)
          ? (prev.companyTagIds[companyParam] || []).filter((x) => x !== tagId)
          : [...(prev.companyTagIds[companyParam] || []), tagId],
      },
    }));
  };

  const togglePersonTag = (contactId: string, tagId: string) => {
    setStore((prev) => ({
      ...prev,
      contacts: prev.contacts.map((c) => {
        if (c.id !== contactId) return c;
        const has = c.subTagIds.includes(tagId);
        return {
          ...c,
          subTagIds: has ? c.subTagIds.filter((x) => x !== tagId) : [...c.subTagIds, tagId],
        };
      }),
    }));
  };

  const startEdit = (c: CrmContact) => {
    setEditingId(c.id);
    setEditForm({
      firstName: c.firstName,
      lastName: c.lastName,
      email: c.email,
      phone: c.phone,
      role: c.role,
      notes: c.notes,
    });
  };

  const saveEdit = () => {
    if (!editingId || !editForm) return;
    setStore((prev) => ({
      ...prev,
      contacts: prev.contacts.map((c) => {
        if (c.id !== editingId) return c;
        return {
          ...c,
          firstName: editForm.firstName.trim(),
          lastName: editForm.lastName.trim(),
          email: editForm.email.trim(),
          phone: editForm.phone.trim(),
          role: editForm.role.trim(),
          notes: editForm.notes.trim(),
        };
      }),
    }));
    setEditingId(null);
    setEditForm(null);
  };

  const deleteContact = (contactId: string) => {
    setStore((prev) => ({
      ...prev,
      contacts: prev.contacts.filter((c) => c.id !== contactId),
    }));
    if (editingId === contactId) {
      setEditingId(null);
      setEditForm(null);
    }
  };

  return (
    <section>
      <div className="row" style={{ justifyContent: 'space-between' }}>
        <h1>Scheda Azienda: {companyName}</h1>
        <Link href="/profiles">Torna a Profiles</Link>
      </div>

      <div className="card">
        <h3>Tag azienda</h3>
        <div className="row" style={{ marginBottom: '0.7rem' }}>
          <input placeholder="Nuovo tag" value={newTagLabel} onChange={(e) => setNewTagLabel(e.target.value)} />
          <input
            type="color"
            value={newTagColor}
            onChange={(e) => setNewTagColor(e.target.value)}
            style={{ width: 48, padding: 0 }}
          />
          <button onClick={addTag}>Crea tag</button>
        </div>
        <div className="row">
          {companyTags.length === 0 ? <span className="small">Nessun tag.</span> : null}
          {companyTags.map((t) => {
            const selected = companyTagMap.has(t.id);
            return (
              <button
                key={t.id}
                onClick={() => toggleCompanyTag(t.id)}
                style={{
                  background: selected ? t.color : '#111111',
                  color: '#f5f5f5',
                  border: `1px solid ${t.color}`,
                }}
              >
                {t.label}
              </button>
            );
          })}
        </div>
      </div>

      <div className="card">
        <h3>Contatti completi</h3>
        {contacts.length === 0 ? (
          <p className="small">Nessun contatto trovato per questa azienda.</p>
        ) : (
          contacts.map((c) => {
            const isEditing = editingId === c.id;
            return (
              <article className="card" key={c.id}>
                {isEditing && editForm ? (
                  <>
                    <div className="row">
                      <input value={editForm.firstName} onChange={(e) => setEditForm({ ...editForm, firstName: e.target.value })} placeholder="Nome" />
                      <input value={editForm.lastName} onChange={(e) => setEditForm({ ...editForm, lastName: e.target.value })} placeholder="Cognome" />
                      <input value={editForm.email} onChange={(e) => setEditForm({ ...editForm, email: e.target.value })} placeholder="Email" />
                    </div>
                    <div className="row" style={{ marginTop: '0.5rem' }}>
                      <input value={editForm.phone} onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })} placeholder="Telefono" />
                      <input value={editForm.role} onChange={(e) => setEditForm({ ...editForm, role: e.target.value })} placeholder="Posizione" />
                      <input value={editForm.notes} onChange={(e) => setEditForm({ ...editForm, notes: e.target.value })} placeholder="Note" style={{ minWidth: 220 }} />
                    </div>
                  </>
                ) : (
                  <>
                    <p><strong>Nome:</strong> {c.firstName} {c.lastName}</p>
                    <p><strong>Email:</strong> {c.email || 'N/A'}</p>
                    <p><strong>Telefono:</strong> {c.phone || 'N/A'}</p>
                    <p><strong>Posizione:</strong> {c.role || 'N/A'}</p>
                    <p><strong>Note:</strong> {c.notes || 'N/A'}</p>
                  </>
                )}

                <p className="small"><strong>Inserito:</strong> {new Date(c.createdAt).toLocaleString()}</p>

                <p className="small"><strong>Sottotag persona:</strong></p>
                <div className="row" style={{ marginBottom: '0.6rem' }}>
                  {personalTags.length === 0 ? <span className="small">Nessun sottotag.</span> : null}
                  {personalTags.map((t) => {
                    const selected = c.subTagIds.includes(t.id);
                    return (
                      <button
                        key={t.id}
                        onClick={() => togglePersonTag(c.id, t.id)}
                        style={{
                          background: selected ? t.color : '#111111',
                          color: '#f5f5f5',
                          border: `1px solid ${t.color}`,
                        }}
                      >
                        {t.label}
                      </button>
                    );
                  })}
                  {personalTagContactId === c.id ? (
                    <>
                      <input
                        placeholder="Nome sottotag"
                        value={personalTagLabel}
                        onChange={(e) => setPersonalTagLabel(e.target.value)}
                        style={{ minWidth: 180 }}
                      />
                      <input
                        type="color"
                        value={personalTagColor}
                        onChange={(e) => setPersonalTagColor(e.target.value)}
                        style={{ width: 48, padding: 0 }}
                      />
                      <button className="btn-soft" onClick={() => createAndAssignPersonalTag(c.id)}>
                        Salva sottotag
                      </button>
                      <button className="btn-soft" onClick={cancelPersonalTag}>
                        Annulla
                      </button>
                    </>
                  ) : (
                    <button className="btn-soft" onClick={() => startPersonalTag(c.id)}>
                      Crea e assegna sottotag
                    </button>
                  )}
                </div>

                <div className="row">
                  {isEditing ? (
                    <>
                      <button onClick={saveEdit}>Salva modifica</button>
                      <button className="btn-soft" onClick={() => { setEditingId(null); setEditForm(null); }}>Annulla</button>
                    </>
                  ) : (
                    <button onClick={() => startEdit(c)}>Modifica</button>
                  )}
                  <button className="btn-danger" onClick={() => deleteContact(c.id)}>Elimina</button>
                </div>
              </article>
            );
          })
        )}
      </div>

      <div className="card">
        <h3>Call con questa azienda</h3>
        <div className="row">
          <input
            placeholder="Titolo call"
            value={callForm.title}
            onChange={(e) => setCallForm((prev) => ({ ...prev, title: e.target.value }))}
          />
          <select
            value={callForm.contactId}
            onChange={(e) => setCallForm((prev) => ({ ...prev, contactId: e.target.value }))}
          >
            <option value="">Seleziona persona</option>
            {contacts.map((c) => (
              <option key={c.id} value={c.id}>
                {c.firstName} {c.lastName}
              </option>
            ))}
          </select>
          <select
            value={callForm.status}
            onChange={(e) => setCallForm((prev) => ({ ...prev, status: e.target.value as CompanyCallStatus }))}
          >
            <option value="DI_INTERESSE_CONTATTO">DI INTERESSE/CONTATTO</option>
            <option value="NEL_CONSORZIO">NEL CONSORZIO</option>
            <option value="PRESENTATA">PRESENTATA</option>
            <option value="FINANZIATA">FINANZIATA</option>
          </select>
          <input
            placeholder="Note (opzionale)"
            value={callForm.notes}
            onChange={(e) => setCallForm((prev) => ({ ...prev, notes: e.target.value }))}
            style={{ minWidth: 280 }}
          />
          <button onClick={addCall}>Aggiungi call</button>
        </div>

        <div className="row" style={{ alignItems: 'flex-start', marginTop: '0.8rem' }}>
          <article className="card" style={{ flex: 1, minWidth: 280 }}>
            <h4>DI INTERESSE/CONTATTO</h4>
            {callDiInteresse.length === 0 ? <p className="small">Nessuna call.</p> : null}
            {callDiInteresse.map((c) => (
              <div key={c.id} className="card">
                <p className="small"><strong>{c.title}</strong>{c.notes ? ` - ${c.notes}` : ''}</p>
                <p className="small">
                  <strong>Persona:</strong> {contacts.find((x) => x.id === c.contactId) ? `${contacts.find((x) => x.id === c.contactId)?.firstName} ${contacts.find((x) => x.id === c.contactId)?.lastName}` : 'N/A'}
                </p>
                <div className="row">
                  <Link className="link-btn" href={`/profiles/company/${companyParam}/call/${c.id}`} target="_blank">Apri</Link>
                  <select value={c.status} onChange={(e) => moveCall(c.id, e.target.value as CompanyCallStatus)}>
                    <option value="DI_INTERESSE_CONTATTO">DI INTERESSE/CONTATTO</option>
                    <option value="NEL_CONSORZIO">NEL CONSORZIO</option>
                    <option value="PRESENTATA">PRESENTATA</option>
                    <option value="FINANZIATA">FINANZIATA</option>
                  </select>
                  <button className="btn-danger" onClick={() => deleteCall(c.id)}>Elimina</button>
                </div>
              </div>
            ))}
          </article>
          <article className="card" style={{ flex: 1, minWidth: 280 }}>
            <h4>NEL CONSORZIO</h4>
            {callNelConsorzio.length === 0 ? <p className="small">Nessuna call.</p> : null}
            {callNelConsorzio.map((c) => (
              <div key={c.id} className="card">
                <p className="small"><strong>{c.title}</strong>{c.notes ? ` - ${c.notes}` : ''}</p>
                <p className="small">
                  <strong>Persona:</strong> {contacts.find((x) => x.id === c.contactId) ? `${contacts.find((x) => x.id === c.contactId)?.firstName} ${contacts.find((x) => x.id === c.contactId)?.lastName}` : 'N/A'}
                </p>
                <div className="row">
                  <Link className="link-btn" href={`/profiles/company/${companyParam}/call/${c.id}`} target="_blank">Apri</Link>
                  <select value={c.status} onChange={(e) => moveCall(c.id, e.target.value as CompanyCallStatus)}>
                    <option value="DI_INTERESSE_CONTATTO">DI INTERESSE/CONTATTO</option>
                    <option value="NEL_CONSORZIO">NEL CONSORZIO</option>
                    <option value="PRESENTATA">PRESENTATA</option>
                    <option value="FINANZIATA">FINANZIATA</option>
                  </select>
                  <button className="btn-danger" onClick={() => deleteCall(c.id)}>Elimina</button>
                </div>
              </div>
            ))}
          </article>
          <article className="card" style={{ flex: 1, minWidth: 280 }}>
            <h4>PRESENTATA</h4>
            {callPresentata.length === 0 ? <p className="small">Nessuna call.</p> : null}
            {callPresentata.map((c) => (
              <div key={c.id} className="card">
                <p className="small"><strong>{c.title}</strong>{c.notes ? ` - ${c.notes}` : ''}</p>
                <p className="small">
                  <strong>Persona:</strong> {contacts.find((x) => x.id === c.contactId) ? `${contacts.find((x) => x.id === c.contactId)?.firstName} ${contacts.find((x) => x.id === c.contactId)?.lastName}` : 'N/A'}
                </p>
                <div className="row">
                  <Link className="link-btn" href={`/profiles/company/${companyParam}/call/${c.id}`} target="_blank">Apri</Link>
                  <select value={c.status} onChange={(e) => moveCall(c.id, e.target.value as CompanyCallStatus)}>
                    <option value="DI_INTERESSE_CONTATTO">DI INTERESSE/CONTATTO</option>
                    <option value="NEL_CONSORZIO">NEL CONSORZIO</option>
                    <option value="PRESENTATA">PRESENTATA</option>
                    <option value="FINANZIATA">FINANZIATA</option>
                  </select>
                  <button className="btn-danger" onClick={() => deleteCall(c.id)}>Elimina</button>
                </div>
              </div>
            ))}
          </article>
          <article className="card" style={{ flex: 1, minWidth: 280 }}>
            <h4>FINANZIATA</h4>
            {callFinanziata.length === 0 ? <p className="small">Nessuna call.</p> : null}
            {callFinanziata.map((c) => (
              <div key={c.id} className="card">
                <p className="small"><strong>{c.title}</strong>{c.notes ? ` - ${c.notes}` : ''}</p>
                <p className="small">
                  <strong>Persona:</strong> {contacts.find((x) => x.id === c.contactId) ? `${contacts.find((x) => x.id === c.contactId)?.firstName} ${contacts.find((x) => x.id === c.contactId)?.lastName}` : 'N/A'}
                </p>
                <div className="row">
                  <Link className="link-btn" href={`/profiles/company/${companyParam}/call/${c.id}`} target="_blank">Apri</Link>
                  <select value={c.status} onChange={(e) => moveCall(c.id, e.target.value as CompanyCallStatus)}>
                    <option value="DI_INTERESSE_CONTATTO">DI INTERESSE/CONTATTO</option>
                    <option value="NEL_CONSORZIO">NEL CONSORZIO</option>
                    <option value="PRESENTATA">PRESENTATA</option>
                    <option value="FINANZIATA">FINANZIATA</option>
                  </select>
                  <button className="btn-danger" onClick={() => deleteCall(c.id)}>Elimina</button>
                </div>
              </div>
            ))}
          </article>
        </div>
      </div>
    </section>
  );
}
