import React, { useState } from 'react';

/** 与旧账号系统校验通过后写入，主界面据此判断是否已登录 */
export const CUSTOMER_AUTH_KEY = 'customer_account_authed';
export const CUSTOMER_AUTH_USER_KEY = 'customer_account_username';

/**
 * 账号校验接口根地址（可选）。
 * - 开源默认不启用门禁：未设置 VITE_ACCOUNT_API_BASE 时直接进入主界面
 * - 商业交付可在构建前设置 VITE_ACCOUNT_API_BASE 指向自有账号服务
 */
function getAccountApiBase(): string {
  const raw = (import.meta.env.VITE_ACCOUNT_API_BASE as string | undefined)?.trim();
  if (!raw) return '';
  let u = raw;
  if (!/^https?:\/\//i.test(u)) u = `http://${u}`;
  return u.replace(/\/+$/, '');
}

const ACCOUNT_API_BASE = getAccountApiBase();

/** 是否启用启动登录门禁（仅当配置了账号服务地址时） */
export function isAccountGateEnabled(): boolean {
  return Boolean(ACCOUNT_API_BASE);
}

export function isCustomerAuthed(): boolean {
  if (typeof window === 'undefined') return false;
  // 未配置账号服务时视为已通过（开源本地运行）
  if (!ACCOUNT_API_BASE) return true;
  return window.localStorage.getItem(CUSTOMER_AUTH_KEY) === '1';
}

interface StartupLoginGateProps {
  onSuccess: () => void;
}

/**
 * 启动全屏门禁：不渲染侧栏与主业务 UI，仅弹层内输入账号密码。
 * 校验走旧系统 POST /api/login，通过后写入 localStorage 并进入主界面。
 */
const StartupLoginGate: React.FC<StartupLoginGateProps> = ({ onSuccess }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage('');
    if (!username.trim() || !password) {
      setMessage('请输入账号和密码');
      return;
    }

    setLoading(true);
    try {
      const resp = await fetch(`${ACCOUNT_API_BASE}/api/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim(), password }),
      });

      if (!resp.ok) {
        const text = await resp.text().catch(() => '');
        throw new Error(`账号校验失败 (${resp.status})${text ? ` ${text.slice(0, 80)}` : ''}`);
      }

      const data: any = await resp.json().catch(() => null);
      if (!data || data.code !== 0) {
        throw new Error(data?.msg || '账号或密码错误，或账号已失效');
      }

      window.localStorage.setItem(CUSTOMER_AUTH_KEY, '1');
      window.localStorage.setItem(CUSTOMER_AUTH_USER_KEY, username.trim());
      onSuccess();
    } catch (err: any) {
      const msg = err?.message ? String(err.message) : '登录失败';
      setMessage(msg);
      window.localStorage.removeItem(CUSTOMER_AUTH_KEY);
      window.localStorage.removeItem(CUSTOMER_AUTH_USER_KEY);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/75 backdrop-blur-sm p-4">
      <div
        className="w-full max-w-md rounded-2xl border border-white/10 bg-[#131720] shadow-2xl shadow-indigo-900/20"
        role="dialog"
        aria-modal="true"
        aria-labelledby="startup-login-title"
      >
        <div className="border-b border-white/5 px-6 py-4">
          <h1 id="startup-login-title" className="text-lg font-bold text-white">
            账号登录
          </h1>
          <p className="mt-1 text-xs text-slate-500">
            验证通过后方可进入系统。抖音/小红书等请在系统内「浏览器登录」中操作。
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 px-6 py-6">
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">账号</label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-[#1a1f2a] px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-indigo-500"
              placeholder="请输入账号"
              autoComplete="username"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-xs font-medium text-slate-400">密码</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-white/10 bg-[#1a1f2a] px-3 py-2.5 text-sm text-slate-200 outline-none focus:border-indigo-500"
              placeholder="请输入密码"
              autoComplete="current-password"
            />
          </div>

          {message ? <p className="text-sm text-rose-400">{message}</p> : null}

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-indigo-600 py-3 text-sm font-bold text-white shadow-lg shadow-indigo-500/25 transition hover:bg-indigo-500 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {loading ? '验证中…' : '进入系统'}
          </button>
        </form>
      </div>
    </div>
  );
};

export default StartupLoginGate;

