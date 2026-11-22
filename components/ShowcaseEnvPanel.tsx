import React, { useCallback, useRef, useState } from 'react';
import type { MaterialCurrentStateApi, MaterialSlotApi } from '../utils/materialAssets';
import {
  clearShowcaseSlot,
  fetchShowcasePreviewBlob,
  uploadShowcaseSlot,
} from '../utils/materialAssets';

const MAX_SEC = 40;

type SlotIx = 0 | 1 | 2;

function slotApi(ms: MaterialCurrentStateApi | null, i: SlotIx): MaterialSlotApi | undefined {
  const arr = ms?.showcase_slots;
  if (!arr || !Array.isArray(arr) || arr.length < 3) return undefined;
  return arr[i] as MaterialSlotApi;
}

function slotLabel(i: SlotIx): string {
  return `槽位 ${i + 1}`;
}

type Props = {
  isConnected: boolean;
  materialServer: MaterialCurrentStateApi | null;
  onRefresh: () => Promise<void>;
  /** oral 用大卡片内嵌；automation 用弹窗里紧凑条 */
  variant?: 'oral' | 'automation';
};

const ShowcaseEnvPanel: React.FC<Props> = ({
  isConnected,
  materialServer,
  onRefresh,
  variant = 'oral',
}) => {
  const [panelOpen, setPanelOpen] = useState(false);
  const [pickSlot, setPickSlot] = useState<SlotIx>(0);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [enlargeSlot, setEnlargeSlot] = useState<SlotIx | null>(null);
  const [enlargeUrl, setEnlargeUrl] = useState<string | null>(null);

  const closeEnlarge = useCallback(() => {
    if (enlargeUrl) URL.revokeObjectURL(enlargeUrl);
    setEnlargeUrl(null);
    setEnlargeSlot(null);
  }, [enlargeUrl]);

  const checkDuration = useCallback((file: File): Promise<boolean> => {
    return new Promise((resolve) => {
      const v = document.createElement('video');
      v.preload = 'metadata';
      const u = URL.createObjectURL(file);
      v.src = u;
      const done = (ok: boolean) => {
        URL.revokeObjectURL(u);
        resolve(ok);
      };
      v.onloadedmetadata = () => {
        const d = v.duration;
        if (!Number.isFinite(d) || d >= MAX_SEC) {
          alert(
            `每段环境视频须小于 ${MAX_SEC} 秒，当前约 ${
              Number.isFinite(d) ? d.toFixed(1) : '?'
            } 秒`,
          );
          done(false);
        } else done(true);
      };
      v.onerror = () => {
        alert('无法读取该视频，请换常见格式（如 MP4）');
        done(false);
      };
    });
  }, []);

  const onFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file || !isConnected) return;
    if (!(await checkDuration(file))) return;
    try {
      await uploadShowcaseSlot(file, pickSlot);
      await onRefresh();
    } catch (err) {
      alert(err instanceof Error ? err.message : String(err));
    }
  };

  const requestUpload = (slot: SlotIx) => {
    if (!isConnected) {
      alert('请等待后台连接成功后再上传');
      return;
    }
    setPickSlot(slot);
    fileInputRef.current?.click();
  };

  const onDeleteSlot = async (slot: SlotIx) => {
    const s = slotApi(materialServer, slot);
    if (!s?.uploaded) return;
    if (!window.confirm(`确定删除${slotLabel(slot)}的环境视频？`)) return;
    try {
      await clearShowcaseSlot(slot);
      await onRefresh();
    } catch (err) {
      alert(err instanceof Error ? err.message : String(err));
    }
  };

  const openEnlarge = async (slot: SlotIx) => {
    const s = slotApi(materialServer, slot);
    if (!isConnected || !s?.uploaded || !s?.exists) {
      alert('该槽位没有可播放的视频');
      return;
    }
    try {
      closeEnlarge();
      const blob = await fetchShowcasePreviewBlob(slot);
      const url = URL.createObjectURL(blob);
      setEnlargeUrl(url);
      setEnlargeSlot(slot);
    } catch (err) {
      alert(err instanceof Error ? err.message : String(err));
    }
  };

  const anyUploaded =
    !!(slotApi(materialServer, 0)?.uploaded && slotApi(materialServer, 0)?.exists) ||
    !!(slotApi(materialServer, 1)?.uploaded && slotApi(materialServer, 1)?.exists) ||
    !!(slotApi(materialServer, 2)?.uploaded && slotApi(materialServer, 2)?.exists);

  const slotBox = (slot: SlotIx) => {
    const s = slotApi(materialServer, slot);
    const has = !!(s?.uploaded && s?.exists);
    return (
      <div
        key={slot}
        className="flex flex-col items-stretch gap-1 rounded-lg border border-white/10 bg-black/30 p-2"
      >
        <div className="text-[9px] font-bold uppercase tracking-wider text-slate-500 text-center">
          {slotLabel(slot)}
        </div>
        <button
          type="button"
          onClick={() => void openEnlarge(slot)}
          disabled={!has}
          className={`relative mx-auto flex h-16 w-16 items-center justify-center overflow-hidden rounded-md border ${
            has
              ? 'border-amber-500/40 bg-black hover:border-amber-400/70'
              : 'border-white/5 bg-slate-900/80 cursor-default'
          }`}
        >
          {has ? (
            <span className="text-[9px] text-amber-200/90">点击放大</span>
          ) : (
            <span className="text-[9px] text-slate-600">空</span>
          )}
        </button>
        <div className="grid grid-cols-2 gap-1">
          <button
            type="button"
            onClick={() => requestUpload(slot)}
            disabled={!isConnected}
            className={`rounded py-1 text-[9px] font-bold uppercase ${
              isConnected
                ? 'bg-indigo-600/80 text-white hover:bg-indigo-500'
                : 'bg-slate-800 text-slate-600 cursor-not-allowed'
            }`}
          >
            上传
          </button>
          <button
            type="button"
            onClick={() => void onDeleteSlot(slot)}
            disabled={!has}
            className={`rounded py-1 text-[9px] font-bold uppercase ${
              has
                ? 'bg-rose-600/40 text-rose-100 hover:bg-rose-600/60'
                : 'bg-slate-800 text-slate-600 cursor-not-allowed'
            }`}
          >
            删
          </button>
        </div>
      </div>
    );
  };

  const panelInner = (
    <div className="space-y-3">
      <p className="text-[10px] text-slate-400 leading-relaxed">
        最多 3 段，每段须小于 40 秒；画中画按槽 1→2→3 顺序拼接后循环。时间轴：0~8 秒无，8~15 秒有，15~27
        秒无，27 秒后至结束有。
      </p>
      <div className="grid grid-cols-3 gap-2">{([0, 1, 2] as const).map((i) => slotBox(i))}</div>
      <input
        ref={fileInputRef}
        type="file"
        accept="video/*"
        className="hidden"
        onChange={(e) => void onFileChange(e)}
      />
    </div>
  );

  const triggerBtnClass =
    variant === 'oral'
      ? `w-full py-2 rounded-lg text-[10px] font-bold uppercase tracking-wider ${
          isConnected
            ? 'bg-amber-600/20 border border-amber-500/30 text-amber-100 hover:bg-amber-600/30'
            : 'bg-slate-900 border border-white/5 text-slate-600 cursor-not-allowed'
        }`
      : `w-full py-2.5 rounded-xl text-[10px] font-bold uppercase tracking-wider ${
          isConnected
            ? 'bg-indigo-600/20 border border-indigo-500/25 text-indigo-100 hover:bg-indigo-600/30'
            : 'bg-slate-900 border border-white/10 text-slate-500 cursor-not-allowed opacity-50'
        }`;

  return (
    <>
      <button type="button" disabled={!isConnected} onClick={() => setPanelOpen(true)} className={triggerBtnClass}>
        {anyUploaded ? '查看 / 管理环境视频（已上传）' : '查看 / 管理环境视频'}
      </button>

      {panelOpen && (
        <div
          className="fixed inset-0 z-[80] flex items-center justify-center bg-black/70 p-4"
          role="presentation"
          onClick={() => setPanelOpen(false)}
        >
          <div
            role="dialog"
            className="max-h-[90vh] w-full max-w-md overflow-y-auto rounded-2xl border border-white/10 bg-[#131720] p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-3 flex items-center justify-between">
              <h3 className="text-sm font-bold text-white">环境演示视频（画中画）</h3>
              <button
                type="button"
                className="rounded-lg px-2 py-1 text-xs text-slate-400 hover:bg-white/5 hover:text-white"
                onClick={() => setPanelOpen(false)}
              >
                关闭
              </button>
            </div>
            {panelInner}
          </div>
        </div>
      )}

      {enlargeSlot !== null && enlargeUrl && (
        <div
          className="fixed inset-0 z-[90] flex flex-col items-center justify-center bg-black/85 p-4"
          onClick={closeEnlarge}
        >
          <div className="mb-2 text-xs text-slate-300">{slotLabel(enlargeSlot)}</div>
          <video
            src={enlargeUrl}
            controls
            autoPlay
            className="max-h-[80vh] max-w-full rounded-lg border border-white/10"
            onClick={(e) => e.stopPropagation()}
          />
          <button
            type="button"
            className="mt-4 rounded-lg bg-white/10 px-4 py-2 text-sm text-white hover:bg-white/20"
            onClick={closeEnlarge}
          >
            关闭
          </button>
        </div>
      )}
    </>
  );
};

export default ShowcaseEnvPanel;
