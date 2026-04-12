export type CrmTag = {
  id: string;
  label: string;
  color: string;
  scope: 'company' | 'personal';
};

export type CrmContact = {
  id: string;
  firstName: string;
  lastName: string;
  email: string;
  phone: string;
  role: string;
  notes: string;
  company: string;
  subTagIds: string[];
  createdAt: string;
};

export type CompanyCallStatus =
  | 'DI_INTERESSE_CONTATTO'
  | 'NEL_CONSORZIO'
  | 'PRESENTATA'
  | 'FINANZIATA';

export type CompanyCall = {
  id: string;
  title: string;
  status: CompanyCallStatus;
  notes: string;
  contactId: string;
  comments: string[];
  attachments: Array<{
    id: string;
    name: string;
    contentType: string;
    size: number;
    dataUrl: string;
    uploadedAt: string;
  }>;
  createdAt: string;
};

export type CrmStore = {
  tags: CrmTag[];
  contacts: CrmContact[];
  companyTagIds: Record<string, string[]>;
  companyCalls: Record<string, CompanyCall[]>;
};

const CRM_STORE_KEY = 'horizon-radar-crm-store-v1';

function emptyStore(): CrmStore {
  return { tags: [], contacts: [], companyTagIds: {}, companyCalls: {} };
}

export function companyKey(name: string): string {
  return (name || '')
    .toLowerCase()
    .trim()
    .replace(/\s+/g, ' ')
    .replace(/[^a-z0-9 ]/g, '')
    .replace(/\s/g, '-');
}

export function readCrmStore(): CrmStore {
  if (typeof window === 'undefined') return emptyStore();
  try {
    const raw = localStorage.getItem(CRM_STORE_KEY);
    if (!raw) return emptyStore();
    const parsed = JSON.parse(raw) as Partial<CrmStore> & { contacts?: Array<Partial<CrmContact> & { tagIds?: string[] }> };

    const parsedTags = Array.isArray(parsed.tags) ? parsed.tags : [];
    const contactsRaw: Array<Partial<CrmContact> & { tagIds?: string[] }> =
      Array.isArray(parsed.contacts) ? (parsed.contacts as Array<Partial<CrmContact> & { tagIds?: string[] }>) : [];
    const companyTagIds: Record<string, string[]> =
      parsed.companyTagIds && typeof parsed.companyTagIds === 'object' ? parsed.companyTagIds : {};

    const contacts: CrmContact[] = contactsRaw.map((c) => {
      const legacyTagIds = Array.isArray(c.tagIds) ? c.tagIds : [];
      const key = companyKey(c.company || '');
      if (legacyTagIds.length > 0 && key) {
        companyTagIds[key] = [...new Set([...(companyTagIds[key] || []), ...legacyTagIds])];
      }
      return {
        id: c.id || makeId('person'),
        firstName: c.firstName || '',
        lastName: c.lastName || '',
        email: c.email || '',
        phone: c.phone || '',
        role: c.role || '',
        notes: c.notes || '',
        company: c.company || '',
        subTagIds: Array.isArray(c.subTagIds) ? c.subTagIds : [],
        createdAt: c.createdAt || new Date().toISOString(),
      };
    });

    const personalTagIdsInUse = new Set(contacts.flatMap((c) => c.subTagIds));
    const tags: CrmTag[] = parsedTags.map((t: Partial<CrmTag>) => {
      const inferredScope = personalTagIdsInUse.has(t.id || '') ? 'personal' : 'company';
      return {
        id: t.id || makeId('tag'),
        label: t.label || 'Tag',
        color: t.color || '#90caf9',
        scope: t.scope === 'personal' ? 'personal' : t.scope === 'company' ? 'company' : inferredScope,
      };
    });

    const rawCalls = parsed.companyCalls && typeof parsed.companyCalls === 'object' ? parsed.companyCalls : {};
    const companyCalls: Record<string, CompanyCall[]> = {};
    for (const [company, calls] of Object.entries(rawCalls as Record<string, Array<Partial<CompanyCall> & { status?: string }>>)) {
      companyCalls[company] = (Array.isArray(calls) ? calls : []).map((c) => {
        let status: CompanyCallStatus = 'DI_INTERESSE_CONTATTO';
        const rawStatus = (c.status || '') as string;
        if (rawStatus === 'NEL_CONSORZIO') status = 'NEL_CONSORZIO';
        if (rawStatus === 'PRESENTATA') status = 'PRESENTATA';
        if (rawStatus === 'FINANZIATA') status = 'FINANZIATA';
        if (rawStatus === 'interest' || rawStatus === 'negotiation') status = 'DI_INTERESSE_CONTATTO';
        return {
          id: c.id || makeId('call'),
          title: c.title || 'Call',
          status,
          notes: c.notes || '',
          contactId: typeof c.contactId === 'string' ? c.contactId : '',
          comments: Array.isArray(c.comments) ? c.comments.filter((x): x is string => typeof x === 'string') : [],
          attachments: Array.isArray(c.attachments)
            ? c.attachments.map((a: Partial<CompanyCall['attachments'][number]>) => ({
                id: a.id || makeId('file'),
                name: a.name || 'file',
                contentType: a.contentType || 'application/octet-stream',
                size: typeof a.size === 'number' ? a.size : 0,
                dataUrl: a.dataUrl || '',
                uploadedAt: a.uploadedAt || new Date().toISOString(),
              }))
            : [],
          createdAt: c.createdAt || new Date().toISOString(),
        };
      });
    }

    return {
      tags,
      contacts,
      companyTagIds,
      companyCalls,
    };
  } catch {
    return emptyStore();
  }
}

export function writeCrmStore(store: CrmStore): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(CRM_STORE_KEY, JSON.stringify(store));
}

export function makeId(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}-${Date.now()}`;
}
