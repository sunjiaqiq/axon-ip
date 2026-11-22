
import React from 'react';

const BAIDU_DOWNLOAD_URL = 'https://pan.baidu.com/s/1mLagx_KO2oMorwJ2o5h27w?pwd=8888';

const AvatarLiveModule: React.FC = () => {
  const handleDownloadClick = () => {
    window.open(BAIDU_DOWNLOAD_URL, '_blank', 'noopener,noreferrer');
  };

  return (
    <div className="max-w-3xl mx-auto space-y-8">
      <h1 className="text-2xl font-bold text-white tracking-tight">分身直播</h1>

      <button
        type="button"
        onClick={handleDownloadClick}
        className="w-full max-w-md py-4 rounded-2xl text-white font-bold text-base shadow-xl shadow-indigo-500/20 hover:opacity-95 active:opacity-90 transition-opacity bg-gradient-to-r from-indigo-600 to-purple-600"
      >
        获取并下载
      </button>

      <div className="rounded-2xl border border-white/10 bg-[#0f1219]/80 p-6 space-y-5 text-sm text-slate-300 leading-relaxed">
        <section>
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">电脑配置</h2>
          <p>显卡3060以上，8G显存以上即可。</p>
        </section>

        <section>
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">重点</h2>
          <p>
            音频的清晰度，取决于上传的音质质量，建议上传音频5分钟时长。人物的清晰度，取决于上传人物素材的质量，建议上传10分钟素材！
          </p>
        </section>

        <section>
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">下载重点</h2>
          <ol className="list-decimal list-inside space-y-2">
            <li>杀毒软件全关闭或卸载（现在已经没有毒了，360等杀毒软件本身就是毒）</li>
            <li>下载要放在内存大于30G以上的盘里</li>
            <li>仔细看教程安装，软件现已有大几千直播间使用，软件没问题，有问题一般都是没有仔细看教程！</li>
          </ol>
          <p className="mt-4 text-slate-400">如需人工辅助，请联系客服！（另收费）</p>
        </section>
      </div>
    </div>
  );
};

export default AvatarLiveModule;
