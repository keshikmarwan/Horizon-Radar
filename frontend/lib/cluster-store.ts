export type ClusterId = 'CL1' | 'CL2' | 'CL3' | 'CL4' | 'CL5' | 'CL6';

export type ClusterData = {
  fileName: string;
  fileType: string;
  uploadedAt: string;
  fileText: string;
  extractedBy?: string;
  extractedChars?: number;
  extractionError?: string;
  companyDescription: string;
  clusterInterests: string;
};

export type ClusterStore = {
  clusterData: Partial<Record<ClusterId, ClusterData>>;
};

export type ClusterInstanceMeta = {
  id: string;
  name: string;
  createdAt: string;
  updatedAt: string;
};

type ClusterIndex = {
  instances: ClusterInstanceMeta[];
};

export const CLUSTERS: ClusterId[] = ['CL1', 'CL2', 'CL3', 'CL4', 'CL5', 'CL6'];
export const STORAGE_KEY = 'horizon-radar-clusters';

const INSTANCE_INDEX_KEY = 'horizon-radar-cluster-instances-v1';
const ACTIVE_INSTANCE_KEY = 'horizon-radar-cluster-active-instance-v1';
const INSTANCE_PREFIX = 'horizon-radar-cluster-instance-v1:';

export function emptyClusterStore(): ClusterStore {
  return { clusterData: {} };
}

function makeId(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}-${Date.now()}`;
}

export function defaultInstanceName(): string {
  return new Date().toISOString().replace('T', ' ').slice(0, 19);
}

function readIndex(): ClusterIndex {
  if (typeof window === 'undefined') return { instances: [] };
  try {
    const raw = localStorage.getItem(INSTANCE_INDEX_KEY);
    if (!raw) return { instances: [] };
    const parsed = JSON.parse(raw) as Partial<ClusterIndex>;
    return { instances: Array.isArray(parsed.instances) ? parsed.instances : [] };
  } catch {
    return { instances: [] };
  }
}

function writeIndex(index: ClusterIndex): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(INSTANCE_INDEX_KEY, JSON.stringify(index));
}

function readStoreById(instanceId: string): ClusterStore {
  if (typeof window === 'undefined') return emptyClusterStore();
  try {
    const raw = localStorage.getItem(`${INSTANCE_PREFIX}${instanceId}`);
    if (!raw) return emptyClusterStore();
    const parsed = JSON.parse(raw) as ClusterStore;
    return { clusterData: parsed.clusterData || {} };
  } catch {
    return emptyClusterStore();
  }
}

function writeStoreById(instanceId: string, store: ClusterStore): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(`${INSTANCE_PREFIX}${instanceId}`, JSON.stringify(store));
}

export function listClusterInstances(): ClusterInstanceMeta[] {
  return readIndex().instances.sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
}

export function getActiveClusterInstanceId(): string | null {
  if (typeof window === 'undefined') return null;
  return localStorage.getItem(ACTIVE_INSTANCE_KEY);
}

export function setActiveClusterInstanceId(instanceId: string): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(ACTIVE_INSTANCE_KEY, instanceId);
}

export function ensureClusterWorkspace(): { instanceId: string; store: ClusterStore; instances: ClusterInstanceMeta[] } {
  let index = readIndex();

  if (index.instances.length === 0) {
    let migrated = emptyClusterStore();
    try {
      const legacy = localStorage.getItem(STORAGE_KEY);
      if (legacy) {
        const parsed = JSON.parse(legacy) as ClusterStore;
        migrated = { clusterData: parsed.clusterData || {} };
      }
    } catch {
      migrated = emptyClusterStore();
    }

    const now = new Date().toISOString();
    const first: ClusterInstanceMeta = {
      id: makeId('instance'),
      name: defaultInstanceName(),
      createdAt: now,
      updatedAt: now,
    };
    index = { instances: [first] };
    writeIndex(index);
    writeStoreById(first.id, migrated);
    setActiveClusterInstanceId(first.id);
  }

  const active = getActiveClusterInstanceId();
  const fallback = index.instances[0].id;
  const instanceId = index.instances.some((x) => x.id === active) && active ? active : fallback;
  setActiveClusterInstanceId(instanceId);

  return {
    instanceId,
    store: readStoreById(instanceId),
    instances: listClusterInstances(),
  };
}

export function readClusterStore(instanceId?: string): ClusterStore {
  const id = instanceId || getActiveClusterInstanceId();
  if (!id) return emptyClusterStore();
  return readStoreById(id);
}

export function writeClusterStore(store: ClusterStore, instanceId?: string): void {
  const id = instanceId || getActiveClusterInstanceId();
  if (!id) return;
  writeStoreById(id, store);
  const index = readIndex();
  const now = new Date().toISOString();
  index.instances = index.instances.map((m) => (m.id === id ? { ...m, updatedAt: now } : m));
  writeIndex(index);
}

export function renameClusterInstance(instanceId: string, name: string): void {
  const clean = name.trim();
  if (!clean) return;
  const index = readIndex();
  const now = new Date().toISOString();
  index.instances = index.instances.map((m) => (m.id === instanceId ? { ...m, name: clean, updatedAt: now } : m));
  writeIndex(index);
}

export function switchClusterInstance(instanceId: string): ClusterStore {
  setActiveClusterInstanceId(instanceId);
  return readStoreById(instanceId);
}

export function createClusterInstance(name: string): { instanceId: string; store: ClusterStore } {
  const now = new Date().toISOString();
  const instanceId = makeId('instance');
  const meta: ClusterInstanceMeta = {
    id: instanceId,
    name: name.trim() || defaultInstanceName(),
    createdAt: now,
    updatedAt: now,
  };
  const index = readIndex();
  index.instances = [meta, ...index.instances];
  writeIndex(index);
  const store = emptyClusterStore();
  writeStoreById(instanceId, store);
  setActiveClusterInstanceId(instanceId);
  return { instanceId, store };
}

export function deleteClusterInstance(instanceId: string): { instanceId: string; store: ClusterStore; instances: ClusterInstanceMeta[] } {
  const index = readIndex();
  const exists = index.instances.some((x) => x.id === instanceId);
  if (!exists) {
    return ensureClusterWorkspace();
  }

  if (typeof window !== 'undefined') {
    localStorage.removeItem(`${INSTANCE_PREFIX}${instanceId}`);
  }

  let nextInstances = index.instances.filter((x) => x.id !== instanceId);
  if (nextInstances.length === 0) {
    const now = new Date().toISOString();
    const fallback: ClusterInstanceMeta = {
      id: makeId('instance'),
      name: defaultInstanceName(),
      createdAt: now,
      updatedAt: now,
    };
    nextInstances = [fallback];
    writeStoreById(fallback.id, emptyClusterStore());
  }

  writeIndex({ instances: nextInstances });

  const active = getActiveClusterInstanceId();
  const newActive = active === instanceId ? nextInstances[0].id : (active && nextInstances.some((x) => x.id === active) ? active : nextInstances[0].id);
  setActiveClusterInstanceId(newActive);

  return {
    instanceId: newActive,
    store: readStoreById(newActive),
    instances: listClusterInstances(),
  };
}
