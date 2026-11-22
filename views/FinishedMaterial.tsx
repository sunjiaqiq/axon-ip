import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import { videoSrcFromLocalPath } from '../utils/videoPreviewUrl';

const Icons = {
  Play: () => <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z"/></svg>,
  Pause: () => <svg className="w-5 h-5" fill="currentColor" viewBox="0 0 24 24"><path d="M6 4h4v16H6V4zm8 0h4v16h-4V4z"/></svg>,
};

export type SubtitleSegment = { start: number; end: number; text: string };

const LS_LOCK = 'finished_material_video_lock';
const LS_CUSTOM = 'finished_material_custom_video_path';

function pickDefaultVideoPath(): string {
  if (typeof localStorage === 'undefined') return '';
  if (localStorage.getItem(LS_LOCK) === '1') {
    const c = (localStorage.getItem(LS_CUSTOM) || '').trim();
    if (c) return c;
  }
  const latest = (localStorage.getItem('latest_video_path') || '').trim();
  const base = (localStorage.getItem('manual_base_video_path') || '').trim();
  const finalP = (localStorage.getItem('manual_final_video_path') || '').trim();
  return latest || base || finalP;
}

function joinSegmentsText(segs: SubtitleSegment[]): string {
  return segs
    .map((s) => (s.text || '').trim())
    .filter(Boolean)
    .join(' ');
}

