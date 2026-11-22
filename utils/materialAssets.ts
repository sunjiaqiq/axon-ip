/** 口播/人设共用：服务端素材状态、预览、清除（与 pixelle_wrapper /api 对齐） */

export type MaterialKind =
  | 'avatar'
  | 'product'
  | 'audio'
  | 'showcase'
  | 'background_music';

export interface MaterialSlotApi {
  path: string | null;
  exists: boolean;
  uploaded: boolean;
  filename?: string | null;
}

export interface MaterialCurrentStateApi {
  avatar: MaterialSlotApi;
  audio: MaterialSlotApi;
  product: MaterialSlotApi;
  showcase: MaterialSlotApi;
  /** 环境演示 3 槽（新）；旧后端无此字段时由前端兜底 */
  showcase_slots?: [MaterialSlotApi, MaterialSlotApi, MaterialSlotApi];
  background_music: MaterialSlotApi;
  text: { content: string | null; length: number; set: boolean };
  ready_for_automation: boolean;
  can_generate_oral?: boolean;
  current_task_id?: string | null;
}

export async function fetchMaterialCurrentState(): Promise<MaterialCurrentStateApi> {
  const r = await fetch('/api/current_state');
  if (!r.ok) throw new Error('无法获取素材状态');
  const j = (await r.json()) as MaterialCurrentStateApi;
  const empty: MaterialSlotApi = { path: null, exists: false, uploaded: false, filename: null };
  if (!j.showcase_slots || !Array.isArray(j.showcase_slots) || j.showcase_slots.length < 3) {
    const sc = j.showcase;
    j.showcase_slots = [
      sc
        ? {
            path: sc.path ?? null,
            exists: !!sc.exists,
            uploaded: !!sc.uploaded,
            filename: sc.filename ?? null,
          }
        : { ...empty },
      { ...empty },
      { ...empty },
    ] as [MaterialSlotApi, MaterialSlotApi, MaterialSlotApi];
  }
  return j;
}

/** 与后端 _MATERIAL_KIND_TO_STATE_KEY 一致 */
export function previewQueryKind(slot: MaterialKind): string {
  if (slot === 'showcase') return 'showcase';
  return slot;
}

export function previewMediaKind(slot: MaterialKind): 'image' | 'audio' | 'video' {
  if (slot === 'audio' || slot === 'background_music') return 'audio';
  if (slot === 'showcase') return 'video';
  return 'image';
}

export async function clearMaterialOnServer(kind: MaterialKind): Promise<void> {
  const r = await fetch('/api/clear_material', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ kind }),
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || '清除失败');
  }
}

export async function fetchMaterialPreviewBlob(slot: MaterialKind): Promise<Blob> {
  const q = previewQueryKind(slot);
  const r = await fetch(`/api/material_preview?kind=${encodeURIComponent(q)}`);
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || '预览失败');
  }
  return r.blob();
}

/** 环境视频槽位 0~2 预览 */
export async function fetchShowcasePreviewBlob(slotIndex: 0 | 1 | 2): Promise<Blob> {
  const r = await fetch(
    `/api/material_preview?kind=${encodeURIComponent('showcase')}&slot=${slotIndex}`,
  );
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || '预览失败');
  }
  return r.blob();
}

export async function uploadShowcaseSlot(file: File, slot: 0 | 1 | 2): Promise<void> {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('slot', String(slot));
  const r = await fetch('/api/showcase_video', { method: 'POST', body: fd });
  if (!r.ok) {
    const t = await r.text();
    let msg = t || '上传失败';
    try {
      const j = JSON.parse(t) as { detail?: string };
      if (j.detail) msg = j.detail;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
}

export async function clearShowcaseSlot(slot: 0 | 1 | 2): Promise<void> {
  const r = await fetch('/api/clear_material', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ kind: 'showcase', showcase_slot: slot }),
  });
  if (!r.ok) {
    const t = await r.text();
    throw new Error(t || '清除失败');
  }
}

export function displayMaterialName(
  localFile: File | null,
  server: MaterialSlotApi | undefined,
): string {
  if (localFile) {
    return localFile.name.length > 15 ? localFile.name.substring(0, 15) + '...' : localFile.name;
  }
  const fn = server?.filename;
  if (fn) {
    return fn.length > 15 ? fn.substring(0, 15) + '...' : fn;
  }
  return '未选择';
}

export function canPreviewMaterial(localFile: File | null, server: MaterialSlotApi | undefined): boolean {
  if (localFile) return true;
  return !!(server?.uploaded && server?.exists);
}

export function hasServerMaterial(server: MaterialSlotApi | undefined): boolean {
  return !!(server?.uploaded && server?.exists);
}

export function serverMaterialSlot(
  s: MaterialCurrentStateApi | null,
  slot: MaterialKind,
): MaterialSlotApi | undefined {
  if (!s) return undefined;
  switch (slot) {
    case 'avatar':
      return s.avatar;
    case 'product':
      return s.product;
    case 'audio':
      return s.audio;
    case 'showcase':
      return s.showcase;
    case 'background_music':
      return s.background_music;
    default:
      return undefined;
  }
}
