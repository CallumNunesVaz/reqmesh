import { useEffect, useState, useCallback } from 'react';
import {
  SlidersHorizontal, ShieldCheck, Save, Loader, Lock, Send, CheckCircle2,
  AlertTriangle, Palette, ToggleLeft, Mail, KeyRound, Gauge, ArrowUpCircle,
} from 'lucide-react';
import { api, type AppSetting } from '../api/client';
import { useAuthStore } from '../store/auth';

const CATEGORY_META: Record<string, { label: string; icon: typeof Palette; hint: string }> = {
  branding: { label: 'Branding', icon: Palette, hint: 'How this instance identifies itself.' },
  features: { label: 'Features', icon: ToggleLeft, hint: 'Toggle instance-wide capabilities.' },
  email: { label: 'Email (SMTP)', icon: Mail, hint: 'Outbound notification email.' },
  security: { label: 'Security', icon: KeyRound, hint: 'Sessions and account lockout.' },
  limits: { label: 'Limits', icon: Gauge, hint: 'Upload and size limits.' },
  updates: { label: 'Updates', icon: ArrowUpCircle, hint: 'Where updates are pulled from.' },
};
const CATEGORY_ORDER = ['branding', 'features', 'email', 'security', 'limits', 'updates'];

export default function SettingsPage() {
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === 'admin';

  const [settings, setSettings] = useState<AppSetting[]>([]);
  const [draft, setDraft] = useState<Record<string, string | number | boolean>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const [saved, setSaved] = useState(false);
  const [testTo, setTestTo] = useState('');
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; error?: string } | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await api.getSettings();
      setSettings(res.settings);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load settings');
    }
  }, []);
  useEffect(() => { if (isAdmin) load(); }, [isAdmin, load]);

  const dirty = Object.keys(draft).length > 0;
  const valueOf = (s: AppSetting) => (s.key in draft ? draft[s.key] : s.value);
  const setValue = (key: string, v: string | number | boolean) => {
    setDraft((d) => ({ ...d, [key]: v }));
    setSaved(false);
  };

  const save = async () => {
    setSaving(true);
    setError('');
    try {
      const res = await api.patchSettings(draft);
      setSettings(res.settings);
      setDraft({});
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const sendTest = async () => {
    setTesting(true);
    setTestResult(null);
    try { setTestResult(await api.testEmail(testTo)); }
    catch (e) { setTestResult({ ok: false, error: e instanceof Error ? e.message : 'Failed' }); }
    finally { setTesting(false); }
  };

  if (!isAdmin) {
    return (
      <div className="max-w-2xl mx-auto p-8 text-center">
        <ShieldCheck className="mx-auto mb-3 text-muted-foreground" size={32} />
        <h1 className="text-lg font-semibold">Administrator access required</h1>
        <p className="text-muted-foreground text-sm mt-1">Application settings are available to administrators only.</p>
      </div>
    );
  }

  const byCategory = CATEGORY_ORDER
    .map((cat) => ({ cat, items: settings.filter((s) => s.category === cat) }))
    .filter((g) => g.items.length > 0);

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6 pb-24">
      <div className="flex items-center gap-2">
        <SlidersHorizontal size={20} className="text-primary" />
        <h1 className="text-xl font-semibold">Application Settings</h1>
      </div>
      <p className="text-sm text-muted-foreground -mt-3">
        Instance-wide configuration. Settings pinned by an environment variable are shown locked and can only be changed in deployment config.
      </p>

      {error && (
        <div className="card p-3 border-destructive/40 bg-destructive/10 text-sm flex items-center gap-2">
          <AlertTriangle size={16} className="text-destructive shrink-0" /> {error}
        </div>
      )}

      {byCategory.map(({ cat, items }) => {
        const meta = CATEGORY_META[cat] ?? { label: cat, icon: SlidersHorizontal, hint: '' };
        const Icon = meta.icon;
        return (
          <section key={cat} className="card p-5">
            <h2 className="font-medium mb-1 flex items-center gap-2"><Icon size={16} className="text-primary" /> {meta.label}</h2>
            {meta.hint && <p className="text-xs text-muted-foreground mb-3">{meta.hint}</p>}
            <div className="space-y-3">
              {items.map((s) => (
                <SettingRow key={s.key} setting={s} value={valueOf(s)} onChange={(v) => setValue(s.key, v)} />
              ))}
            </div>

            {cat === 'email' && (
              <div className="mt-4 pt-3 border-t border-border/60">
                <label className="text-xs text-muted-foreground">Send a test email</label>
                <div className="flex gap-2 mt-1">
                  <input className="input text-sm flex-1" type="email" placeholder="you@example.com"
                    value={testTo} onChange={(e) => setTestTo(e.target.value)} />
                  <button className="btn-secondary" onClick={sendTest} disabled={testing || !testTo}>
                    {testing ? <Loader size={15} className="animate-spin" /> : <Send size={15} />} Test
                  </button>
                </div>
                {testResult && (
                  <p className={`text-xs mt-1.5 flex items-center gap-1 ${testResult.ok ? 'text-emerald-500' : 'text-destructive'}`}>
                    {testResult.ok ? <><CheckCircle2 size={12} /> Test email sent.</> : <><AlertTriangle size={12} /> {testResult.error}</>}
                  </p>
                )}
                <p className="text-[11px] text-muted-foreground mt-1.5">Save SMTP changes before testing.</p>
              </div>
            )}
          </section>
        );
      })}

      {/* Sticky save bar */}
      <div className="fixed bottom-0 left-0 right-0 border-t bg-card/95 backdrop-blur px-6 py-3 flex items-center justify-end gap-3 z-30">
        {saved && <span className="text-xs text-emerald-500 flex items-center gap-1"><CheckCircle2 size={14} /> Saved</span>}
        {dirty && <span className="text-xs text-muted-foreground">{Object.keys(draft).length} unsaved change(s)</span>}
        <button className="btn-primary" onClick={save} disabled={!dirty || saving}>
          {saving ? <Loader size={15} className="animate-spin" /> : <Save size={15} />} Save changes
        </button>
      </div>
    </div>
  );
}

function SettingRow({ setting, value, onChange }: {
  setting: AppSetting;
  value: string | number | boolean;
  onChange: (v: string | number | boolean) => void;
}) {
  const locked = setting.env_locked;
  return (
    <div className="flex items-start gap-3">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 text-sm">
          {setting.label}
          {locked && <Lock size={11} className="text-muted-foreground" aria-label="Set by environment variable" />}
        </div>
        {setting.help && <div className="text-[11px] text-muted-foreground">{setting.help}</div>}
      </div>
      <div className="shrink-0 w-56">
        {setting.type === 'bool' ? (
          <button
            role="switch"
            aria-checked={!!value}
            disabled={locked}
            onClick={() => onChange(!value)}
            className={`relative w-11 h-6 rounded-full transition-colors ${value ? 'bg-primary' : 'bg-muted'} ${locked ? 'opacity-50 cursor-not-allowed' : ''}`}
          >
            <span className={`absolute top-0.5 left-0.5 w-5 h-5 rounded-full bg-white transition-transform ${value ? 'translate-x-5' : ''}`} />
          </button>
        ) : (
          <input
            className="input text-sm w-full font-mono"
            type={setting.secret ? 'password' : setting.type === 'int' ? 'number' : 'text'}
            value={String(value ?? '')}
            placeholder={setting.secret && setting.has_value ? '•••••••• (set)' : ''}
            disabled={locked}
            onChange={(e) => onChange(setting.type === 'int' ? Number(e.target.value) : e.target.value)}
          />
        )}
      </div>
    </div>
  );
}