const FinishedMaterial: React.FC = () => {
  const [coverText, setCoverText] = useState('');
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [videoPath, setVideoPath] = useState('');
  const [scriptText, setScriptText] = useState('');
  const [subtitleSegments, setSubtitleSegments] = useState<SubtitleSegment[]>([]);
  const [isPlaying, setIsPlaying] = useState(false);
  const [finalizing, setFinalizing] = useState(false);
  const [finalizeProgress, setFinalizeProgress] = useState(0);
  const [finalizeStep, setFinalizeStep] = useState('');
  const [aiLoading, setAiLoading] = useState(false);
  const [subtitleLoading, setSubtitleLoading] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [lockHint, setLockHint] = useState(false);
  const videoRef = useRef<HTMLVideoElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const persistMaterial = useCallback(() => {
    const materialData = {
      coverText,
      title,
      description,
      videoPath,
      scriptText,
      subtitleSegments,
    };
    localStorage.setItem('finished_material_data', JSON.stringify(materialData));
    localStorage.setItem('manual_subtitle_segments', JSON.stringify(subtitleSegments));
    const base = videoPath.trim() || localStorage.getItem('manual_base_video_path') || '';
    if (base) localStorage.setItem('manual_base_video_path', base);
  }, [coverText, title, description, videoPath, scriptText, subtitleSegments]);

  const refreshDouyinFromScript = useCallback(async (script: string) => {
    const s = (script || '').trim();
    if (!s) return null;
    setAiLoading(true);
    try {
      const response = await fetch('/api/generate_douyin_content', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ script_text: s }),
      });
      if (response.ok) {
        const data = await response.json();
        const ct = data.cover_text || '';
        const ti = data.title || '';
        const de = data.description || '';
        setCoverText(ct);
        setTitle(ti);
        setDescription(de);
        return { coverText: ct, title: ti, description: de };
      }
    } catch (error) {
      console.error('AI 生成封面/标题/描述失败:', error);
    } finally {
      setAiLoading(false);
    }
    return null;
  }, []);

  /** 进入成品页：默认最新口播底片；若用户曾锁定自定义视频则保留 */
  useEffect(() => {
    const run = async () => {
      const path = pickDefaultVideoPath();
      if (path) setVideoPath(path);

      const segRaw = localStorage.getItem('manual_subtitle_segments');
      let segs: SubtitleSegment[] = [];
      if (segRaw) {
        try {
          const parsed = JSON.parse(segRaw) as unknown[];
          if (Array.isArray(parsed)) {
            segs = parsed.map((x: any) => ({
              start: Number(x.start) || 0,
              end: Number(x.end) || 0,
              text: String(x.text ?? ''),
            }));
          }
        } catch {
          /* ignore */
        }
      }
      if (segs.length) setSubtitleSegments(segs);

      const curScript = (localStorage.getItem('current_script') || '').trim();
      let st = curScript;
      const finished = localStorage.getItem('finished_material_data');
      if (!st && finished) {
        try {
          const m = JSON.parse(finished);
          if (m.scriptText != null && String(m.scriptText).trim()) st = String(m.scriptText).trim();
          if (!segs.length && Array.isArray(m.subtitleSegments) && m.subtitleSegments.length) {
            const fromFin = m.subtitleSegments.map((x: any) => ({
              start: Number(x.start) || 0,
              end: Number(x.end) || 0,
              text: String(x.text ?? ''),
            }));
            setSubtitleSegments(fromFin);
            segs = fromFin;
          }
        } catch {
          /* ignore */
        }
      }
      if (st) setScriptText(st);

      const scriptForAi = st || joinSegmentsText(segs);
      if (scriptForAi.trim()) void refreshDouyinFromScript(scriptForAi);
      setLockHint(localStorage.getItem(LS_LOCK) === '1');
    };
    void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleResetToLatestOral = () => {
    localStorage.removeItem(LS_LOCK);
    localStorage.removeItem(LS_CUSTOM);
    setLockHint(false);
    const path = pickDefaultVideoPath();
    setVideoPath(path);
    const segRaw = localStorage.getItem('manual_subtitle_segments');
    let nextSegs: SubtitleSegment[] = [];
    if (segRaw) {
      try {
        const parsed = JSON.parse(segRaw) as unknown[];
        if (Array.isArray(parsed)) {
          nextSegs = parsed.map((x: any) => ({
            start: Number(x.start) || 0,
            end: Number(x.end) || 0,
            text: String(x.text ?? ''),
          }));
        }
      } catch {
        nextSegs = [];
      }
    }
    setSubtitleSegments(nextSegs);
    const cs = (localStorage.getItem('current_script') || '').trim();
    const scriptForAi = cs || joinSegmentsText(nextSegs);
    if (cs) setScriptText(cs);
    if (scriptForAi) void refreshDouyinFromScript(scriptForAi);
  };

  const handlePickVideoClick = () => fileInputRef.current?.click();

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file) return;
    setUploading(true);
    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('script_text', scriptText.trim());
      const res = await fetch('/api/finished_material/upload_video', { method: 'POST', body: fd });
      if (!res.ok) {
        const t = await res.text();
        let msg = t || '上传失败';
        try {
          const j = JSON.parse(t) as { detail?: string };
          if (j.detail) msg = j.detail;
        } catch {
          /* ignore */
        }
        throw new Error(msg);
      }
      const data = (await res.json()) as {
        path?: string;
        subtitle_segments?: { start: number; end: number; text: string }[];
      };
      const p = (data.path || '').trim();
      if (!p) throw new Error('未返回视频路径');
      localStorage.setItem(LS_LOCK, '1');
      localStorage.setItem(LS_CUSTOM, p);
      setLockHint(true);
      setVideoPath(p);
      const segs = Array.isArray(data.subtitle_segments) ? data.subtitle_segments : [];
      if (segs.length) {
        const norm = segs.map((x) => ({
          start: Number(x.start) || 0,
          end: Number(x.end) || 0,
          text: String(x.text ?? ''),
        }));
        setSubtitleSegments(norm);
        localStorage.setItem('manual_subtitle_segments', JSON.stringify(norm));
      } else {
        setSubtitleSegments([]);
        localStorage.removeItem('manual_subtitle_segments');
      }
      const scriptForAi =
        scriptText.trim() || joinSegmentsText(segs as SubtitleSegment[]) || (localStorage.getItem('current_script') || '').trim();
      if (scriptForAi) await refreshDouyinFromScript(scriptForAi);
      else alert('已上传视频。请在左侧填写「原始文案」后点击「根据当前视频与文案生成字幕」或直接去合成。');
    } catch (err: any) {
      alert(err?.message || '上传失败');
    } finally {
      setUploading(false);
    }
  };

  const handleRebuildSubtitles = async () => {
    const vp = videoPath.trim();
    if (!vp) {
      alert('请先选择或上传视频');
      return;
    }
    const st = scriptText.trim();
    if (!st) {
      alert('请先填写「原始文案」（口播稿），用于与时间轴对齐');
      return;
    }
    setSubtitleLoading(true);
    try {
      const res = await fetch('/api/finished_material/rebuild_subtitles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ video_path: vp, script_text: st }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error((err as any).detail || '生成字幕失败');
      }
      const data = (await res.json()) as { subtitle_segments?: SubtitleSegment[] };
      const segs = Array.isArray(data.subtitle_segments) ? data.subtitle_segments : [];
      if (!segs.length) {
        alert('未生成到字幕轴，请检查文案是否与视频内容匹配，或稍后重试');
        return;
      }
      setSubtitleSegments(segs);
      localStorage.setItem('manual_subtitle_segments', JSON.stringify(segs));
      await refreshDouyinFromScript(st);
    } catch (e: any) {
      alert(e?.message || '生成字幕失败');
    } finally {
      setSubtitleLoading(false);
    }
  };

  const togglePlay = () => {
    if (videoRef.current) {
      if (isPlaying) videoRef.current.pause();
      else videoRef.current.play();
      setIsPlaying(!isPlaying);
    }
  };

  const handleSave = () => {
    persistMaterial();
    if (videoPath.trim()) localStorage.setItem('latest_video_path', videoPath.trim());
    alert('保存成功！可以在分发平台使用这些内容进行发布。');
  };

  const handleFinalize = async () => {
    const base = (videoPath || '').trim() || pickDefaultVideoPath();
    if (!base) {
      alert('未找到视频路径，请先在口播页生成或上传视频。');
      return;
    }
    const scriptForFinalize =
      scriptText.trim() ||
      joinSegmentsText(subtitleSegments) ||
      (localStorage.getItem('current_script') || '').trim();
    if (!scriptForFinalize) {
      alert('请先填写原始文案，或生成字幕后重试');
      return;
    }
    if (!subtitleSegments.length) {
      alert('没有可用的字幕时间轴。请先口播生成或上传视频后点击「根据当前视频与文案生成字幕」。');
      return;
    }

    setFinalizing(true);
    setFinalizeProgress(2);
    setFinalizeStep('正在刷新封面、标题与描述…');
    let triple = { coverText, title, description };
    try {
      setScriptText(scriptForFinalize);
      const aiSnap = await refreshDouyinFromScript(scriptForFinalize);
      if (aiSnap) triple = aiSnap;
    } catch {
      /* refreshDouyin 已内部 catch */
    }

    persistMaterial();
    setFinalizeProgress(8);
    setFinalizeStep('提交合成任务…');
    try {
      const res = await fetch('/api/generate/finalize_manual', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          base_video_path: base,
          segments: subtitleSegments,
          script_text: scriptForFinalize,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error((err as any).detail || '创建合成任务失败');
      }
      const data = await res.json();
      const tid = data.task_id as string;
      if (!tid) throw new Error('未返回 task_id');

      const poll = async () => {
        const st = await fetch(`/api/task/${tid}`);
        if (!st.ok) {
          setTimeout(poll, 1000);
          return;
        }
        const s = await st.json();
        setFinalizeProgress(s.progress ?? 0);
        setFinalizeStep(s.step || s.message || '');
        if (s.status === 'done' || s.status === 'completed') {
          setFinalizing(false);
          setFinalizeProgress(100);
          localStorage.removeItem(LS_LOCK);
          localStorage.removeItem(LS_CUSTOM);
          setLockHint(false);
          if (s.output) {
            setVideoPath(s.output);
            localStorage.setItem('manual_final_video_path', s.output);
            localStorage.setItem('latest_video_path', s.output);
            const materialData = {
              coverText: triple.coverText,
              title: triple.title,
              description: triple.description,
              videoPath: s.output,
              scriptText: scriptForFinalize,
              subtitleSegments,
            };
            localStorage.setItem('finished_material_data', JSON.stringify(materialData));
            localStorage.setItem('manual_subtitle_segments', JSON.stringify(subtitleSegments));
          }
          alert('成片生成完成！');
        } else if (s.status === 'error' || s.status === 'failed') {
          setFinalizing(false);
          alert(`合成失败: ${s.error || s.message || '未知错误'}`);
        } else {
          setTimeout(poll, 1000);
        }
      };
      setTimeout(poll, 800);
    } catch (e: any) {
      setFinalizing(false);
      alert(e?.message || '合成失败');
    }
  };

  const previewSrc = useMemo(() => videoSrcFromLocalPath(videoPath), [videoPath]);

  const updateSegText = (index: number, text: string) => {
    setSubtitleSegments((prev) => {
      const next = [...prev];
      if (next[index]) next[index] = { ...next[index], text };
      return next;
    });
  };

  return (
    <div className="h-full flex flex-col">
      <div className="mb-6">
        <h1 className="text-3xl font-black tracking-tight text-white mb-2">成品素材</h1>
        <p className="text-slate-400 text-sm">
          默认展示最新口播成片底片；可上传其它视频。编辑字幕后点「再次生成」将同步刷新封面/标题/描述并合成。
        </p>
        {aiLoading && <p className="text-xs text-indigo-400 mt-2">正在生成封面、标题与描述…</p>}
      </div>

      <div className="flex-1 flex gap-6 overflow-hidden min-h-0">
        <div className="w-1/2 flex flex-col gap-6 overflow-y-auto pr-2">
          <div className="bg-[#131720] border border-white/5 rounded-2xl p-6">
            <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-3">
              封面内容
            </label>
            <input
              type="text"
              value={coverText}
              onChange={(e) => setCoverText(e.target.value)}
              placeholder="4-8个字总结"
              maxLength={10}
              className="w-full bg-[#0b0e14] border border-white/5 rounded-xl px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500/50 transition-all"
            />
            <p className="mt-2 text-xs text-slate-500">AI生成：4-8个字总结</p>
          </div>

          <div className="bg-[#131720] border border-white/5 rounded-2xl p-6">
            <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-3">
              标题
            </label>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="15个字总结，包含3个左右话题#"
              maxLength={30}
              className="w-full bg-[#0b0e14] border border-white/5 rounded-xl px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500/50 transition-all"
            />
            <p className="mt-2 text-xs text-slate-500">AI生成：15个字总结，包含3个左右话题#</p>
          </div>

          <div className="bg-[#131720] border border-white/5 rounded-2xl p-6">
            <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-3">
              描述内容
            </label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="20字左右"
              maxLength={50}
              rows={4}
              className="w-full bg-[#0b0e14] border border-white/5 rounded-xl px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500/50 transition-all resize-none"
            />
            <p className="mt-2 text-xs text-slate-500">AI生成：20字左右</p>
          </div>

          <div className="bg-[#131720] border border-white/5 rounded-2xl p-6">
            <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-3">
              原始文案（用于AI生成）
            </label>
            <textarea
              value={scriptText}
              onChange={(e) => setScriptText(e.target.value)}
              placeholder="输入或粘贴文案内容，用于AI生成封面、标题和描述"
              rows={3}
              className="w-full bg-[#0b0e14] border border-white/5 rounded-xl px-4 py-3 text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500/50 transition-all resize-none"
            />
          </div>

          <div className="bg-[#131720] border border-amber-500/20 rounded-2xl p-6">
            <label className="block text-[10px] font-black uppercase tracking-widest text-amber-500/80 mb-2">
              字幕（Whisper 时间轴 + AI 文案，仅可改错别字）
            </label>
            <p className="text-xs text-slate-500 mb-3">
              勿删行、勿改时间；更换视频后请先填原始文案再点下方「根据当前视频与文案生成字幕」。
            </p>
            {subtitleSegments.length === 0 ? (
              <p className="text-sm text-slate-500">暂无字幕数据。口播生成后会自动带入；上传新视频后请生成字幕轴。</p>
            ) : (
              <div className="space-y-2 max-h-64 overflow-y-auto pr-1">
                {subtitleSegments.map((seg, i) => (
                  <div
                    key={`${seg.start}-${seg.end}-${i}`}
                    className="flex gap-2 items-start bg-[#0b0e14] rounded-lg px-3 py-2 border border-white/5"
                  >
                    <span className="text-[10px] text-slate-500 font-mono shrink-0 w-28 pt-2">
                      {seg.start.toFixed(2)}–{seg.end.toFixed(2)}s
                    </span>
                    <input
                      type="text"
                      value={seg.text}
                      onChange={(e) => updateSegText(i, e.target.value)}
                      className="flex-1 min-w-0 bg-transparent text-sm text-slate-200 focus:outline-none border-b border-transparent focus:border-indigo-500/50"
                    />
                  </div>
                ))}
              </div>
            )}
            <button
              type="button"
              disabled={subtitleLoading || finalizing}
              onClick={() => void handleRebuildSubtitles()}
              className="mt-4 w-full py-3 rounded-xl text-xs font-black uppercase tracking-widest bg-slate-700 text-white hover:bg-slate-600 disabled:opacity-50"
            >
              {subtitleLoading ? '正在生成字幕轴…' : '根据当前视频与文案生成字幕'}
            </button>
          </div>

          <div className="flex gap-4">
            <button
              type="button"
              onClick={handleSave}
              className="flex-1 py-4 rounded-xl font-black text-sm uppercase tracking-widest transition-all flex items-center justify-center space-x-3 shadow-lg bg-indigo-600 text-white hover:bg-indigo-500 shadow-indigo-500/20"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
              </svg>
              <span>保存</span>
            </button>
            <button
              type="button"
              disabled={finalizing || aiLoading}
              onClick={() => void handleFinalize()}
              className="flex-1 py-4 rounded-xl font-black text-sm uppercase tracking-widest transition-all flex items-center justify-center space-x-3 shadow-lg bg-emerald-700 text-white hover:bg-emerald-600 shadow-emerald-900/30 disabled:opacity-50"
            >
              <span>{finalizing ? '合成中…' : '再次生成'}</span>
            </button>
          </div>
        </div>

        <div className="w-1/2 flex flex-col gap-4 min-h-0">
          <div className="bg-[#131720] border border-white/5 rounded-2xl p-6 flex-1 flex flex-col min-h-0">
            <label className="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-4">
              视频预览
            </label>

            <input
              ref={fileInputRef}
              type="file"
              accept="video/mp4,video/webm,video/quicktime,.mp4,.webm,.mov,.mkv,.m4v"
              className="hidden"
              onChange={(e) => void handleFileChange(e)}
            />
            <div className="flex flex-wrap gap-2 mb-3">
              <button
                type="button"
                disabled={uploading || finalizing}
                onClick={handlePickVideoClick}
                className="px-4 py-2 rounded-lg text-xs font-bold bg-indigo-600 text-white hover:bg-indigo-500 disabled:opacity-50"
              >
                {uploading ? '上传中…' : '上传其它视频'}
              </button>
              <button
                type="button"
                disabled={finalizing || uploading}
                onClick={handleResetToLatestOral}
                className="px-4 py-2 rounded-lg text-xs font-bold bg-slate-700 text-slate-200 hover:bg-slate-600 disabled:opacity-50"
              >
                使用最新口播视频
              </button>
              {lockHint && (
                <span className="text-[10px] text-amber-400 self-center">当前为自选/上传视频</span>
              )}
            </div>

            {finalizing && (
              <div className="mb-4 space-y-2">
                <div className="flex items-center gap-2 text-sm text-slate-300">
                  <span className="inline-block h-4 w-4 border-2 border-indigo-400 border-t-transparent rounded-full animate-spin" />
                  <span>{finalizeStep || '正在合成成片…'}</span>
                </div>
                <div className="h-2 bg-white/10 rounded-full overflow-hidden">
                  <div
                    className="h-full bg-indigo-500 transition-all duration-300"
                    style={{ width: `${Math.min(100, Math.max(0, finalizeProgress))}%` }}
                  />
                </div>
              </div>
            )}

            {videoPath ? (
              <>
                <div className="flex-1 bg-[#0b0e14] rounded-xl overflow-hidden relative min-h-[200px]">
                  <video
                    key={previewSrc}
                    ref={videoRef}
                    src={previewSrc || undefined}
                    className="w-full h-full object-contain"
                    onPlay={() => setIsPlaying(true)}
                    onPause={() => setIsPlaying(false)}
                    controls
                  />
                </div>
                <div className="mt-4 flex items-center justify-center">
                  <button
                    type="button"
                    onClick={togglePlay}
                    className="px-6 py-3 bg-indigo-600 hover:bg-indigo-500 text-white rounded-xl font-medium flex items-center space-x-2 transition-all"
                  >
                    {isPlaying ? (
                      <>
                        <Icons.Pause />
                        <span>暂停</span>
                      </>
                    ) : (
                      <>
                        <Icons.Play />
                        <span>播放</span>
                      </>
                    )}
                  </button>
                </div>
                <p className="mt-2 text-xs text-slate-500 text-center truncate">{videoPath}</p>
              </>
            ) : (
              <div className="flex-1 bg-[#0b0e14] rounded-xl flex items-center justify-center border-2 border-dashed border-white/10 min-h-[200px]">
                <p className="text-slate-500 text-sm">暂无视频，请先在口播页生成或上传视频</p>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default FinishedMaterial;
