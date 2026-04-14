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
  // Profile flags (affect constraints score — 20% of reliability)
  trlCurrent?: number;        // 1–9, default 5
  isSme?: boolean;            // PMI/SME flag
  sshCapacity?: boolean;      // Social Sciences & Humanities
  fairCompliant?: boolean;    // FAIR data principles
  genderDimensionActive?: boolean; // Gender dimension integration
};

export type ClusterStore = {
  clusterData: Partial<Record<ClusterId, ClusterData>>;
};

export const CLUSTERS: ClusterId[] = ['CL1', 'CL2', 'CL3', 'CL4', 'CL5', 'CL6'];
export const STORAGE_KEY = 'horizon-radar-clusters';

export function emptyClusterStore(): ClusterStore {
  return { clusterData: {} };
}

export function readClusterStore(): ClusterStore {
  if (typeof window === 'undefined') return emptyClusterStore();
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return emptyClusterStore();
    const parsed = JSON.parse(raw) as ClusterStore;
    return { clusterData: parsed.clusterData || {} };
  } catch {
    return emptyClusterStore();
  }
}

export function writeClusterStore(store: ClusterStore): void {
  if (typeof window === 'undefined') return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
}

export function ensureClusterWorkspace(): ClusterStore {
  const existing = readClusterStore();
  if (Object.keys(existing.clusterData).length > 0) return existing;
  const fresh = emptyClusterStore();
  writeClusterStore(fresh);
  return fresh;
}
