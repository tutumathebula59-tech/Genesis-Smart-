const base = (p) => ({ width: p.size || 18, height: p.size || 18, viewBox: "0 0 24 24", fill: "none", stroke: p.color || "currentColor", strokeWidth: 1.8, strokeLinecap: "round", strokeLinejoin: "round" });
export const ShieldIcon = (p) => <svg {...base(p)}><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" /></svg>;
export const BoltIcon = (p) => <svg {...base(p)}><path d="M13 2L4 14h7l-1 8 9-12h-7z" /></svg>;
export const WifiIcon = (p) => <svg {...base(p)}><path d="M2 9a15 15 0 0120 0M5 12.5a10 10 0 0114 0M8.5 16a5 5 0 017 0" /><circle cx="12" cy="19.5" r="1" /></svg>;
