/**
 * 将后端返回的本地绝对路径转为同源 HTTP 地址，供 <video src> 使用。
 * 从 http 页面加载 file:// 会被浏览器拦截，故统一走 /api/local_video_file。
 */
export function videoSrcFromLocalPath(absPath: string | null | undefined): string {
  if (absPath == null || typeof absPath !== 'string') return '';
  const t = absPath.trim();
  if (!t) return '';
  if (t.startsWith('http://') || t.startsWith('https://')) return t;
  if (t.startsWith('/api/local_video_file') || t.startsWith('/api/download/')) return t;
  if (t.startsWith('blob:') || t.startsWith('data:')) return t;
  return `/api/local_video_file?path=${encodeURIComponent(t)}`;
}
