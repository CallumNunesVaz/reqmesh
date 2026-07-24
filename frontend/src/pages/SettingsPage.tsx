import { useEffect, useState, useCallback, useRef } from 'react';
import {
  SlidersHorizontal, ShieldCheck, Save, Loader, Lock, Send, CheckCircle2,
  AlertTriangle,   Palette, ToggleLeft, Mail, KeyRound, Gauge, ArrowUpCircle, Users, FileText, Plus, X, Upload,
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
  teams: { label: 'Teams', icon: Users, hint: 'Organisational units available for requirement allocation.' },
  reporting: { label: 'Reporting', icon: FileText, hint: 'Configuration for generated reports (cover page, headers, footers).' },
};
const CATEGORY_ORDER = ['branding', 'features', 'teams', 'reporting', 'email', 'security', 'limits', 'updates'];

export default function SettingsPage() {
  const user = useAuthStore((s) => s.user);
  const isAdmin = user?.role === 'admin';

  const [settings, setSettings] = useState<AppSetting[]>([]);
  const [draft, setDraft] = useState<Record<string, string | number | boolean | string[]>>({});
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
  const valueOf = (s: AppSetting) => {
    if (s.key in draft) return draft[s.key];
    return s.value;
  };
  const setValue = (key: string, v: string | number | boolean | string[]) => {
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
                <SettingRow key={s.key} setting={s} value={valueOf(s) as any} onChange={(v) => setValue(s.key, v)} />
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

      {/* Sticky save bar — pane-anchored (sticks to the inspector's scrollport) */}
      <div className="sticky bottom-0 -mx-6 border-t bg-card/95 backdrop-blur px-6 py-3 flex flex-wrap items-center justify-end gap-3 z-30">
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
  value: string | number | boolean | string[];
  onChange: (v: string | number | boolean | string[]) => void;
}) {
  const locked = setting.env_locked;

  if (setting.type === 'list') {
    const teams = Array.isArray(value) ? value : [];
    return (
      <div className="flex flex-wrap items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 text-sm">
            {setting.label}
            {locked && <Lock size={11} className="text-muted-foreground" aria-label="Set by environment variable" />}
          </div>
          {setting.help && <div className="text-[11px] text-muted-foreground">{setting.help}</div>}
        </div>
        <TeamList teams={teams} onChange={(v) => onChange(v)} locked={locked} />
      </div>
    );
  }

  if (setting.key === 'report_logo_url') {
    return (
      <div className="flex flex-wrap items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 text-sm">
            {setting.label}
            {locked && <Lock size={11} className="text-muted-foreground" aria-label="Set by environment variable" />}
          </div>
          {setting.help && <div className="text-[11px] text-muted-foreground">{setting.help}</div>}
        </div>
        <LogoInput value={typeof value === 'string' ? value : ''} onChange={(v) => onChange(v)} locked={locked} />
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-start gap-3">
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5 text-sm">
          {setting.label}
          {locked && <Lock size={11} className="text-muted-foreground" aria-label="Set by environment variable" />}
        </div>
        {setting.help && <div className="text-[11px] text-muted-foreground">{setting.help}</div>}
      </div>
      <div className="shrink-0 w-56 max-w-full">
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

function TeamList({ teams, onChange, locked }: { teams: string[]; onChange: (v: string[]) => void; locked: boolean }) {
  const [newName, setNewName] = useState('');

  const add = () => {
    const name = newName.trim();
    if (!name || teams.includes(name)) return;
    onChange([...teams, name]);
    setNewName('');
  };

  const remove = (name: string) => {
    onChange(teams.filter((t) => t !== name));
  };

  return (
    <div className="shrink-0 w-64 max-w-full space-y-2">
      <div className="flex flex-wrap gap-1">
        {teams.map((t) => (
          <span key={t} className="inline-flex items-center gap-1 rounded-full bg-accent px-2 py-0.5 text-xs">
            {t}
            {!locked && (
              <button onClick={() => remove(t)} className="text-muted-foreground hover:text-destructive">
                <X size={11} />
              </button>
            )}
          </span>
        ))}
        {teams.length === 0 && (
          <span className="text-xs text-muted-foreground italic">No teams defined</span>
        )}
      </div>
      {!locked && (
        <div className="flex gap-1.5">
          <input
            className="input text-xs flex-1"
            placeholder="Add team…"
            value={newName}
            onChange={(e) => setNewName(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); add(); } }}
          />
          <button className="btn-ghost p-1" onClick={add} disabled={!newName.trim()} title="Add team">
            <Plus size={14} />
          </button>
        </div>
      )}
    </div>
  );
}

// ~1 MB keeps the base64 logo small in settings.yaml; a report logo never
// needs more. The value is stored as a data: URI (or a plain URL).
const MAX_LOGO_BYTES = 1_000_000;

function LogoInput({ value, onChange, locked }: { value: string; onChange: (v: string) => void; locked: boolean }) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [err, setErr] = useState('');
  const isData = value.startsWith('data:');
  const embeddedKb = isData ? Math.round((value.length * 3) / 4 / 1024) : 0;

  const pick = (file: File | undefined) => {
    setErr('');
    if (!file) return;
    if (!file.type.startsWith('image/')) {
      setErr('Please choose an image file (PNG recommended).');
      return;
    }
    if (file.size > MAX_LOGO_BYTES) {
      setErr(`Image is too large (${Math.round(file.size / 1024)} KB). Max ${MAX_LOGO_BYTES / 1000} KB.`);
      return;
    }
    const reader = new FileReader();
    reader.onload = () => onChange(String(reader.result || ''));
    reader.onerror = () => setErr('Could not read the file.');
    reader.readAsDataURL(file);
  };

  return (
    <div className="shrink-0 w-64 max-w-full space-y-2">
      {value ? (
        <div className="flex items-center gap-2">
          <img src={value} alt="Logo preview" className="max-h-10 max-w-[7rem] rounded border border-border bg-white/5 object-contain" />
          {!locked && (
            <button onClick={() => { onChange(''); setErr(''); }} className="text-muted-foreground hover:text-destructive" title="Remove logo">
              <X size={13} />
            </button>
          )}
        </div>
      ) : (
        <div className="text-xs text-muted-foreground italic">No logo set</div>
      )}
      {isData ? (
        <div className="text-[11px] text-muted-foreground">Embedded image ({embeddedKb} KB)</div>
      ) : (
        <input
          className="input text-xs w-full font-mono"
          placeholder="https://… or paste a data: URI"
          value={value}
          disabled={locked}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
      {!locked && (
        <>
          <input
            ref={inputRef}
            type="file"
            accept="image/png,image/jpeg,image/svg+xml"
            className="hidden"
            onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ''; }}
          />
          <button onClick={() => inputRef.current?.click()} className="btn-secondary text-xs w-full justify-center">
            <Upload size={13} /> Upload PNG
          </button>
        </>
      )}
      {err && <div className="text-[11px] text-destructive">{err}</div>}
    </div>
  );
}
