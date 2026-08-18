import { useState, useEffect, useCallback } from "react";
import axios from "axios";
import { API, useAuth } from "../App";
import { Gear, Plus, Trash, FloppyDisk, MapPin } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "../components/ui/card";
import { Switch } from "../components/ui/switch";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "../components/ui/select";
import { toast } from "sonner";

export default function Settings() {
  const { user } = useAuth();
  const isAdmin = user?.role !== "instructor";
  const [s, setS] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/reservations/settings`, { withCredentials: true });
      setS(res.data);
    } catch {
      toast.error("Nepodařilo se načíst nastavení");
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  const setField = (k, v) => setS((prev) => ({ ...prev, [k]: v }));

  const setLocation = (i, v) => setS((prev) => {
    const locations = [...prev.locations];
    locations[i] = v;
    return { ...prev, locations };
  });
  const addLocation = () => setS((prev) => ({ ...prev, locations: [...(prev.locations || []), ""] }));
  const removeLocation = (i) => setS((prev) => ({ ...prev, locations: prev.locations.filter((_, idx) => idx !== i) }));

  const setDistance = (i, key, v) => setS((prev) => {
    const distances = [...prev.distances];
    distances[i] = { ...distances[i], [key]: v };
    return { ...prev, distances };
  });
  const addDistance = () => setS((prev) => ({ ...prev, distances: [...(prev.distances || []), { from: "", to: "", km: 0 }] }));
  const removeDistance = (i) => setS((prev) => ({ ...prev, distances: prev.distances.filter((_, idx) => idx !== i) }));

  const save = async () => {
    setSaving(true);
    try {
      const payload = {
        base_limit_km: parseFloat(s.base_limit_km) || 0,
        minutes_per_hour_unit: parseInt(s.minutes_per_hour_unit) || 45,
        gps_tz_offset_hours: parseInt(s.gps_tz_offset_hours) || 0,
        private_by_instructor: !!s.private_by_instructor,
        locations: (s.locations || []).map((x) => x.trim()).filter(Boolean),
        distances: (s.distances || [])
          .filter((d) => d.from && d.to)
          .map((d) => ({ from: d.from, to: d.to, km: parseFloat(d.km) || 0 })),
      };
      const res = await axios.put(`${API}/reservations/settings`, payload, { withCredentials: true });
      setS(res.data);
      toast.success("Nastavení uloženo");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Uložení se nezdařilo");
    } finally {
      setSaving(false);
    }
  };

  if (!s) return <div className="p-8 text-[#71717A]">Načítám…</div>;

  const numInput = "border border-[#E4E4E7] rounded-lg px-3 py-2 text-sm w-full";

  return (
    <div className="max-w-[900px] mx-auto space-y-6" data-testid="settings-page">
      <div className="flex items-center gap-3">
        <div className="w-11 h-11 rounded-xl bg-[#002FA7]/10 flex items-center justify-center">
          <Gear size={24} weight="duotone" className="text-[#002FA7]" />
        </div>
        <div>
          <h1 className="font-['Manrope'] text-2xl font-bold text-[#18181B]">Nastavení reportu</h1>
          <p className="text-sm text-[#52525B]">Limity, stanoviště a tolerance přejezdů pro report ujetých km</p>
        </div>
      </div>

      {!isAdmin && <p className="text-sm text-[#A16207] bg-amber-50 border border-amber-200 rounded-lg px-4 py-2">Nastavení může měnit pouze admin.</p>}

      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base">Limity a výpočet</CardTitle></CardHeader>
        <CardContent className="grid sm:grid-cols-2 gap-4">
          <div>
            <label className="block text-xs font-medium text-[#71717A] mb-1">Výchozí limit km na jízdu</label>
            <input type="number" disabled={!isAdmin} value={s.base_limit_km} onChange={(e) => setField("base_limit_km", e.target.value)} className={numInput} data-testid="setting-base-limit" />
          </div>
          <div>
            <label className="block text-xs font-medium text-[#71717A] mb-1">Délka 1 hodiny výcviku (min)</label>
            <input type="number" disabled={!isAdmin} value={s.minutes_per_hour_unit} onChange={(e) => setField("minutes_per_hour_unit", e.target.value)} className={numInput} data-testid="setting-minutes" />
          </div>
          <div>
            <label className="block text-xs font-medium text-[#71717A] mb-1">Posun času GPS vůči UTC (hod)</label>
            <input type="number" disabled={!isAdmin} value={s.gps_tz_offset_hours} onChange={(e) => setField("gps_tz_offset_hours", e.target.value)} className={numInput} data-testid="setting-tz" />
            <p className="text-[11px] text-[#A1A1AA] mt-1">Léto = 2, zima = 1 (SEČ/SELČ)</p>
          </div>
          <div className="flex items-center gap-3 pt-6">
            <Switch disabled={!isAdmin} checked={!!s.private_by_instructor} onCheckedChange={(v) => setField("private_by_instructor", v)} data-testid="setting-private-instructor" />
            <span className="text-sm">Instruktor smí označit jízdu jako soukromou</span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-base flex items-center gap-2"><MapPin size={18} weight="duotone" /> Stanoviště (nástupní místa)</CardTitle></CardHeader>
        <CardContent className="space-y-2">
          {(s.locations || []).map((loc, i) => (
            <div key={i} className="flex gap-2">
              <input disabled={!isAdmin} value={loc} onChange={(e) => setLocation(i, e.target.value)} className={numInput} data-testid={`location-${i}`} placeholder="Např. Karlovy Vary, Dolní nádraží" />
              {isAdmin && <button onClick={() => removeLocation(i)} className="text-[#991B1B] p-2 hover:bg-red-50 rounded"><Trash size={16} weight="duotone" /></button>}
            </div>
          ))}
          {isAdmin && <Button variant="outline" size="sm" onClick={addLocation} data-testid="add-location"><Plus size={14} className="mr-1" /> Přidat stanoviště</Button>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">Vzdálenosti mezi stanovišti (tolerance přejezdu)</CardTitle>
          <p className="text-xs text-[#71717A]">Km přičtené k limitu za přejezd mezi dvěma stanovišti. Např. KV ↔ Ostrov = 12 km.</p>
        </CardHeader>
        <CardContent className="space-y-2">
          {(s.distances || []).map((d, i) => (
            <div key={i} className="flex flex-wrap items-center gap-2" data-testid={`distance-${i}`}>
              <div className="min-w-[180px] flex-1">
                <Select value={d.from} onValueChange={(v) => setDistance(i, "from", v)} disabled={!isAdmin}>
                  <SelectTrigger><SelectValue placeholder="Z" /></SelectTrigger>
                  <SelectContent>{(s.locations || []).filter(Boolean).map((l) => <SelectItem key={l} value={l}>{l}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <span className="text-[#71717A]">↔</span>
              <div className="min-w-[180px] flex-1">
                <Select value={d.to} onValueChange={(v) => setDistance(i, "to", v)} disabled={!isAdmin}>
                  <SelectTrigger><SelectValue placeholder="Do" /></SelectTrigger>
                  <SelectContent>{(s.locations || []).filter(Boolean).map((l) => <SelectItem key={l} value={l}>{l}</SelectItem>)}</SelectContent>
                </Select>
              </div>
              <input type="number" disabled={!isAdmin} value={d.km} onChange={(e) => setDistance(i, "km", e.target.value)} className="border border-[#E4E4E7] rounded-lg px-3 py-2 text-sm w-24" placeholder="km" />
              <span className="text-sm text-[#71717A]">km</span>
              {isAdmin && <button onClick={() => removeDistance(i)} className="text-[#991B1B] p-2 hover:bg-red-50 rounded"><Trash size={16} weight="duotone" /></button>}
            </div>
          ))}
          {isAdmin && <Button variant="outline" size="sm" onClick={addDistance} data-testid="add-distance"><Plus size={14} className="mr-1" /> Přidat vzdálenost</Button>}
        </CardContent>
      </Card>

      {isAdmin && (
        <div className="flex justify-end">
          <Button onClick={save} disabled={saving} data-testid="save-settings-btn">
            <FloppyDisk size={16} weight="duotone" className="mr-1" /> {saving ? "Ukládám…" : "Uložit nastavení"}
          </Button>
        </div>
      )}
    </div>
  );
}
